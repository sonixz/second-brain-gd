"""The timeline of changes and restore points (Loop MCP-B2): who changed what and when (you through the assistant,
the archivist, an agent, an MCP client), named moments to come back to, and « go back to this moment »: every
journaled action after it undone, newest first, for everyone or for one author. An item edited since is reported
as a conflict and left as it is, never overwritten silently. Nothing is erased: an item created after the moment
goes to the trash.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any

from engine import brain
from engine.events import utc_now

SESSION_GAP_S = 6 * 3600   # a client writing again after this long starts a new session (a new automatic point)
_pending_backups: list[str] = []  # clients whose new session asks for a backup once the transaction is committed

KIND_WORDS = {"create_note": "created", "add_task": "created a task", "update_note": "changed", "classify": "filed",
              "link": "linked", "unlink": "unlinked", "remove_place": "removed a place", "to_checklist": "added to a checklist",
              "mission_saved": "saved a mission", "create_project": "created a project", "set_fields": "changed fields",
              "complete_task": "completed a task", "web_page": "added a page"}


def author_of(row: Any) -> str:
    a = row["author"] if "author" in row.keys() else None
    return a or "assistant"


def entries(conn: sqlite3.Connection, author: str = "", limit: int = 200) -> list[dict[str, Any]]:
    """Actions and restore points, newest first."""
    sql = ("SELECT a.id, a.kind, a.note_id, a.reason, a.created_at, a.undone_at, a.author, n.title FROM assistant_actions a"
           " LEFT JOIN notes n ON n.id = a.note_id")
    args: list[Any] = []
    if author == "assistant":
        sql += " WHERE a.author IS NULL"
    elif author:
        sql += " WHERE a.author = ?"
        args.append(author)
    sql += " ORDER BY a.id DESC LIMIT ?"
    args.append(limit)
    out: list[dict[str, Any]] = []
    for r in conn.execute(sql, args):
        out.append({"type": "action", "id": r["id"], "kind": r["kind"], "what": KIND_WORDS.get(r["kind"], r["kind"]),
                    "title": r["title"] or "", "note_id": r["note_id"], "reason": r["reason"], "at": r["created_at"],
                    "undone": bool(r["undone_at"]), "author": author_of(r)})
    oldest = out[-1]["id"] if out else 0
    for p in conn.execute("SELECT * FROM restore_points WHERE action_id >= ? ORDER BY created_at DESC LIMIT 50", (max(0, oldest - 1),)):
        out.append({"type": "point", "id": p["id"], "name": p["name"], "action_id": p["action_id"], "at": p["created_at"],
                    "auto": bool(p["auto"]), "author": p["author"]})
    out.sort(key=lambda e: (e["at"], 0 if e["type"] == "point" else 1), reverse=True)
    return out[:limit]


def authors(conn: sqlite3.Connection) -> list[str]:
    names = [r[0] for r in conn.execute("SELECT DISTINCT author FROM assistant_actions WHERE author IS NOT NULL ORDER BY author")]
    return ["assistant"] + names


def last_action(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COALESCE(MAX(id), 0) FROM assistant_actions").fetchone()[0])


def create_point(conn: sqlite3.Connection, name: str, auto: bool = False, author: str | None = None) -> dict[str, Any]:
    pid = "r" + uuid.uuid4().hex[:10]
    name = " ".join(str(name or "").split())[:80] or "Point de retour"
    conn.execute("INSERT INTO restore_points (id, name, action_id, auto, author, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 (pid, name, last_action(conn), 1 if auto else 0, author, utc_now()))
    return dict(conn.execute("SELECT * FROM restore_points WHERE id = ?", (pid,)).fetchone())


def ensure_session_point(conn: sqlite3.Connection, author: str) -> bool:
    """Before a client's first write of a session: an automatic restore point (and a full backup once committed)."""
    last = conn.execute("SELECT created_at FROM assistant_actions WHERE author = ? ORDER BY id DESC LIMIT 1", (author,)).fetchone()
    if last:
        import calendar
        try:
            when = calendar.timegm(time.strptime(last["created_at"][:19], "%Y-%m-%dT%H:%M:%S"))  # stored in UTC
            if time.time() - when < SESSION_GAP_S:
                return False
        except ValueError:
            pass
    who = author.split(":", 1)[-1]
    create_point(conn, f"Avant les changements de {who}", auto=True, author=author)
    _pending_backups.append(author)
    return True


