"""The archivist: the Brain's AI at intake (Loop 9).

It receives an item (anything typed, spoken, a page, a document), understands it as fully as
it can, files it in PARA (creating the place or theme when none fits, so a brand-new Brain
builds its own structure), links it by meaning, and answers with a factual receipt.
No opinions, no challenge: it collects and organises. It asks a question only when it
cannot file the item without one.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from engine import brain, database
from engine.events import utc_now

SYSTEM = """Tu es l'ARCHIVISTE d'un second cerveau (méthode CODE: Capture, Organize, Distill, Express; classement PARA).
Ton rôle: recevoir un élément, le comprendre au maximum et le classer. Tu ne donnes AUCUNE opinion, tu ne
critiques pas, tu ne conseilles pas: tu collectes et tu organises, de façon factuelle.

PARA:
- project: un effort avec un résultat et une échéance (ex. « Lancement du site », « Voyage au Japon »).
- area: une responsabilité permanente (ex. « Santé », « Finances », « Équipe »).
- resource: un sujet d'intérêt ou de référence (ex. « IA & agents », « Recettes », « Architecture logicielle »).
Le cerveau peut être presque vide: si aucune place existante ne convient, PROPOSE-EN UNE NOUVELLE (le plus souvent
une resource au nom large et clair, 1 à 4 mots). Réutilise une place existante dès qu'elle convient vraiment.
Si un contexte de travail est donné, classe dans ce contexte quand l'élément s'y rapporte.

Réponds en JSON strict avec:
- title: titre court et clair, dans la langue de l'élément
- item_type: note | idea | article | document | reference | quote | list | journal
- language: code ISO (fr, en, ...)
- summary: 2 à 4 phrases factuelles en français si l'élément est long (> 400 caractères) ou est une source; sinon null
- key_points: 0 à 6 points courts en français (vide pour une note courte)
- entities: {"people": [], "organizations": [], "concepts": [], "places": [], "dates": []} (seulement ce qui est dans le texte)
- place: {"space_id": "<id existant>"} OU {"new_space": {"name": "...", "kind": "resource|project|area"}}
- themes: 1 à 3 thèmes courts en minuscules, mots reliés par des tirets; réutilise les thèmes existants quand ils conviennent
- link_ids: 0 à 3 ids parmi candidates, seulement s'ils sont vraiment liés
- confidence: 0 à 1 (ta certitude sur le classement)
- question: null, ou UNE question courte seulement si tu ne peux vraiment pas classer sans réponse
- receipt: une phrase factuelle en français: ce que c'est et où c'est classé (ex. « Article sur X, classé dans Ressources › IA & agents, relié à 2 éléments. »)
N'invente rien qui n'est pas dans l'élément."""

ITEM_TYPES = ("note", "idea", "article", "document", "reference", "quote", "list", "journal")
NOTE_KIND = {"note": "note", "idea": "idea", "journal": "journal", "list": "note", "quote": "reference",
             "article": "reference", "document": "reference", "reference": "reference"}
SPACE_COLORS = ["#a6dcff", "#ffd2a1", "#c8b6ff", "#a9f0c7", "#ffb3c6", "#f5e6a3", "#9fd8d0", "#d8c3a5"]
KIND_LABEL = {"project": "Projets", "area": "Domaines", "resource": "Ressources", "archive": "Archives", "inbox": "Inbox"}


def _json_list(v: Any, n: int, size: int = 120) -> list[str]:
    return [str(x).strip()[:size] for x in (v if isinstance(v, list) else []) if str(x).strip()][:n]


def theme_name(t: Any) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^\w-]", "", str(t).strip().lower().replace(" ", "-")))[:30].strip("-")


def get_context(conn: sqlite3.Connection) -> dict[str, Any] | None:
    ctx = database.get_setting(conn, "intake_context")
    if not ctx or not ctx.get("space_id"):
        return None
    row = conn.execute("SELECT id, name, kind FROM spaces WHERE id = ? AND archived_at IS NULL", (ctx["space_id"],)).fetchone()
    return dict(row) if row else None


