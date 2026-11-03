"""Assistant logic over the second brain. Synchronous; called from API threads."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine import brain, database
from engine.brain import structure
from engine.assistant.llm import LLMError, TTS_PRICE_PER_1M_CHARS, estimate_cost
from engine.events import utc_now

DEFAULTS = {
    "assistant_chat_model": "gpt-4o",
    # Measured 2026-11-02 on 10 French captures (tools/model_bench.py): gpt-6-sol 10/10 in 1.45 s,
    # gpt-4o 9/10, gpt-4o-mini 7/10. Chat stays on gpt-4o: as correct with tools and faster (2.9 s vs 4.4 s).
    "assistant_classify_model": "gpt-6-sol",
    # Weekly review and deep syntheses: a reasoning model through the Responses API (Loop 6b).
    "assistant_review_model": "gpt-6-astra",
    # Measured 2026-11-03 (tools/model_bench.py --review): astra@low 10.6 s cites notes and links facts;
    # astra@medium 16.4 s barely deeper; gpt-4o 3.5 s but generic.
    "assistant_review_effort": "low",
    "assistant_voice": "marin",
    "assistant_auto_classify": True,
    "assistant_min_confidence": 0.6,
}
# When a user's OpenAI project lacks a configured model, the job falls back instead of failing.
FALLBACK_MODELS = {"assistant_classify_model": "gpt-4o-mini", "assistant_review_model": "gpt-4o"}
MAX_TOOL_ROUNDS = 8
# A reply that claims an interface action or an undo, in a turn where no tool ran, gets one nudge
# (measured 2026-11-03: gpt-4o sometimes said « j'annule » or « la revue est lancée » without the tool).
CLAIM_RE = re.compile(r"\b(j'annule|c'est annulé|annulée?s?\b|je l'ouvre|j'ouvre|j'ai ouvert|ouverte?\b|"
                      r"c'est affiché|j'affiche|affichée?\b|est lancée?|je lance|j'ai lancé|activée?\b|baissé|monté)",
                      re.IGNORECASE)
CLAIM_NUDGE = ("Tu viens d'affirmer une action sans appeler d'outil dans ce tour. Si l'utilisateur la demande, "
               "appelle maintenant l'outil (ui_* ou undo_last_action). Sinon, corrige ta réponse sans prétendre "
               "l'avoir faite.")
HISTORY = 20

VOICE_TONES = {
    "morning": "Voix chaleureuse, calme et souriante, comme une assistante bienveillante le matin. Débit posé.",
    "focus": "Voix claire, concise et posée, qui va droit au but sans précipitation.",
    "evening": "Voix douce et détendue, chaleureuse, rythme lent de fin de journée.",
    "forest": "Voix calme et naturelle, apaisante.",
}
ACCENT = " Accent québécois naturel et léger, français du Québec."

PERSONA = """Tu es l'assistante de Second Brain GD, le second cerveau personnel de l'utilisateur.
Tu parles comme une collègue chaleureuse et efficace, en français québécois naturel (tutoiement),
sauf si l'utilisateur écrit dans une autre langue: réponds alors dans sa langue.
Règles:
- Tu travailles avec ses notes grâce aux outils. Cherche avant d'affirmer quelque chose sur ses projets.
- Ne jamais inventer le contenu d'une note.
- IMPORTANT: chaque fois que ta réponse s'appuie sur une note, écris son titre EXACT entre doubles crochets
  dans ta phrase, ex. « d'après [[Atlas risks]], ... ». L'interface en fait un lien cliquable.
- Structure: domaines (areas, permanents) > projets (résultat + échéance) > tâches (prochaines actions).
  Une tâche à faire = add_task dans le bon projet (avec due_date AAAA-MM-JJ si une date est dite).
  Une idée, une décision ou une info = create_note. Des articles d'épicerie ou de liste = add_to_checklist.
  Un nouveau projet = create_project sous le bon domaine. « C'est fait » = complete_task.
