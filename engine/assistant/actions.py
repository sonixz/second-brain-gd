"""Reliable graph actions for the assistant: find items by what the user calls them, act, and report exactly
what changed. Every change goes through the action journal (Undo), and a request that changes nothing says so,
so the model cannot report a success that did not happen.
"""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from typing import Any, Callable

from engine import brain
from engine.events import utc_now

Journal = Callable[[sqlite3.Connection, str, str | None, Any, Any, str], int]


def _norm(text: str) -> str:
    t = re.sub(r"[\u2018\u2019\u02bc'`´\u2013\u2014-]", " ", text or "")  # d’emploi = d'emploi = d emploi
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def place_name(conn: sqlite3.Connection, space_id: str | None) -> str:
    row = conn.execute("SELECT name, kind FROM spaces WHERE id = ?", (space_id,)).fetchone() if space_id else None
    if row is None:
        return "?"
    label = {"project": "Projets", "area": "Domaines", "resource": "Ressources", "inbox": ""}.get(row["kind"], "")
    return f"{label} › {row['name']}" if label else row["name"]


def describe(conn: sqlite3.Connection, note_id: str) -> dict[str, Any]:
    n = conn.execute("SELECT id, title, space_id, kind, source, status FROM notes WHERE id = ?", (note_id,)).fetchone()
    src = conn.execute("SELECT mime, pages FROM sources WHERE note_id = ?", (note_id,)).fetchone()
    what = "document" if src else ("note dictée" if n["source"] == "voice" else n["kind"])
    if src and src["mime"]:
        what = {"application/pdf": "PDF", "text/html": "page HTML"}.get(src["mime"], "image" if src["mime"].startswith("image/") else "document")
    return {"id": n["id"], "title": n["title"], "place": place_name(conn, n["space_id"]), "type": what}