def take_pending_backups() -> list[str]:
    out = list(_pending_backups)
    _pending_backups.clear()
    return out


def _conflict(conn: sqlite3.Connection, row: Any) -> str | None:
    """The item was changed after this action (by someone else, or by hand): say so instead of overwriting it."""
    after = json.loads(row["after"]) if row["after"] else None
    if row["kind"] in ("update_note", "classify", "complete_task") and isinstance(after, dict) and row["note_id"]:
        n = conn.execute("SELECT * FROM notes WHERE id = ?", (row["note_id"],)).fetchone()
        if n is None:
            return "the item no longer exists"
        for k in ("title", "body", "space_id", "status"):
            if k in after and n[k] != after[k]:
                return f"« {n['title']} » was changed since ({k})"
    if row["kind"] == "set_fields" and row["note_id"]:
        from engine.brain import types
        now = types.get_props(conn, row["note_id"])
        if isinstance(after, dict) and now != after:
            return "its fields were changed since"
    return None


def undo_one(conn: sqlite3.Connection, row: Any) -> None:
    """Undo one journaled action; a created item goes to the trash (never erased)."""
    from engine.assistant import core
    from engine.brain import types
    if row["kind"] in ("create_note", "add_task") and row["note_id"]:
        try:
            brain.update_note(conn, row["note_id"], status="archived")
        except brain.NotFound:
            pass
        conn.execute("UPDATE assistant_actions SET undone_at = ? WHERE id = ?", (utc_now(), row["id"]))
    elif row["kind"] == "set_fields" and row["note_id"]:
        before = json.loads(row["before"]) if row["before"] else None
        if before:
            types.set_props(conn, row["note_id"], before["type"], before["props"], merge=False, rewrite_body=True)
        else:
            conn.execute("DELETE FROM item_props WHERE note_id = ?", (row["note_id"],))
        conn.execute("UPDATE assistant_actions SET undone_at = ? WHERE id = ?", (utc_now(), row["id"]))
    else:
        core.undo(conn, row["id"])


def rewind(conn: sqlite3.Connection, after_action: int, author: str = "") -> dict[str, Any]:
    """Undo every action after `after_action` (newest first), for everyone or one author. Conflicts are left as they
    are and listed."""
    sql = "SELECT * FROM assistant_actions WHERE id > ? AND undone_at IS NULL"
    args: list[Any] = [after_action]
    if author == "assistant":
        sql += " AND author IS NULL"
    elif author:
        sql += " AND author = ?"
        args.append(author)
    undone, conflicts = 0, []
    for row in conn.execute(sql + " ORDER BY id DESC", args).fetchall():
        why = _conflict(conn, row)
        if why:
            conflicts.append({"action": row["id"], "why": why})
            continue
        try:
            undo_one(conn, row)
            undone += 1
        except Exception as exc:  # one action that cannot be undone does not stop the others
            conflicts.append({"action": row["id"], "why": f"could not be undone ({exc.__class__.__name__})"})
    return {"undone": undone, "conflicts": conflicts}


def rewind_to_point(conn: sqlite3.Connection, point_id: str, author: str = "") -> dict[str, Any]:
    p = conn.execute("SELECT * FROM restore_points WHERE id = ?", (point_id,)).fetchone()
    if p is None:
        raise brain.NotFound(f"restore point {point_id}")
    return {**rewind(conn, int(p["action_id"]), author), "point": p["name"]}