- Pour « qu'est-ce que j'ai aujourd'hui / cette semaine », utilise get_today.
- Tu pilotes aussi l'interface: l'utilisateur peut tout faire à la voix, sans cliquer. Dès qu'il dit
  « montre, ouvre, affiche, va dans, lance, mets », APPELLE l'outil d'interface correspondant:
  une vue (graphe, aujourd'hui, projets, agents) = ui_open_view; un projet = ui_open_project (id via
  get_structure); une note = ui_open_note (trouve son id avec search_notes d'abord); thème = ui_set_theme;
  son = ui_set_volume; la revue de la semaine = ui_start_weekly_review; « annule ça » = undo_last_action.
  « Qu'est-ce que j'ai aujourd'hui? Affiche-le » = get_today ET ui_open_view(today).
  INTERDIT: dire « je l'ouvre », « c'est affiché » ou « c'est lancé » sans avoir appelé l'outil ui_* dans ce
  tour. Après une action d'interface, réponds en une phrase courte (elle est lue à voix haute).
- Pour une question de fond, cherche dans les notes (search_notes) ET dans les documents importés (search_sources).
  Cite un document par le titre de sa fiche entre [[ ]].
- Réponses courtes et parlées (2 à 5 phrases), sauf si on te demande du détail. Pas de listes à puces longues, pas d'emojis.
- Ne refais jamais une action déjà indiquée comme effectuée dans l'historique.
- Tout ce que tu modifies est visible et annulable: dis brièvement ce que tu as fait."""


def settings(conn: sqlite3.Connection) -> dict[str, Any]:
    return {k: database.get_setting(conn, k, v) for k, v in DEFAULTS.items()}


def today_conversation() -> str:
    return "daily-" + datetime.now().strftime("%Y-%m-%d")


# --------------------------------------------------------------- journal
def _journal(conn: sqlite3.Connection, kind: str, note_id: str | None, before: Any, after: Any, reason: str) -> int:
    cur = conn.execute("INSERT INTO assistant_actions (kind, note_id, before, after, reason, created_at)"
                       " VALUES (?, ?, ?, ?, ?, ?)", (kind, note_id, json.dumps(before), json.dumps(after),
                                                    reason[:500], utc_now()))
    return int(cur.lastrowid)


def _usage_event(conn: sqlite3.Connection, what: str, model: str, usage: dict[str, Any], provider: str) -> float:
    cost = estimate_cost(model, usage) if provider == "openai" else 0.0
    price = f"≈ ${cost:.4f}" if cost is not None else "cost unknown (no price for this model)"
    database.record_event(conn, {"timestamp": utc_now(), "component": "assistant", "stage": what, "status": "ok",
                                 "message": f"{what}: {model}, {usage.get('prompt_tokens', 0)}+"
                                            f"{usage.get('completion_tokens', 0)} tokens, {price}",
                                 "details": {"model": model, "usage": usage, "estimated_cost_usd": cost}})
    return cost or 0.0


def _snapshot(conn: sqlite3.Connection, note_id: str) -> dict[str, Any]:
    n = brain.get_note(conn, note_id)
    return {k: n[k] for k in ("title", "body", "space_id", "kind", "status", "due_date")}


def undo(conn: sqlite3.Connection, action_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM assistant_actions WHERE id = ?", (action_id,)).fetchone()
    if row is None:
        raise brain.NotFound(f"action {action_id}")
    if row["undone_at"]:
        return {"undone": False, "reason": "already undone"}
    kind = row["kind"]
    before = json.loads(row["before"]) if row["before"] else None
    after = json.loads(row["after"]) if row["after"] else {}
    result: dict[str, Any] = {"undone": True, "kind": kind, "note_id": row["note_id"]}
    if kind == "to_checklist":
        for item_id in after.get("item_ids", []):
            structure.delete_item(conn, int(item_id))
        if before:  # a capture had been turned into list items: bring the note back
            restored = brain.create_note(conn, before["title"], before["body"], before["space_id"], before["kind"],
                                         source=before.get("source") if before.get("source") in ("typed", "voice") else "typed")
            result["note_id"] = restored["id"]
    elif kind == "create_project":
        conn.execute("UPDATE spaces SET archived_at = ? WHERE id = ?", (utc_now(), row["note_id"]))
    elif kind in ("create_note", "add_task"):
        try:
            brain.delete_note(conn, row["note_id"])
        except brain.NotFound:
            pass
    elif before:  # classify, update_note, complete_task: restore the previous state
        try:
            brain.update_note(conn, row["note_id"], **{k: v for k, v in before.items() if k != "due_date"})
            conn.execute("UPDATE notes SET due_date = ? WHERE id = ?", (before.get("due_date"), row["note_id"]))
        except brain.NotFound:
            pass
        conn.execute("DELETE FROM links WHERE from_note = ? AND created_by = 'assistant' AND created_at >= ?",
                     (row["note_id"], row["created_at"]))
    conn.execute("UPDATE assistant_actions SET undone_at = ? WHERE id = ?", (utc_now(), action_id))
    return result


# ---------------------------------------------------------- classification
def classify(conn: sqlite3.Connection, client: Any, note_id: str) -> dict[str, Any]:
    """Proposes space, title, kind, tags and links for a note, and applies them when confident."""
    s = settings(conn)
    note = brain.get_note(conn, note_id)
    spaces = []
    all_spaces = brain.list_spaces(conn)
    names = {sp["id"]: sp["name"] for sp in all_spaces}
    for sp in all_spaces:
        titles = [r["title"] for r in conn.execute(
            "SELECT title FROM notes WHERE space_id = ? AND id != ? ORDER BY updated_at DESC LIMIT 5", (sp["id"], note_id))]
        entry = {"id": sp["id"], "name": sp["name"], "kind": sp["kind"], "examples": titles}
        for k in ("goal", "why"):
            if sp.get(k):
                entry[k] = sp[k]
        if sp.get("area_id"):
            entry["area"] = names.get(sp["area_id"], "")
        spaces.append(entry)
    words = " ".join(re.findall(r"[\w-]{4,}", note["title"] + " " + note["body"])[:8])
    candidates = [{"id": r["id"], "title": r["title"]} for r in brain.search(conn, words, 8) if r["id"] != note_id][:6] if words else []
    checklists = [{"id": c["id"], "name": c["name"]} for c in structure.list_checklists(conn)]
    ctx = {"note": {"title": note["title"], "body": note["body"][:2000]}, "spaces": spaces, "candidates": candidates,
           "checklists": checklists}
    system = ("Tu ranges les notes d'un second cerveau. Si la note n'est qu'une liste d'articles à ajouter à une liste "
              "existante (ex. épicerie: « acheter lait et pain »), réponds {\"target\": \"checklist\", \"checklist_id\": id, "
              "\"items\": [articles courts], \"confidence\": 0-1, \"reason\": phrase}. Sinon réponds en JSON avec les clés: "
              "space_id (l'espace le plus précis: un projet si la note le concerne, sinon le domaine de vie qui "
              "correspond (kind=area: famille, santé, maison, travail/vision); 'inbox' seulement si rien ne colle "
              "vraiment; une idée sur une app ou un produit va dans le projet de ce produit), title (titre court et clair, dans la langue de la note, "
              "garde le sens), kind (note|idea|task|journal|reference), tags (0 à 2 mots-clés courts en minuscules, sans #; plusieurs mots reliés par un tiret, ex. mode-nuit), "
              "link_ids (0 à 2 ids parmi candidates vraiment liés), confidence (0 à 1), reason (une phrase courte en français).")
    res = complete_with_fallback(conn, client, "assistant_classify_model",
                                 [{"role": "system", "content": system},
                                  {"role": "user", "content": json.dumps(ctx, ensure_ascii=False)}],
                                 json_mode=True, temperature=0.1)
    _usage_event(conn, "classify", res["model"], res["usage"], client.provider)
    try:
        prop = json.loads(res["message"]["content"] or "{}")
    except ValueError:
        return {"applied": False, "reason": "unreadable proposal"}
    if prop.get("target") == "checklist":
        return _file_to_checklist(conn, note, prop, checklists, float(s["assistant_min_confidence"]))
    valid_spaces = {sp["id"] for sp in spaces}
    space_id = prop.get("space_id") if prop.get("space_id") in valid_spaces else note["space_id"]
    confidence = float(prop.get("confidence") or 0)
    proposal = {"space_id": space_id, "space_name": next((sp["name"] for sp in spaces if sp["id"] == space_id), ""),
                "title": str(prop.get("title") or note["title"]).strip()[:120] or note["title"],
                "kind": prop.get("kind") if prop.get("kind") in brain.KINDS else note["kind"],
                "tags": [re.sub(r"[^\w/-]", "", str(t).lower())[:30] for t in (prop.get("tags") or [])][:2],
                "link_ids": [i for i in (prop.get("link_ids") or []) if i in {c["id"] for c in candidates}][:2],
                "confidence": confidence, "reason": str(prop.get("reason") or "")[:300]}
    if confidence < float(s["assistant_min_confidence"]):
        return {"applied": False, "proposal": proposal, "reason": "not confident enough; left in place"}
    before = _snapshot(conn, note_id)
    body = note["body"]
    new_tags = [t for t in proposal["tags"] if t and t not in note["tags"]]
    if new_tags:
        body = (body.rstrip() + "\n\n" if body.strip() else "") + " ".join("#" + t for t in new_tags)
    brain.update_note(conn, note_id, title=proposal["title"], space_id=space_id, kind=proposal["kind"], body=body)
    now = utc_now()
    for target in proposal["link_ids"]:
        conn.execute("INSERT OR IGNORE INTO links (from_note, to_note, kind, created_by, created_at)"
                     " VALUES (?, ?, 'related', 'assistant', ?)", (note_id, target, now))
    action_id = _journal(conn, "classify", note_id, before, _snapshot(conn, note_id), proposal["reason"])
    return {"applied": True, "action_id": action_id, "proposal": proposal}


def _file_to_checklist(conn: sqlite3.Connection, note: dict[str, Any], prop: dict[str, Any],
                       checklists: list[dict[str, Any]], min_conf: float) -> dict[str, Any]:
    cid = prop.get("checklist_id")
    items = [str(i).strip()[:200] for i in (prop.get("items") or []) if str(i).strip()][:30]
    target = next((c for c in checklists if c["id"] == cid), None)
    confidence = float(prop.get("confidence") or 0)
    proposal = {"target": "checklist", "checklist_id": cid, "checklist_name": target["name"] if target else "",
                "items": items, "confidence": confidence, "reason": str(prop.get("reason") or "")[:300]}
    if not target or not items or confidence < min_conf:
        return {"applied": False, "proposal": proposal, "reason": "not confident enough; left in place"}
    before_ids = {i["id"] for i in structure.get_checklist(conn, cid)["items"]}
    structure.add_items(conn, cid, items, source="agent")
    added = [i["id"] for i in structure.get_checklist(conn, cid)["items"] if i["id"] not in before_ids]
    snapshot = {k: note[k] for k in ("title", "body", "space_id", "kind", "source", "created_at")}
    brain.delete_note(conn, note["id"])
    action_id = _journal(conn, "to_checklist", note["id"], snapshot, {"checklist_id": cid, "item_ids": added},
                         proposal["reason"])
    return {"applied": True, "action_id": action_id, "proposal": proposal}


# ------------------------------------------------------------------ tools
TOOLS = [
    {"type": "function", "function": {"name": "search_notes", "description": "Search the user's notes by meaning (any language) and by keywords. Optional space_ids limits the scope (project mode); resources are always included.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"},
                                                         "space_ids": {"type": "array", "items": {"type": "string"}}},
                       "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_note", "description": "Read a note with its links and tags.",
        "parameters": {"type": "object", "properties": {"note_id": {"type": "string"}}, "required": ["note_id"]}}},
    {"type": "function", "function": {"name": "list_spaces", "description": "List spaces (projects, areas) with note counts.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "list_notes", "description": "Recent notes, optionally in one space or of one kind (e.g. open tasks).",
        "parameters": {"type": "object", "properties": {"space_id": {"type": "string"},
                                                         "kind": {"type": "string", "enum": list(brain.KINDS)},
                                                         "limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "create_note", "description": "Save an idea, task, decision or note the user dictates.",
        "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"},
                                                         "space_id": {"type": "string"},
                                                         "kind": {"type": "string", "enum": list(brain.KINDS)}},
                       "required": ["title"]}}},
    {"type": "function", "function": {"name": "search_sources", "description": "Search inside imported documents and web pages (PDF, Word, links). Use it with search_notes for factual questions.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_today", "description": "Today's view: overdue, due today and soon, next action per project, projects without next action, inbox count, checklists.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_structure", "description": "Areas with their projects, resources.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "create_project", "description": "Create a project (an outcome with a deadline) under an area.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "area_id": {"type": "string"},
                                                         "goal": {"type": "string"}, "due_date": {"type": "string", "description": "YYYY-MM-DD"}},
                       "required": ["name"]}}},
    {"type": "function", "function": {"name": "add_task", "description": "Add a next action (task) to a project or area.",
        "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "space_id": {"type": "string"},
                                                         "due_date": {"type": "string", "description": "YYYY-MM-DD"}},
                       "required": ["title"]}}},
    {"type": "function", "function": {"name": "complete_task", "description": "Mark a task as done.",
        "parameters": {"type": "object", "properties": {"note_id": {"type": "string"}}, "required": ["note_id"]}}},
    {"type": "function", "function": {"name": "add_to_checklist", "description": "Add items to a checklist such as Épicerie (by name or id).",
        "parameters": {"type": "object", "properties": {"checklist": {"type": "string"},
                                                         "items": {"type": "array", "items": {"type": "string"}}},
                       "required": ["checklist", "items"]}}},
    {"type": "function", "function": {"name": "update_note", "description": "Move or edit a note (space, title, kind, body, status).",
        "parameters": {"type": "object", "properties": {"note_id": {"type": "string"}, "space_id": {"type": "string"},
                                                         "title": {"type": "string"}, "body": {"type": "string"},
                                                         "kind": {"type": "string", "enum": list(brain.KINDS)},
                                                         "status": {"type": "string", "enum": ["active", "done", "archived"]}},
                       "required": ["note_id"]}}},
]

# Interface tools: the engine validates them, Godot performs them (hands-free control, Loop 7a).
UI_VIEWS = ["graph", "today", "projects", "agents"]
UI_THEMES = ["morning", "focus", "evening", "forest", "auto"]
UI_TOOLS = [
    {"type": "function", "function": {"name": "ui_open_view", "description": "Show a view of the app: graph (the knowledge map), today (what to do now), projects, agents (the agent room).",
     "parameters": {"type": "object", "properties": {"view": {"type": "string", "enum": UI_VIEWS}}, "required": ["view"]}}},
    {"type": "function", "function": {"name": "ui_open_project", "description": "Open a project's card on screen.",
     "parameters": {"type": "object", "properties": {"space_id": {"type": "string"}}, "required": ["space_id"]}}},
    {"type": "function", "function": {"name": "ui_open_note", "description": "Open a note in the inspector and focus it in the graph.",
     "parameters": {"type": "object", "properties": {"note_id": {"type": "string"}}, "required": ["note_id"]}}},
    {"type": "function", "function": {"name": "ui_set_theme", "description": "Change the visual and music theme.",
     "parameters": {"type": "object", "properties": {"theme": {"type": "string", "enum": UI_THEMES}}, "required": ["theme"]}}},
    {"type": "function", "function": {"name": "ui_set_volume", "description": "Change the app's sound: louder, quieter, mute or unmute.",
     "parameters": {"type": "object", "properties": {"change": {"type": "string", "enum": ["up", "down", "mute", "unmute"]}}, "required": ["change"]}}},
    {"type": "function", "function": {"name": "ui_start_weekly_review", "description": "Start the guided weekly review on screen.",
     "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "undo_last_action", "description": "Undo the most recent change the assistant made (a filed note, a task, a list item...).",
     "parameters": {"type": "object", "properties": {}}}},
]
TOOLS = TOOLS + UI_TOOLS
_UI: dict[str, list[dict[str, Any]]] = {"actions": []}  # interface actions requested during the current chat turn


def _ui_tool(conn: sqlite3.Connection, name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "ui_open_view":
        view = str(args.get("view", ""))
        if view not in UI_VIEWS:
            return {"error": f"unknown view, use one of {UI_VIEWS}"}
        act = {"action": "open_view", "view": view}
    elif name == "ui_open_project":
        sid = str(args.get("space_id", ""))
        row = conn.execute("SELECT id, name, kind FROM spaces WHERE id = ?", (sid,)).fetchone()
        if row is None:
            return {"error": "unknown space_id: call get_structure to find the project's id"}
        act = {"action": "open_project", "space_id": sid, "name": row["name"]}
    elif name == "ui_open_note":
        nid = str(args.get("note_id", ""))
        row = conn.execute("SELECT id, title FROM notes WHERE id = ?", (nid,)).fetchone()
        if row is None:
            return {"error": "unknown note_id: search for the note first"}
        act = {"action": "open_note", "note_id": nid, "title": row["title"]}
    elif name == "ui_set_theme":
        theme = str(args.get("theme", ""))
        if theme not in UI_THEMES:
            return {"error": f"unknown theme, use one of {UI_THEMES}"}
        act = {"action": "set_theme", "theme": theme}
    elif name == "ui_set_volume":
        change = str(args.get("change", ""))
        if change not in ("up", "down", "mute", "unmute"):
            return {"error": "change must be up, down, mute or unmute"}
        act = {"action": "set_volume", "change": change}
    else:  # ui_start_weekly_review
        act = {"action": "weekly_review"}
    _UI["actions"].append(act)
    return {"done": True, "shown_to_user": act}


def run_tool(conn: sqlite3.Connection, name: str, args: dict[str, Any], actions: list[dict[str, Any]]) -> Any:
    if name.startswith("ui_"):
        return _ui_tool(conn, name, args)
    if name == "undo_last_action":
        row = conn.execute("SELECT id, kind FROM assistant_actions WHERE undone_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            return {"undone": False, "reason": "nothing to undo"}
        out = undo(conn, int(row["id"]))
        if out.get("undone"):
            _UI["actions"].append({"action": "refresh"})
        return out
    try:
        if name == "search_notes":
            from engine.brain.meaning import search_notes

            hits = search_notes(conn, _CLIENT.get("c"), str(args.get("query", "")), 20)
            scope = [str(s) for s in (args.get("space_ids") or []) if s]
            if scope:
                shared = {r["id"] for r in conn.execute("SELECT id FROM spaces WHERE kind = 'resource'")}
                hits = [h for h in hits if h["space_id"] in scope or h["space_id"] in shared]
            return {"results": [{k: r.get(k) for k in ("id", "title", "space_id", "kind", "snippet", "match")} for r in hits[:8]],
                    "scope": "project + shared resources" if scope else "everything"}
        if name == "get_note":
            n = brain.get_note(conn, str(args["note_id"]))
            n["body"] = n["body"][:4000]
            return n
        if name == "list_spaces":
            return {"spaces": [{k: s[k] for k in ("id", "name", "kind", "note_count")} for s in brain.list_spaces(conn)]}
        if name == "list_notes":
            notes = brain.list_notes(conn, args.get("space_id"), min(int(args.get("limit") or 15), 40))
            if args.get("kind"):
                notes = [n for n in notes if n["kind"] == args["kind"]]
            return {"notes": [{k: n[k] for k in ("id", "title", "space_id", "kind", "status", "updated_at")} for n in notes]}
        if name == "create_note":
            n = brain.create_note(conn, str(args["title"]), str(args.get("body") or ""), args.get("space_id") or None,
                                  args.get("kind") or "note", source="agent")
            aid = _journal(conn, "create_note", n["id"], None, _snapshot(conn, n["id"]), "créée par l'assistante")
            actions.append({"action_id": aid, "kind": "create_note", "note_id": n["id"], "title": n["title"]})
            return {"created": {"id": n["id"], "title": n["title"], "space_id": n["space_id"]}}
        if name == "search_sources":
            from engine.sources.core import search_any

            hits = search_any(conn, _CLIENT.get("c"), str(args.get("query", "")), 6)
            note_titles = {r["id"]: r["title"] for r in conn.execute("SELECT id, title FROM notes")}
            return {"results": [{"document": h["title"], "note_title": note_titles.get(h.get("note_id"), h["title"]),
                                 "excerpt": h["snippet"], "match": h["match"]} for h in hits]}
        if name == "get_today":
            d = structure.today(conn)
            d["checklists"] = [{"name": c["name"], "open_items": [i["text"] for i in c["items"] if not i["done"]][:30]}
                               for c in d["checklists"]]
            return d
        if name == "get_structure":
            s = structure.structure(conn)
            slim = lambda x: {k: x.get(k) for k in ("id", "name", "kind", "status", "goal", "due_date", "open_tasks", "note_count")}
            return {"areas": [{**slim(a), "projects": [slim(p) for p in a["projects"]]} for a in s["areas"]],
                    "loose_projects": [slim(p) for p in s["loose_projects"]], "resources": [slim(r) for r in s["resources"]]}
        if name == "create_project":
            p = structure.create_project(conn, str(args["name"]), args.get("area_id") or None, args.get("goal"),
                                         args.get("due_date") or None)
            aid = _journal(conn, "create_project", p["id"], None, {"name": p["name"]}, "projet créé par l'assistante")
            actions.append({"action_id": aid, "kind": "create_project", "note_id": p["id"], "title": p["name"]})
            return {"created_project": {"id": p["id"], "name": p["name"]}}
        if name == "add_task":
            n = structure.add_task(conn, str(args["title"]), args.get("space_id") or None, args.get("due_date") or None,
                                   source="agent")
            aid = _journal(conn, "add_task", n["id"], None, _snapshot(conn, n["id"]), "tâche ajoutée par l'assistante")
            actions.append({"action_id": aid, "kind": "add_task", "note_id": n["id"], "title": n["title"]})
            return {"created_task": {"id": n["id"], "title": n["title"], "space_id": n["space_id"], "due_date": n["due_date"]}}
        if name == "complete_task":
            nid = str(args["note_id"])
            before = _snapshot(conn, nid)
            n = structure.set_task(conn, nid, done=True)
            aid = _journal(conn, "complete_task", nid, before, _snapshot(conn, nid), "tâche cochée par l'assistante")
            actions.append({"action_id": aid, "kind": "complete_task", "note_id": nid, "title": n["title"]})
            return {"done": {"id": nid, "title": n["title"]}}
        if name == "add_to_checklist":
            cl = structure.find_checklist(conn, str(args["checklist"]))
            before_ids = {i["id"] for i in cl["items"]}
            cl = structure.add_items(conn, cl["id"], [str(i) for i in args.get("items") or []], source="agent")
            added = [i["id"] for i in cl["items"] if i["id"] not in before_ids]
            aid = _journal(conn, "to_checklist", None, None, {"checklist_id": cl["id"], "item_ids": added},
                           f"ajouté à {cl['name']}")
            actions.append({"action_id": aid, "kind": "to_checklist", "note_id": None,
                            "title": f"{cl['name']}: " + ", ".join(i["text"] for i in cl["items"] if i["id"] in added)})
            return {"checklist": cl["name"], "added": len(added)}
        if name == "update_note":
            nid = str(args["note_id"])
            before = _snapshot(conn, nid)
            fields = {k: args[k] for k in ("space_id", "title", "body", "kind", "status") if args.get(k)}
            n = brain.update_note(conn, nid, **fields)
            aid = _journal(conn, "update_note", nid, before, _snapshot(conn, nid), "modifiée par l'assistante")
            actions.append({"action_id": aid, "kind": "update_note", "note_id": nid, "title": n["title"]})
            return {"updated": {"id": nid, "title": n["title"], "space_id": n["space_id"]}}
    except (brain.NotFound, ValueError, KeyError) as exc:
        return {"error": str(exc)}
    return {"error": f"unknown tool {name}"}


# ------------------------------------------------------------------- chat
def history(conn: sqlite3.Connection, conversation: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT id, role, content, meta, created_at FROM assistant_messages WHERE conversation = ?"
                        " AND role IN ('user', 'assistant', 'briefing') ORDER BY id DESC LIMIT ?", (conversation, limit))
    out = [dict(r) for r in rows][::-1]
    for m in out:
        m["meta"] = json.loads(m["meta"]) if m["meta"] else None
    return out


def _save(conn: sqlite3.Connection, conversation: str, role: str, content: str, meta: Any = None) -> None:
    conn.execute("INSERT INTO assistant_messages (conversation, role, content, meta, created_at) VALUES (?, ?, ?, ?, ?)",
                 (conversation, role, content, json.dumps(meta, ensure_ascii=False) if meta else None, utc_now()))


def project_context(conn: sqlite3.Connection, space_id: str) -> str:
    """System-prompt block for project mode: the card, its own instructions, and the search scope."""
    sp = brain.get_space(conn, space_id)
    lines = [f"\nMODE PROJET: l'utilisateur travaille sur « {sp['name']} » (id {sp['id']}, {sp['kind']})."]
    for key, label in (("goal", "Objectif"), ("why", "Pourquoi"), ("due_date", "Échéance"), ("status", "Statut")):
        if sp.get(key):
            lines.append(f"{label}: {sp[key]}")
    open_tasks = [t["title"] + (f" (due {t['due_date']})" if t["due_date"] else "") for t in structure.tasks(conn, space_id)][:10]
    if open_tasks:
        lines.append("Prochaines actions ouvertes: " + "; ".join(open_tasks))
    if sp.get("instructions"):
        lines.append("Consignes propres à ce projet (à respecter): " + str(sp["instructions"]).strip())
    lines.append("Portée: cherche d'abord dans ce projet (search_notes avec space_ids=[cet id]) et dans les ressources "
                 "partagées. Ne cherche dans tout le cerveau que si l'utilisateur le demande (« partout », « dans tout »). "
                 "Range ce qu'il dicte dans ce projet par défaut.")
    return "\n".join(lines)


_CLIENT: dict[str, Any] = {}  # the current request's client, for tools that call the API (semantic search)


def chat(conn: sqlite3.Connection, client: Any, text: str, space_id: str | None = None) -> dict[str, Any]:
    _CLIENT["c"] = client
    s = settings(conn)
    conversation = today_conversation()
    focus = ""
    if space_id:
        try:
            focus = project_context(conn, space_id)
        except brain.NotFound:
            pass
    now = datetime.now().strftime("%A %Y-%m-%d %H:%M")
    messages: list[dict[str, Any]] = [{"role": "system", "content": PERSONA + f"\nNous sommes le {now}." + focus}]
    for m in history(conn, conversation, HISTORY):
        content = m["content"]
        acts = (m.get("meta") or {}).get("actions") or []
        if acts:  # so the model knows what it already did and never repeats it
            content += "\n(Actions déjà effectuées: " + "; ".join(f"{a['kind']} « {a['title']} »" for a in acts) + ")"
        ui_done = (m.get("meta") or {}).get("ui_actions") or []
        if ui_done:  # interface actions really performed, so the model sees the tools behind past replies
            content += "\n(Interface: " + "; ".join(str(u.get("action")) + (f" {u.get('view') or u.get('name') or u.get('title') or u.get('theme') or u.get('change') or ''}") for u in ui_done) + ")"
        messages.append({"role": "assistant" if m["role"] in ("assistant", "briefing") else "user", "content": content})
    messages.append({"role": "user", "content": text})
    _save(conn, conversation, "user", text)
    actions: list[dict[str, Any]] = []
    _UI["actions"] = []
    cost = 0.0
    reply = ""
    tools_ran = False
    nudged = False
    for _ in range(MAX_TOOL_ROUNDS):
        res = client.complete(s["assistant_chat_model"], messages, tools=TOOLS)
        cost += _usage_event(conn, "chat", res["model"], res["usage"], client.provider)
        msg = res["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            reply = (msg.get("content") or "").strip()
            if not tools_ran and not nudged and CLAIM_RE.search(reply):
                nudged = True
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": CLAIM_NUDGE})
                reply = ""
                continue
            break
        tools_ran = True
        messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls,
                         **({"_items": msg["_items"]} if msg.get("_items") else {})})
        for call in calls:
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except ValueError:
                args = {}
            result = run_tool(conn, call["function"]["name"], args, actions)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)[:12000]})
    if not reply:
        # Out of tool rounds: ask for a plain summary of what was done, without tools.
        messages.append({"role": "user", "content": "Résume en 1 à 3 phrases ce que tu viens de faire, sans appeler d'outil."})
        res = client.complete(s["assistant_chat_model"], messages)
        cost += _usage_event(conn, "chat", res["model"], res["usage"], client.provider)
        reply = (res["message"].get("content") or "").strip() or "C'est fait."
    cited = _cited(conn, reply)
    _save(conn, conversation, "assistant", reply, {"actions": actions, "cited": cited, "estimated_cost_usd": round(cost, 6),
                                                   "ui_actions": list(_UI["actions"])})
    return {"reply": reply, "actions": actions, "cited": cited, "estimated_cost_usd": round(cost, 6),
            "ui_actions": list(_UI["actions"])}


def _cited(conn: sqlite3.Connection, text: str) -> list[dict[str, str]]:
    out = []
    for title in dict.fromkeys(m.group(1).strip() for m in brain.WIKILINK.finditer(text)):
        row = conn.execute("SELECT id, title FROM notes WHERE lower(title) = lower(?) LIMIT 1", (title,)).fetchone()
        if row:
            out.append({"id": row["id"], "title": row["title"]})
    return out


# --------------------------------------------------------------- briefing
def briefing(conn: sqlite3.Connection, client: Any, force: bool = False) -> dict[str, Any]:
    """Spoken-style morning briefing, generated once per day (cached)."""
    key = "assistant_briefing_" + datetime.now().strftime("%Y-%m-%d")
    cached = database.get_setting(conn, key)
    if cached and not force:
        return {**cached, "cached": True}
    s = settings(conn)
    since = database.get_setting(conn, "assistant_last_briefing_at") or "1970-01-01T00:00:00Z"
    new = [r["title"] for r in conn.execute("SELECT title FROM notes WHERE created_at > ? AND status != 'archived'"
                                            " ORDER BY created_at DESC LIMIT 10", (since,))]
    tasks = [dict(r) for r in conn.execute("SELECT title, space_id, updated_at FROM notes WHERE kind = 'task'"
                                           " AND status = 'active' ORDER BY updated_at LIMIT 8")]
    inbox = conn.execute("SELECT COUNT(*) FROM notes WHERE space_id = 'inbox' AND status = 'active'").fetchone()[0]
    dormant = [dict(r) for r in conn.execute("SELECT title, updated_at FROM notes WHERE kind = 'idea' AND status = 'active'"
                                             " ORDER BY updated_at LIMIT 3")]
    spaces = [{"name": sp["name"], "notes": sp["note_count"]} for sp in brain.list_spaces(conn)]
    td = structure.today(conn)
    slim = lambda xs: [{"title": x["title"], "project": x.get("space_name"), "due": x.get("due_date")} for x in xs]
    facts = {"now": datetime.now().strftime("%A %d %B %Y, %H:%M"), "new_since_last_briefing": new,
             "overdue": slim(td["overdue"]), "due_today": slim(td["today"]), "due_this_week": slim(td["soon"]),
             "next_action_per_project": [{"project": x["project"], "next": x["title"]} for x in td["next_actions"]],
             "projects_without_next_action": [p["name"] for p in td["projects_without_next_action"]],
             "checklists": [{"name": c["name"], "open_items": sum(1 for i in c["items"] if not i["done"])} for c in td["checklists"]],
             "inbox_count": inbox, "oldest_ideas": dormant, "spaces": spaces}
    system = (PERSONA + "\nTu écris le briefing du matin qui sera LU À VOIX HAUTE. 60 à 110 mots, ton parlé, "
              "pas de listes ni de crochets ni d'emojis. Salue selon l'heure, résume ce qui compte aujourd'hui "
              "(retards et échéances, prochaines actions, projets sans prochaine action, nouveautés, Inbox), rappelle au plus une idée qui dort, puis propose par quoi commencer "
              "avec une question. N'invente rien: utilise seulement les faits fournis.")
    res = client.complete(s["assistant_chat_model"], [{"role": "system", "content": system},
                                                      {"role": "user", "content": json.dumps(facts, ensure_ascii=False)}])
    cost = _usage_event(conn, "briefing", res["model"], res["usage"], client.provider)
    text = (res["message"].get("content") or "").strip()
    out = {"text": text, "generated_at": utc_now(), "estimated_cost_usd": cost}
    database.set_setting(conn, key, out)
    database.set_setting(conn, "assistant_last_briefing_at", utc_now())
    _save(conn, today_conversation(), "briefing", text, {"estimated_cost_usd": cost})
    return {**out, "cached": False}


def _model_refused(exc: Exception) -> bool:
    msg = str(exc).lower()
    return ("http 403" in msg or "http 404" in msg) and "model" in msg


def complete_with_fallback(conn: sqlite3.Connection, client: Any, setting: str, messages: list[dict[str, Any]],
                           **kwargs: Any) -> dict[str, Any]:
    """Calls the model chosen in `setting`; if the user's project lacks it, uses the fallback and says so once."""
    s = settings(conn)
    model = str(s[setting])
    try:
        return client.complete(model, messages, **kwargs)
    except LLMError as exc:
        fallback = FALLBACK_MODELS.get(setting, s["assistant_chat_model"])
        if not _model_refused(exc) or fallback == model:
            raise
        if database.get_setting(conn, f"model_refused:{model}") is None:
            database.set_setting(conn, f"model_refused:{model}", utc_now())
            database.record_event(conn, {"timestamp": utc_now(), "component": "assistant", "stage": "model_fallback",
                                         "status": "warning",
                                         "message": f"{model} is not available on this OpenAI project; using {fallback}",
                                         "details": {"model": model, "fallback": fallback}})
        kwargs.pop("effort", None)
        return client.complete(fallback, messages, **kwargs)


# ------------------------------------------------------------ weekly review
def weekly_review(conn: sqlite3.Connection, client: Any) -> dict[str, Any]:
    """Guided weekly review: progress, blockers and a proposed next step per project,
    the Inbox, and a few reflective questions for the areas (vision at work)."""
    s = settings(conn)
    week_ago = (datetime.now(timezone.utc).timestamp() - 7 * 86400)
    since = datetime.fromtimestamp(week_ago, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    projects = []
    for p in conn.execute("SELECT id, name, goal, due_date, status, area_id FROM spaces WHERE kind = 'project'"
                          " AND archived_at IS NULL AND status != 'done' ORDER BY due_date IS NULL, due_date"):
        done = [r["title"] for r in conn.execute("SELECT title FROM notes WHERE space_id = ? AND kind = 'task'"
                                                 " AND status = 'done' AND done_at > ?", (p["id"], since))]
        open_ = [{"title": r["title"], "due": r["due_date"]} for r in conn.execute(
            "SELECT title, due_date FROM notes WHERE space_id = ? AND kind = 'task' AND status = 'active'"
            " ORDER BY due_date IS NULL, due_date LIMIT 8", (p["id"],))]
        new_notes = [r["title"] for r in conn.execute("SELECT title FROM notes WHERE space_id = ? AND kind != 'task'"
                                                      " AND created_at > ? LIMIT 8", (p["id"], since))]
        projects.append({"name": p["name"], "goal": p["goal"], "due": p["due_date"], "status": p["status"],
                         "done_this_week": done, "open_tasks": open_, "new_notes": new_notes})
    areas = [{"name": a["name"], "new_notes": [r["title"] for r in conn.execute(
        "SELECT title FROM notes WHERE space_id = ? AND created_at > ? LIMIT 8", (a["id"], since))]}
        for a in conn.execute("SELECT id, name FROM spaces WHERE kind = 'area' AND archived_at IS NULL")]
    inbox = [r["title"] for r in conn.execute("SELECT title FROM notes WHERE space_id = 'inbox' AND status = 'active' LIMIT 15")]
    facts = {"week_ending": datetime.now().strftime("%A %d %B %Y"), "projects": projects, "areas": areas, "inbox": inbox}
    system = (PERSONA + "\nTu animes la REVUE HEBDOMADAIRE. Format (texte simple, titres courts, pas de tableau):\n"
              "1) Une phrase d'ouverture sur la semaine.\n2) Pour chaque projet actif: ce qui a avancé, ce qui bloque ou "
              "manque (ex. pas de prochaine action, échéance proche), et UNE prochaine étape concrète proposée.\n"
              "3) Inbox: combien de pensées à trier, et une suggestion.\n4) Trois questions de réflexion pour faire "
              "avancer la vision (surtout le domaine Vision au travail), inspirées des notes de la semaine.\n"
              "N'invente rien: seulement les faits fournis. 150 à 280 mots.")
    res = complete_with_fallback(conn, client, "assistant_review_model",
                                 [{"role": "system", "content": system},
                                  {"role": "user", "content": json.dumps(facts, ensure_ascii=False)}],
                                 effort=str(s.get("assistant_review_effort") or "") or None)
    cost = _usage_event(conn, "weekly_review", res["model"], res["usage"], client.provider)
    text = (res["message"].get("content") or "").strip()
    _save(conn, today_conversation(), "assistant", text, {"kind": "weekly_review", "estimated_cost_usd": cost})
    database.set_setting(conn, "assistant_last_review_at", utc_now())
    return {"text": text, "estimated_cost_usd": cost, "projects": len(projects)}


# ------------------------------------------------------------------ voice
def speak(conn: sqlite3.Connection, client: Any, text: str, theme: str, cache_dir: Path) -> tuple[bytes, bool]:
    s = settings(conn)
    text = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", r"\1", text)[:3000]  # say titles, not brackets
    text = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]", "", text).strip()  # never read emojis aloud
    instructions = VOICE_TONES.get(theme, VOICE_TONES["morning"]) + ACCENT
    digest = hashlib.sha256(f"{s['assistant_voice']}|{instructions}|{text}".encode()).hexdigest()[:24]
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{digest}.mp3"
    if path.exists():
        return path.read_bytes(), True
    audio = client.speak(text, s["assistant_voice"], instructions)
    path.write_bytes(audio)
    cost = round(len(text) / 1e6 * TTS_PRICE_PER_1M_CHARS, 6) if client.provider == "openai" else 0.0
    database.record_event(conn, {"timestamp": utc_now(), "component": "assistant", "stage": "speak", "status": "ok",
                                 "message": f"speak: {len(text)} characters, voice {s['assistant_voice']}, ≈ ${cost:.4f}",
                                 "details": {"chars": len(text), "estimated_cost_usd": cost}})
    for old in sorted(cache_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime)[:-200]:
        old.unlink(missing_ok=True)
    return audio, False