def set_context(conn: sqlite3.Connection, name: str | None = None, space_id: str | None = None,
                kind: str = "project") -> dict[str, Any] | None:
    """« Je veux structurer le projet X »: the next items are filed with X in mind. None clears it."""
    if not name and not space_id:
        database.set_setting(conn, "intake_context", None)
        return None
    row = None
    if space_id:
        row = conn.execute("SELECT id, name, kind FROM spaces WHERE id = ?", (space_id,)).fetchone()
    elif name:
        row = conn.execute("SELECT id, name, kind FROM spaces WHERE name = ? COLLATE NOCASE AND archived_at IS NULL",
                           (name.strip(),)).fetchone()
        if row is None:
            sp = brain.create_space(conn, name.strip()[:80], kind if kind in ("project", "area", "resource") else "project",
                                    color=_next_color(conn))
            row = {"id": sp["id"], "name": sp["name"], "kind": sp["kind"]}
    if row is None:
        raise brain.NotFound(f"space {space_id or name}")
    database.set_setting(conn, "intake_context", {"space_id": row["id"], "set_at": utc_now()})
    return dict(row)


def _next_color(conn: sqlite3.Connection) -> str:
    n = conn.execute("SELECT COUNT(*) FROM spaces").fetchone()[0]
    return SPACE_COLORS[n % len(SPACE_COLORS)]


def _places(conn: sqlite3.Connection, exclude_note: str) -> list[dict[str, Any]]:
    out = []
    names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM spaces")}
    for sp in brain.list_spaces(conn):
        examples = [r["title"] for r in conn.execute(
            "SELECT title FROM notes WHERE space_id = ? AND id != ? ORDER BY updated_at DESC LIMIT 3", (sp["id"], exclude_note))]
        e = {"id": sp["id"], "name": sp["name"], "kind": sp["kind"], "items": sp.get("note_count", 0), "examples": examples}
        for k in ("goal", "why"):
            if sp.get(k):
                e[k] = sp[k]
        if sp.get("area_id"):
            e["area"] = names.get(sp["area_id"], "")
        out.append(e)
    return out


def _themes(conn: sqlite3.Connection) -> list[str]:
    return [r["name"] for r in conn.execute(
        "SELECT t.name, COUNT(*) c FROM tags t JOIN note_tags nt ON nt.tag_id = t.id GROUP BY t.id ORDER BY c DESC LIMIT 40")]


def _candidates(conn: sqlite3.Connection, client: Any, note: dict[str, Any]) -> list[dict[str, Any]]:
    from engine.brain import meaning

    query = (note["title"] + " " + note["body"][:400]).strip()
    try:
        hits = meaning.search_notes(conn, client, query, 8)
    except Exception:
        hits = []
    return [{"id": h["id"], "title": h["title"]} for h in hits if h["id"] != note["id"]][:6]


def save_meta(conn: sqlite3.Connection, note_id: str, **fields: Any) -> None:
    now = utc_now()
    cols = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v) for k, v in fields.items()}
    exists = conn.execute("SELECT 1 FROM item_meta WHERE note_id = ?", (note_id,)).fetchone()
    if exists:
        if cols:
            sets = ", ".join(f"{k} = ?" for k in cols)
            conn.execute(f"UPDATE item_meta SET {sets}, updated_at = ? WHERE note_id = ?", (*cols.values(), now, note_id))
    else:
        cols.setdefault("origin", "typed")
        names = ", ".join(cols)
        conn.execute(f"INSERT INTO item_meta (note_id, {names}, created_at, updated_at) VALUES (?, {', '.join('?' * len(cols))}, ?, ?)",
                     (note_id, *cols.values(), now, now))


