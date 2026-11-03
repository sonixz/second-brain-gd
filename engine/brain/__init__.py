"""The second brain: spaces, notes, links, tags, search, graph, briefing.

Pure functions over a sqlite3 connection (stdlib only), used by the API.
Links come from [[wikilinks]] in note bodies; tags from #hashtags.
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from typing import Any

from engine import database
from engine.events import utc_now

WIKILINK = re.compile(r"\[\[([^\[\]\n|]{1,200})(?:\|[^\[\]\n]*)?\]\]")
HASHTAG = re.compile(r"(?:(?<=\s)|^)#([\w][\w/-]{0,48})", re.UNICODE)
INBOX_ID = "inbox"
KINDS = ("note", "idea", "task", "journal", "reference")
SPACE_KINDS = ("inbox", "project", "area", "resource", "archive")


class NotFound(LookupError):
    pass


def _id() -> str:
    return uuid.uuid4().hex[:16]


# ------------------------------------------------------------------ spaces
def ensure_inbox(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM spaces WHERE id = ?", (INBOX_ID,)).fetchone() is None:
        now = utc_now()
        conn.execute("INSERT INTO spaces (id, name, kind, color, icon, position, created_at, updated_at)"
                     " VALUES (?, 'Inbox', 'inbox', '#9cc8ff', 'inbox', 0, ?, ?)", (INBOX_ID, now, now))


def list_spaces(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT s.*, (SELECT COUNT(*) FROM notes n WHERE n.space_id = s.id AND n.status != 'archived') AS note_count"
        " FROM spaces s WHERE s.archived_at IS NULL ORDER BY s.position, s.created_at").fetchall()
    return [dict(r) for r in rows]


def create_space(conn: sqlite3.Connection, name: str, kind: str = "project", color: str | None = None,
                 icon: str | None = None) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise ValueError("space name is empty")
    if kind not in SPACE_KINDS or kind == "inbox":
        raise ValueError(f"invalid space kind {kind!r}")
    now = utc_now()
    pos = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM spaces").fetchone()[0]
    sid = _id()
    conn.execute("INSERT INTO spaces (id, name, kind, color, icon, position, created_at, updated_at)"
                 " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (sid, name, kind, color, icon, pos, now, now))
    return get_space(conn, sid)


def get_space(conn: sqlite3.Connection, space_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM spaces WHERE id = ?", (space_id,)).fetchone()
    if row is None:
        raise NotFound(f"space {space_id}")
    return dict(row)


# ------------------------------------------------------------------- notes
def _note_row(conn: sqlite3.Connection, note_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if row is None:
        raise NotFound(f"note {note_id}")
    return row


def get_note(conn: sqlite3.Connection, note_id: str) -> dict[str, Any]:
    note = dict(_note_row(conn, note_id))
    note["tags"] = [r[0] for r in conn.execute(
        "SELECT t.name FROM tags t JOIN note_tags nt ON nt.tag_id = t.id WHERE nt.note_id = ? ORDER BY t.name",
        (note_id,))]
    note["links_out"] = [dict(r) for r in conn.execute(
        "SELECT n.id, n.title FROM links l JOIN notes n ON n.id = l.to_note WHERE l.from_note = ? ORDER BY n.title",
        (note_id,))]
    note["links_in"] = [dict(r) for r in conn.execute(
        "SELECT n.id, n.title FROM links l JOIN notes n ON n.id = l.from_note WHERE l.to_note = ? ORDER BY n.title",
        (note_id,))]
    return note


def list_notes(conn: sqlite3.Connection, space_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    sql = ("SELECT id, space_id, title, kind, source, status, pinned, created_at, updated_at,"
           " substr(body, 1, 160) AS excerpt FROM notes WHERE status != 'archived'")
    args: list[Any] = []
    if space_id:
        sql += " AND space_id = ?"
        args.append(space_id)
    sql += " ORDER BY pinned DESC, updated_at DESC LIMIT ?"
    args.append(max(1, min(limit, 1000)))
    return [dict(r) for r in conn.execute(sql, args)]


def create_note(conn: sqlite3.Connection, title: str, body: str = "", space_id: str | None = None,
                kind: str = "note", source: str = "typed") -> dict[str, Any]:
    title = title.strip()
    if not title:
        raise ValueError("note title is empty")
    if kind not in KINDS:
        raise ValueError(f"invalid note kind {kind!r}")
    ensure_inbox(conn)
    space_id = space_id or INBOX_ID
    get_space(conn, space_id)
    now = utc_now()
    nid = _id()
    conn.execute("INSERT INTO notes (id, space_id, title, body, kind, source, created_at, updated_at)"
                 " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (nid, space_id, title[:300], body, kind, source, now, now))
    _sync_links_and_tags(conn, nid)
    _link_incoming(conn, nid, title)
    return get_note(conn, nid)


def update_note(conn: sqlite3.Connection, note_id: str, **fields: Any) -> dict[str, Any]:
    _note_row(conn, note_id)
    allowed = {"title", "body", "space_id", "kind", "status", "pinned", "due_date"}
    changes = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if "title" in changes:
        changes["title"] = str(changes["title"]).strip()[:300]
        if not changes["title"]:
            raise ValueError("note title is empty")
    if "space_id" in changes:
        get_space(conn, changes["space_id"])
    if "kind" in changes and changes["kind"] not in KINDS:
        raise ValueError("invalid kind")
    if "pinned" in changes:
        changes["pinned"] = 1 if changes["pinned"] else 0
    if "status" in changes:
        changes["done_at"] = utc_now() if changes["status"] == "done" else None
    if changes:
        changes["updated_at"] = utc_now()
        sets = ", ".join(f"{k} = :{k}" for k in changes)
        conn.execute(f"UPDATE notes SET {sets} WHERE id = :id", {**changes, "id": note_id})
        if "body" in changes or "title" in changes:
            _sync_links_and_tags(conn, note_id)
        if "title" in changes:
            _link_incoming(conn, note_id, changes["title"])
    return get_note(conn, note_id)


def delete_note(conn: sqlite3.Connection, note_id: str) -> None:
    _note_row(conn, note_id)
    conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))


def _sync_links_and_tags(conn: sqlite3.Connection, note_id: str) -> None:
    row = _note_row(conn, note_id)
    body = row["body"] or ""
    targets = {m.group(1).strip().lower() for m in WIKILINK.finditer(body)}
    conn.execute("DELETE FROM links WHERE from_note = ? AND kind = 'wikilink'", (note_id,))
    now = utc_now()
    for title in targets:
        hit = conn.execute("SELECT id FROM notes WHERE lower(title) = ? AND id != ? ORDER BY created_at LIMIT 1",
                           (title, note_id)).fetchone()
        if hit:
            conn.execute("INSERT OR IGNORE INTO links (from_note, to_note, kind, created_by, created_at)"
                         " VALUES (?, ?, 'wikilink', 'user', ?)", (note_id, hit["id"], now))
    conn.execute("DELETE FROM note_tags WHERE note_id = ?", (note_id,))
    for tag in {m.group(1).lower() for m in HASHTAG.finditer(body)}:
        conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
        tag_id = conn.execute("SELECT id FROM tags WHERE name = ?", (tag,)).fetchone()[0]
        conn.execute("INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)", (note_id, tag_id))
    conn.execute("DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM note_tags)")


def _link_incoming(conn: sqlite3.Connection, note_id: str, title: str) -> None:
    """Notes that already wrote [[title]] before this note existed now link to it."""
    pattern = f"%[[{title.strip()}%"
    for row in conn.execute("SELECT id FROM notes WHERE id != ? AND body LIKE ? COLLATE NOCASE",
                            (note_id, pattern)).fetchall():
        _sync_links_and_tags(conn, row["id"])


# ------------------------------------------------------------------ search
def search(conn: sqlite3.Connection, query: str, limit: int = 30) -> list[dict[str, Any]]:
    from engine.brain.meaning import keywords

    words = keywords(query)
    if not words:
        return []
    rows = _fts_notes(conn, " ".join(f'"{w}"*' for w in words), limit)
    if not rows and len(words) > 1:  # every word did not match: any word, best first
        rows = _fts_notes(conn, " OR ".join(f'"{w}"*' for w in words), limit)
    return rows


def _fts_notes(conn: sqlite3.Connection, fts_query: str, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT n.id, n.space_id, n.title, n.kind, n.updated_at,"
        " snippet(notes_fts, 1, '[', ']', '…', 12) AS snippet, bm25(notes_fts, 4.0, 1.0) AS score"
        " FROM notes_fts JOIN notes n ON n.rowid = notes_fts.rowid"
        " WHERE notes_fts MATCH ? AND n.status != 'archived' ORDER BY score LIMIT ?",
        (fts_query, max(1, min(limit, 200)))).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------- graph
def graph(conn: sqlite3.Connection) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for s in list_spaces(conn):
        nodes.append({"id": f"space:{s['id']}", "type": "space", "label": s["name"], "kind": s["kind"],
                      "color": s["color"], "weight": s["note_count"], "status": s.get("status")})
        if s.get("area_id"):
            edges.append({"from": f"space:{s['id']}", "to": f"space:{s['area_id']}", "type": "area"})
    degree: dict[str, int] = {}
    for r in conn.execute("SELECT from_note, to_note FROM links"):
        edges.append({"from": r["from_note"], "to": r["to_note"], "type": "link"})
        degree[r["from_note"]] = degree.get(r["from_note"], 0) + 1
        degree[r["to_note"]] = degree.get(r["to_note"], 0) + 1
    for n in conn.execute("SELECT id, space_id, title, kind, source, pinned, created_at, updated_at FROM notes"
                          " WHERE status != 'archived'"):
        nodes.append({"id": n["id"], "type": "note", "label": n["title"], "kind": n["kind"], "space_id": n["space_id"],
                      "source": n["source"], "pinned": bool(n["pinned"]), "created_at": n["created_at"],
                      "updated_at": n["updated_at"], "weight": degree.get(n["id"], 0)})
        edges.append({"from": n["id"], "to": f"space:{n['space_id']}", "type": "space"})
    for t in conn.execute("SELECT t.id, t.name, COUNT(*) AS c FROM tags t JOIN note_tags nt ON nt.tag_id = t.id"
                          " JOIN notes n ON n.id = nt.note_id AND n.status != 'archived' GROUP BY t.id"):
        nodes.append({"id": f"tag:{t['name']}", "type": "tag", "label": f"#{t['name']}", "weight": t["c"]})
    for r in conn.execute("SELECT nt.note_id, t.name FROM note_tags nt JOIN tags t ON t.id = nt.tag_id"
                          " JOIN notes n ON n.id = nt.note_id AND n.status != 'archived'"):
        edges.append({"from": r["note_id"], "to": f"tag:{r['name']}", "type": "tag"})
    from engine.brain.meaning import related_edges

    edges.extend(related_edges(conn))
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------- briefing
def briefing(conn: sqlite3.Connection) -> dict[str, Any]:
    """'What's new since my last visit?' Records this visit."""
    previous = database.get_setting(conn, "last_visit_at")
    since = previous or "1970-01-01T00:00:00Z"
    created = [dict(r) for r in conn.execute(
        "SELECT id, title, space_id, source, created_at FROM notes WHERE created_at > ? AND status != 'archived'"
        " ORDER BY created_at DESC LIMIT 20", (since,))]
    updated = [dict(r) for r in conn.execute(
        "SELECT id, title, space_id, updated_at FROM notes WHERE updated_at > ? AND created_at <= ?"
        " AND status != 'archived' ORDER BY updated_at DESC LIMIT 20", (since, since))]
    totals = {
        "notes": conn.execute("SELECT COUNT(*) FROM notes WHERE status != 'archived'").fetchone()[0],
        "links": conn.execute("SELECT COUNT(*) FROM links").fetchone()[0],
        "spaces": conn.execute("SELECT COUNT(*) FROM spaces WHERE archived_at IS NULL").fetchone()[0],
        "tags": conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0],
        "inbox": conn.execute("SELECT COUNT(*) FROM notes WHERE space_id = ? AND status = 'active'",
                              (INBOX_ID,)).fetchone()[0],
    }
    recent = [dict(r) for r in conn.execute(
        "SELECT id, title, space_id, updated_at FROM notes WHERE status != 'archived'"
        " ORDER BY updated_at DESC LIMIT 5")]
    database.set_setting(conn, "last_visit_at", utc_now())
    return {"previous_visit_at": previous, "created": created, "updated": updated, "totals": totals,
            "recent": recent}