def _active(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT id, title, space_id FROM notes WHERE status != 'archived'").fetchall()


def resolve_item(conn: sqlite3.Connection, ref: str, client: Any = None) -> dict[str, Any]:
    """{"id"} for one clear match, {"candidates"} when several fit, {} when nothing does."""
    ref = (ref or "").strip()
    if not ref:
        return {}
    rows = _active(conn)
    for r in rows:
        if r["id"] == ref:
            return {"id": r["id"]}
    exact = [r for r in rows if r["title"].casefold() == ref.casefold()] or [r for r in rows if _norm(r["title"]) == _norm(ref)]
    if len(exact) == 1:
        return {"id": exact[0]["id"]}
    nref = _norm(ref)
    partial = exact or [r for r in rows if nref and (nref in _norm(r["title"]) or (len(_norm(r["title"])) > 8 and _norm(r["title"]) in nref))]
    if len(partial) == 1:
        return {"id": partial[0]["id"]}
    if len(partial) > 1:
        return {"candidates": [describe(conn, r["id"]) for r in partial[:8]]}
    from engine.brain import meaning

    hits = meaning.search_notes(conn, client, ref, 3)
    if len(hits) == 1 or (hits and hits[0].get("match") == "words" and _norm(ref) in _norm(hits[0]["title"])):
        return {"id": hits[0]["id"]}
    if hits:
        return {"candidates": [describe(conn, h["id"]) for h in hits[:3]]}
    return {}


def resolve_place(conn: sqlite3.Connection, ref: str) -> dict[str, Any] | None:
    ref = (ref or "").strip()
    spaces = conn.execute("SELECT id, name, kind FROM spaces WHERE archived_at IS NULL").fetchall()
    for s in spaces:
        if s["id"] == ref:
            return dict(s)
    nref = _norm(re.sub(r"^(projets?|domaines?|ressources?|areas?|resources?)\s*[›>:]\s*", "", ref, flags=re.I))
    same = [s for s in spaces if _norm(s["name"]) == nref]
    if len(same) == 1:
        return dict(same[0])
    near = [s for s in spaces if nref and (nref in _norm(s["name"]) or _norm(s["name"]) in nref)]
    return dict(near[0]) if len(near) == 1 else None


def all_places(conn: sqlite3.Connection) -> list[str]:
    return [place_name(conn, r["id"]) for r in conn.execute("SELECT id FROM spaces WHERE archived_at IS NULL ORDER BY name")]


def _resolve_many(conn: sqlite3.Connection, refs: list[str], client: Any) -> tuple[list[str], list[str], list[dict]]:
    ids, missing, ambiguous = [], [], []
    for ref in refs:
        r = resolve_item(conn, str(ref), client)
        if r.get("id"):
            if r["id"] not in ids:
                ids.append(r["id"])
        elif r.get("candidates"):
            ambiguous.append({"asked": ref, "candidates": r["candidates"]})
        else:
            missing.append(str(ref))
    return ids, missing, ambiguous


def find_items(conn: sqlite3.Connection, client: Any, query: str = "", place: str = "", limit: int = 25) -> dict[str, Any]:
    """Items with their place and type, by words/meaning, or everything in one place (e.g. the Inbox)."""
    if place:
        p = resolve_place(conn, place)
        if p is None:
            return {"error": f"no place called « {place} »", "existing_places": all_places(conn)}
        rows = conn.execute("SELECT id FROM notes WHERE space_id = ? AND status != 'archived' ORDER BY created_at DESC LIMIT ?",
                            (p["id"], limit)).fetchall()
        items = [describe(conn, r["id"]) for r in rows]
        if query:
            q = _norm(query)
            items = [i for i in items if q in _norm(i["title"])] or items
        return {"place": place_name(conn, p["id"]), "items": items}
    from engine.brain import meaning

    hits = meaning.search_notes(conn, client, query, limit) if query.strip() else []
    return {"items": [{**describe(conn, h["id"]), "match": h.get("match")} for h in hits]}


def move_items(conn: sqlite3.Connection, client: Any, journal: Journal, actions: list, items: list[str], place: str) -> dict[str, Any]:
    p = resolve_place(conn, place)
    if p is None:
        return {"error": f"no place called « {place} »: nothing moved. Use one of the existing places, or create_project.",
                "existing_places": all_places(conn)}
    ids, missing, ambiguous = _resolve_many(conn, items, client)
    moved, already = [], []
    for nid in ids:
        n = brain.get_note(conn, nid)
        if n["space_id"] == p["id"]:
            already.append(n["title"])
            continue
        before = {k: n[k] for k in ("title", "body", "space_id", "kind", "status", "due_date")}
        brain.update_note(conn, nid, space_id=p["id"])
        conn.execute("UPDATE item_meta SET filed = 1 WHERE note_id = ?", (nid,))
        after = {**before, "space_id": p["id"]}
        aid = journal(conn, "update_note", nid, before, after, f"déplacée dans {p['name']}")
        actions.append({"action_id": aid, "kind": "move", "note_id": nid, "title": n["title"]})
        moved.append(n["title"])
    return {"place": place_name(conn, p["id"]), "moved": moved, "already_there": already, "not_found": missing,
            "ambiguous": ambiguous, "changed": len(moved)}


def _link_rows(conn: sqlite3.Connection, a: str, b: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM links WHERE (from_note = ? AND to_note = ?) OR (from_note = ? AND to_note = ?)",
                        (a, b, b, a)).fetchall()


def unlink_items(conn: sqlite3.Connection, client: Any, journal: Journal, actions: list, item: str, other: str) -> dict[str, Any]:
    ids, missing, ambiguous = _resolve_many(conn, [item, other], client)
    if missing or ambiguous or len(ids) < 2:
        return {"error": "could not identify both items", "not_found": missing, "ambiguous": ambiguous, "changed": 0}
    a, b = ids
    rows = [dict(r) for r in _link_rows(conn, a, b)]
    edited = []
    for r in rows:
        if r["kind"] == "wikilink":  # the link comes from « [[Title]] » in the text: keep the words, drop the brackets
            src = brain.get_note(conn, r["from_note"])
            target = brain.get_note(conn, r["to_note"])["title"]
            body = re.sub(r"\[\[\s*" + re.escape(target) + r"\s*\]\]", target, src["body"], flags=re.I)
            if body != src["body"]:
                edited.append({"id": src["id"], "body": src["body"]})
                brain.update_note(conn, src["id"], body=body)
    conn.execute("DELETE FROM links WHERE (from_note = ? AND to_note = ?) OR (from_note = ? AND to_note = ?)", (a, b, b, a))
    from engine.brain import connect

    dismissed = False
    x, y = sorted((a, b))
    already = conn.execute("SELECT 1 FROM related_choices WHERE a = ? AND b = ? AND choice = 'dismissed'", (x, y)).fetchone()
    if not already and conn.execute("SELECT 1 FROM note_related WHERE (owner = ? AND other = ?) OR (owner = ? AND other = ?)",
                                    (a, b, b, a)).fetchone():
        connect.choose_related(conn, a, b, "dismissed")  # a suggestion by meaning: never offered again
        dismissed = True
    ta, tb = brain.get_note(conn, a)["title"], brain.get_note(conn, b)["title"]
    if not rows and not dismissed:
        return {"changed": 0, "no_link": f"« {ta} » and « {tb} » are not linked directly. If they look connected in "
                "the graph, it is through a shared #tag or the same place.", "shared": shared_ties(conn, a, b)}
    aid = journal(conn, "unlink", a, {"links": rows, "bodies": edited, "dismissed": dismissed}, {"other": b},
                  f"lien retiré avec {tb}")
    actions.append({"action_id": aid, "kind": "unlink", "note_id": a, "title": f"{ta} ✕ {tb}"})
    return {"changed": 1, "unlinked": [ta, tb], "suggestion_dismissed": dismissed}


def shared_ties(conn: sqlite3.Connection, a: str, b: str) -> dict[str, Any]:
    tags = [r["name"] for r in conn.execute(
        "SELECT t.name FROM note_tags x JOIN note_tags y ON x.tag_id = y.tag_id JOIN tags t ON t.id = x.tag_id"
        " WHERE x.note_id = ? AND y.note_id = ?", (a, b))]
    sa, sb = (conn.execute("SELECT space_id FROM notes WHERE id = ?", (i,)).fetchone()["space_id"] for i in (a, b))
    return {"tags": tags, "same_place": place_name(conn, sa) if sa == sb else None}


def link_items(conn: sqlite3.Connection, client: Any, journal: Journal, actions: list, item: str, other: str) -> dict[str, Any]:
    ids, missing, ambiguous = _resolve_many(conn, [item, other], client)
    if missing or ambiguous or len(ids) < 2:
        return {"error": "could not identify both items", "not_found": missing, "ambiguous": ambiguous, "changed": 0}
    a, b = ids
    ta, tb = brain.get_note(conn, a)["title"], brain.get_note(conn, b)["title"]
    if _link_rows(conn, a, b):
        return {"changed": 0, "already_linked": [ta, tb]}
    conn.execute("INSERT INTO links (from_note, to_note, kind, created_by, created_at) VALUES (?, ?, 'related', 'user', ?)",
                 (a, b, utc_now()))
    aid = journal(conn, "link", a, None, {"other": b}, f"relié à {tb}")
    actions.append({"action_id": aid, "kind": "link", "note_id": a, "title": f"{ta} — {tb}"})
    return {"changed": 1, "linked": [ta, tb]}


def remove_tag(conn: sqlite3.Connection, client: Any, journal: Journal, actions: list, item: str, tag: str) -> dict[str, Any]:
    r = resolve_item(conn, item, client)
    if not r.get("id"):
        return {"error": "item not found", "candidates": r.get("candidates", []), "changed": 0}
    n = brain.get_note(conn, r["id"])
    t = tag.strip().lstrip("#")
    body = re.sub(r"(?<![\w#])#" + re.escape(t) + r"(?![\w-])", "", n["body"], flags=re.I)
    body = re.sub(r"[ \t]{2,}", " ", body).strip()
    if body == n["body"].strip():
        return {"changed": 0, "no_tag": f"« {n['title']} » has no #{t}", "tags": n.get("tags", [])}
    before = {k: n[k] for k in ("title", "body", "space_id", "kind", "status", "due_date")}
    brain.update_note(conn, n["id"], body=body)
    aid = journal(conn, "update_note", n["id"], before, {**before, "body": body}, f"#{t} retiré")
    actions.append({"action_id": aid, "kind": "untag", "note_id": n["id"], "title": f"{n['title']} −#{t}"})
    return {"changed": 1, "removed_tag": t, "item": n["title"]}


def trash_items(conn: sqlite3.Connection, client: Any, journal: Journal, actions: list, items: list[str]) -> dict[str, Any]:
    """« Supprime X »: the item leaves the graph (archived), and Undo brings it back."""
    ids, missing, ambiguous = _resolve_many(conn, items, client)
    gone = []
    for nid in ids:
        n = brain.get_note(conn, nid)
        before = {k: n[k] for k in ("title", "body", "space_id", "kind", "status", "due_date")}
        brain.update_note(conn, nid, status="archived")
        aid = journal(conn, "update_note", nid, before, {**before, "status": "archived"}, "mise à la corbeille")
        actions.append({"action_id": aid, "kind": "trash", "note_id": nid, "title": n["title"]})
        gone.append(n["title"])
    return {"trashed": gone, "not_found": missing, "ambiguous": ambiguous, "changed": len(gone)}


def remove_place(conn: sqlite3.Connection, journal: Journal, actions: list, place: str) -> dict[str, Any]:
    """« Supprime la place / le projet X »: it leaves the graph, its items go back to the Inbox; Undo restores it."""
    p = resolve_place(conn, place)
    if p is None:
        return {"error": f"no place called « {place} »", "existing_places": all_places(conn), "changed": 0}
    if p["kind"] == "inbox":
        return {"error": "the Inbox cannot be removed", "changed": 0}
    out = brain.remove_space(conn, p["id"])
    aid = journal(conn, "remove_place", p["id"], {"note_ids": out["moved_to_inbox"], "children": out["children"]},
                  {"name": out["removed"]}, f"place {out['removed']} retirée")
    actions.append({"action_id": aid, "kind": "remove_place", "note_id": None, "title": out["removed"]})
    return {"changed": 1, "removed_place": out["removed"], "items_back_in_inbox": len(out["moved_to_inbox"])}


def undo_link_action(conn: sqlite3.Connection, kind: str, note_id: str, before: Any, after: Any) -> None:
    if kind == "link":
        b = (after or {}).get("other")
        conn.execute("DELETE FROM links WHERE from_note = ? AND to_note = ? AND kind = 'related'", (note_id, b))
        return
    for e in (before or {}).get("bodies", []):
        try:
            brain.update_note(conn, e["id"], body=e["body"])
        except brain.NotFound:
            pass
    for r in (before or {}).get("links", []):
        conn.execute("INSERT OR IGNORE INTO links (from_note, to_note, kind, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
                     (r["from_note"], r["to_note"], r["kind"], r["created_by"], r["created_at"]))
    b = str((after or {}).get("other") or "")
    if (before or {}).get("dismissed"):  # the suggestion comes back too
        x, y = sorted((note_id, b))
        conn.execute("DELETE FROM related_choices WHERE a = ? AND b = ? AND choice = 'dismissed'", (x, y))


def dumps(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False)
