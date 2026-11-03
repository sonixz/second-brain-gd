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
from engine.assistant.llm import TTS_PRICE_PER_1M_CHARS, estimate_cost
from engine.events import utc_now

DEFAULTS = {
    "assistant_chat_model": "gpt-4o",
    "assistant_classify_model": "gpt-4o-mini",
    "assistant_voice": "marin",
    "assistant_auto_classify": True,
    "assistant_min_confidence": 0.6,
}
MAX_TOOL_ROUNDS = 5
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
- Quand il te dicte une idée, une tâche ou une décision, enregistre-la avec create_note dans le bon espace.
- Réponses courtes et parlées (2 à 5 phrases), sauf si on te demande du détail. Pas de listes à puces longues.
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
    database.record_event(conn, {"timestamp": utc_now(), "component": "assistant", "stage": what, "status": "ok",
                                 "message": f"{what}: {model}, {usage.get('prompt_tokens', 0)}+"
                                            f"{usage.get('completion_tokens', 0)} tokens, ≈ ${cost:.4f}",
                                 "details": {"model": model, "usage": usage, "estimated_cost_usd": cost}})
    return cost


def _snapshot(conn: sqlite3.Connection, note_id: str) -> dict[str, Any]:
    n = brain.get_note(conn, note_id)
    return {k: n[k] for k in ("title", "body", "space_id", "kind")}