def get_meta(conn: sqlite3.Connection, note_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM item_meta WHERE note_id = ?", (note_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    for k in ("key_points", "entities", "themes", "proposal"):
        try:
            d[k] = json.loads(d[k]) if d.get(k) else ([] if k != "entities" and k != "proposal" else {})
        except ValueError:
            d[k] = []
    return d


def place_label(conn: sqlite3.Connection, space_id: str) -> str:
    row = conn.execute("SELECT name, kind FROM spaces WHERE id = ?", (space_id,)).fetchone()
    if row is None:
        return "?"
    return row["name"] if row["kind"] == "inbox" else f"{KIND_LABEL.get(row['kind'], row['kind'])} › {row['name']}"


def file_item(conn: sqlite3.Connection, client: Any, note_id: str, min_confidence: float = 0.6) -> dict[str, Any]:
    """Understands and files one item. Returns {applied, receipt, proposal, action_id, item}."""
    from engine.assistant.core import _journal, _snapshot, _usage_event, complete_with_fallback

    note = brain.get_note(conn, note_id)
    meta = get_meta(conn, note_id) or {}
    src = conn.execute("SELECT kind, uri FROM sources WHERE note_id = ?", (note_id,)).fetchone()
    working = get_context(conn)
    ctx: dict[str, Any] = {
        "item": {"title": note["title"], "content": note["body"][:6000],
                 "origin": src["kind"] if src else meta.get("origin", note.get("source", "typed")),
                 "uri": src["uri"] if src else None},
        "places": _places(conn, note_id),
        "themes": _themes(conn),
        "candidates": _candidates(conn, client, note),
    }
    if src:
        text = " ".join(r["text"] for r in conn.execute(
            "SELECT c.text FROM source_chunks c JOIN sources s ON s.id = c.source_id WHERE s.note_id = ? ORDER BY c.idx LIMIT 6",
            (note_id,)))
        ctx["item"]["original_excerpt"] = text[:8000]
    if working:
        ctx["working_context"] = working
    res = complete_with_fallback(conn, client, "assistant_classify_model",
                                 [{"role": "system", "content": SYSTEM},
                                  {"role": "user", "content": json.dumps(ctx, ensure_ascii=False)}],
                                 json_mode=True, temperature=0.1)
    _usage_event(conn, "classify", res["model"], res["usage"], client.provider)
    try:
        prop = json.loads(res["message"]["content"] or "{}")
    except ValueError:
        return {"applied": False, "reason": "unreadable proposal", "receipt": "Je n'ai pas pu lire ma propre proposition; l'élément reste dans l'Inbox."}

    valid = {p["id"] for p in ctx["places"]}
    place = prop.get("place") or {}
    new_space = place.get("new_space") if isinstance(place.get("new_space"), dict) else None
    target = place.get("space_id") if place.get("space_id") in valid else None
    if target is None and new_space and str(new_space.get("name", "")).strip():
        existing = conn.execute("SELECT id FROM spaces WHERE name = ? COLLATE NOCASE AND archived_at IS NULL",
                                (str(new_space["name"]).strip(),)).fetchone()
        if existing:
            target, new_space = existing["id"], None
    item_type = prop.get("item_type") if prop.get("item_type") in ITEM_TYPES else ("reference" if src else "note")
    themes = [t for t in (theme_name(x) for x in _json_list(prop.get("themes"), 3, 40)) if t]
    entities = prop.get("entities") if isinstance(prop.get("entities"), dict) else {}
    entities = {k: _json_list(entities.get(k), 8, 80) for k in ("people", "organizations", "concepts", "places", "dates")}
    confidence = float(prop.get("confidence") or 0)
    proposal = {
        "title": str(prop.get("title") or note["title"]).strip()[:120] or note["title"],
        "item_type": item_type, "language": str(prop.get("language") or "")[:8] or None,
        "summary": (str(prop["summary"]).strip()[:1200] if prop.get("summary") else None),
        "key_points": _json_list(prop.get("key_points"), 6, 200), "entities": entities, "themes": themes,
        "space_id": target, "new_space": ({"name": str(new_space["name"]).strip()[:80],
                                           "kind": new_space.get("kind") if new_space.get("kind") in ("project", "area", "resource") else "resource"}
                                          if new_space and target is None else None),
        "link_ids": [i for i in _json_list(prop.get("link_ids"), 3, 40) if i in {c["id"] for c in ctx["candidates"]}],
        "confidence": confidence, "question": (str(prop["question"]).strip()[:300] if prop.get("question") else None),
        "receipt": str(prop.get("receipt") or "").strip()[:400],
    }
    common = dict(item_type=item_type, language=proposal["language"], summary=proposal["summary"],
                  key_points=proposal["key_points"], entities=entities, themes=themes, confidence=confidence,
                  proposal=proposal)
    if meta.get("summary") and not proposal["summary"]:
        common["summary"] = meta["summary"]
    if src:
        common.update(origin=src["kind"], origin_uri=src["uri"])
    placeable = proposal["space_id"] is not None or proposal["new_space"] is not None
    if confidence < min_confidence or not placeable:
        q = proposal["question"] or "Où veux-tu que je le classe?"
        save_meta(conn, note_id, filed=0, question=q,
                  receipt=f"Reçu « {proposal['title']} ». Je le laisse dans l'Inbox: {q}", **common)
        return {"applied": False, "proposal": proposal, "question": q, "item": item(conn, note_id),
                "receipt": f"Reçu « {proposal['title']} ». Je le laisse dans l'Inbox: {q}"}

    before = _snapshot(conn, note_id)
    created_space = None
    if proposal["new_space"]:
        sp = brain.create_space(conn, proposal["new_space"]["name"], proposal["new_space"]["kind"], color=_next_color(conn))
        created_space = sp["id"]
        proposal["space_id"] = sp["id"]
    body = note["body"]
    new_tags = [t for t in themes if t not in note["tags"]]
    if new_tags:
        body = (body.rstrip() + "\n\n" if body.strip() else "") + " ".join("#" + t for t in new_tags)
    brain.update_note(conn, note_id, title=proposal["title"], space_id=proposal["space_id"],
                      kind=NOTE_KIND.get(item_type, "note"), body=body)
    now = utc_now()
    for other in proposal["link_ids"]:
        conn.execute("INSERT OR IGNORE INTO links (from_note, to_note, kind, created_by, created_at)"
                     " VALUES (?, ?, 'related', 'assistant', ?)", (note_id, other, now))
    where = place_label(conn, proposal["space_id"])
    receipt = proposal["receipt"] or f"« {proposal['title']} » classé dans {where}."
    if created_space and "nouvel" not in receipt.lower():
        receipt += " Nouvelle place créée."
    save_meta(conn, note_id, filed=1, question=None, receipt=receipt, **common)
    after = _snapshot(conn, note_id)
    after["created_space"] = created_space
    action_id = _journal(conn, "classify", note_id, before, after, receipt)
    return {"applied": True, "action_id": action_id, "proposal": proposal, "receipt": receipt,
            "created_space": created_space, "item": item(conn, note_id)}


def item(conn: sqlite3.Connection, note_id: str, with_body: bool = False) -> dict[str, Any]:
    """One item as the feed, the inspector and the graph's cards show it."""
    n = brain.get_note(conn, note_id)
    m = get_meta(conn, note_id) or {}
    src = conn.execute("SELECT id, kind, uri, chunks FROM sources WHERE note_id = ?", (note_id,)).fetchone()
    return {"id": n["id"], "title": n["title"], "space_id": n["space_id"], "place": place_label(conn, n["space_id"]),
            "kind": n["kind"], "tags": n.get("tags", []), "created_at": n["created_at"],
            "item_type": m.get("item_type", "note"), "origin": (src["kind"] if src else m.get("origin", n.get("source"))),
            "origin_uri": src["uri"] if src else m.get("origin_uri"), "summary": m.get("summary"),
            "key_points": m.get("key_points", []), "entities": m.get("entities", {}), "themes": m.get("themes", []),
            "language": m.get("language"), "confidence": m.get("confidence"), "filed": bool(m.get("filed", 0)),
            "question": m.get("question"), "receipt": m.get("receipt"),
            "source": dict(src) if src else None, **({"body": n["body"]} if with_body else {})}


def feed(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """The captures feed: newest items first (seed content excluded)."""
    rows = conn.execute("SELECT id FROM notes WHERE source != 'seed' ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)).fetchall()
    return [item(conn, r["id"]) for r in rows]