def undo(conn: sqlite3.Connection, action_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM assistant_actions WHERE id = ?", (action_id,)).fetchone()
    if row is None:
        raise brain.NotFound(f"action {action_id}")
    if row["undone_at"]:
        return {"undone": False, "reason": "already undone"}
    before = json.loads(row["before"]) if row["before"] else None
    if row["kind"] == "create_note":
        try:
            brain.delete_note(conn, row["note_id"])
        except brain.NotFound:
            pass
    elif before:
        try:
            brain.update_note(conn, row["note_id"], **before)
        except brain.NotFound:
            pass
        conn.execute("DELETE FROM links WHERE from_note = ? AND created_by = 'assistant' AND created_at >= ?",
                     (row["note_id"], row["created_at"]))
    conn.execute("UPDATE assistant_actions SET undone_at = ? WHERE id = ?", (utc_now(), action_id))
    return {"undone": True, "kind": row["kind"], "note_id": row["note_id"]}


# ---------------------------------------------------------- classification
def classify(conn: sqlite3.Connection, client: Any, note_id: str) -> dict[str, Any]:
    """Proposes space, title, kind, tags and links for a note, and applies them when confident."""
    s = settings(conn)
    note = brain.get_note(conn, note_id)
    spaces = []
    for sp in brain.list_spaces(conn):
        titles = [r["title"] for r in conn.execute(
            "SELECT title FROM notes WHERE space_id = ? AND id != ? ORDER BY updated_at DESC LIMIT 5", (sp["id"], note_id))]
        spaces.append({"id": sp["id"], "name": sp["name"], "kind": sp["kind"], "examples": titles})
    words = " ".join(re.findall(r"[\w-]{4,}", note["title"] + " " + note["body"])[:8])
    candidates = [{"id": r["id"], "title": r["title"]} for r in brain.search(conn, words, 8) if r["id"] != note_id][:6] if words else []
    ctx = {"note": {"title": note["title"], "body": note["body"][:2000]}, "spaces": spaces, "candidates": candidates}
    system = ("Tu ranges les notes d'un second cerveau. Réponds en JSON uniquement avec les clés: "
              "space_id (un id de la liste, 'inbox' si incertain), title (titre court et clair, dans la langue de la note, "
              "garde le sens), kind (note|idea|task|journal|reference), tags (0 à 2 mots-clés courts en minuscules, sans #; plusieurs mots reliés par un tiret, ex. mode-nuit), "
              "link_ids (0 à 2 ids parmi candidates vraiment liés), confidence (0 à 1), reason (une phrase courte en français).")
    res = client.complete(s["assistant_classify_model"], [{"role": "system", "content": system},
                                                          {"role": "user", "content": json.dumps(ctx, ensure_ascii=False)}],
                          json_mode=True, temperature=0.1)
    _usage_event(conn, "classify", res["model"], res["usage"], client.provider)
    try:
        prop = json.loads(res["message"]["content"] or "{}")
    except ValueError:
        return {"applied": False, "reason": "unreadable proposal"}
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


# ------------------------------------------------------------------ tools
TOOLS = [
    {"type": "function", "function": {"name": "search_notes", "description": "Full-text search in the user's notes.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
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
    {"type": "function", "function": {"name": "update_note", "description": "Move or edit a note (space, title, kind, body, status).",
        "parameters": {"type": "object", "properties": {"note_id": {"type": "string"}, "space_id": {"type": "string"},
                                                         "title": {"type": "string"}, "body": {"type": "string"},
                                                         "kind": {"type": "string", "enum": list(brain.KINDS)},
                                                         "status": {"type": "string", "enum": ["active", "done", "archived"]}},
                       "required": ["note_id"]}}},
]


def run_tool(conn: sqlite3.Connection, name: str, args: dict[str, Any], actions: list[dict[str, Any]]) -> Any:
    try:
        if name == "search_notes":
            return {"results": [{k: r[k] for k in ("id", "title", "space_id", "kind", "snippet")}
                                for r in brain.search(conn, str(args.get("query", "")), 8)]}
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


def chat(conn: sqlite3.Connection, client: Any, text: str, space_id: str | None = None) -> dict[str, Any]:
    s = settings(conn)
    conversation = today_conversation()
    focus = ""
    if space_id:
        try:
            sp = brain.get_space(conn, space_id)
            focus = f"\nMode projet: l'utilisateur travaille sur l'espace « {sp['name']} » (id {sp['id']}). Concentre-toi dessus."
        except brain.NotFound:
            pass
    now = datetime.now().strftime("%A %Y-%m-%d %H:%M")
    messages: list[dict[str, Any]] = [{"role": "system", "content": PERSONA + f"\nNous sommes le {now}." + focus}]
    for m in history(conn, conversation, HISTORY):
        messages.append({"role": "assistant" if m["role"] in ("assistant", "briefing") else "user", "content": m["content"]})
    messages.append({"role": "user", "content": text})
    _save(conn, conversation, "user", text)
    actions: list[dict[str, Any]] = []
    cost = 0.0
    reply = ""
    for _ in range(MAX_TOOL_ROUNDS):
        res = client.complete(s["assistant_chat_model"], messages, tools=TOOLS)
        cost += _usage_event(conn, "chat", res["model"], res["usage"], client.provider)
        msg = res["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            reply = (msg.get("content") or "").strip()
            break
        messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls})
        for call in calls:
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except ValueError:
                args = {}
            result = run_tool(conn, call["function"]["name"], args, actions)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)[:12000]})
    if not reply:
        reply = "Je n'ai pas réussi à terminer. Peux-tu reformuler?"
    cited = _cited(conn, reply)
    _save(conn, conversation, "assistant", reply, {"actions": actions, "cited": cited, "estimated_cost_usd": round(cost, 6)})
    return {"reply": reply, "actions": actions, "cited": cited, "estimated_cost_usd": round(cost, 6)}


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
    facts = {"now": datetime.now().strftime("%A %d %B %Y, %H:%M"), "new_since_last_briefing": new, "open_tasks": tasks,
             "inbox_count": inbox, "oldest_ideas": dormant, "spaces": spaces}
    system = (PERSONA + "\nTu écris le briefing du matin qui sera LU À VOIX HAUTE. 60 à 110 mots, ton parlé, "
              "pas de listes ni de crochets ni d'emojis. Salue selon l'heure, résume ce qui compte aujourd'hui "
              "(tâches ouvertes, nouveautés, Inbox), rappelle au plus une idée qui dort, puis propose par quoi commencer "
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


# ------------------------------------------------------------------ voice
def speak(conn: sqlite3.Connection, client: Any, text: str, theme: str, cache_dir: Path) -> tuple[bytes, bool]:
    s = settings(conn)
    text = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", r"\1", text)[:3000]  # say titles, not brackets
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
