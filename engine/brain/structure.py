"""PARA structure on top of the brain: areas own projects, projects have goals,
due dates and next actions (tasks), and checklists hold simple lists."""
from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import date, timedelta
from typing import Any

from engine import brain, database
from engine.events import utc_now

STATUSES = ("active", "waiting", "someday", "done")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SEED_AREAS = [  # from what the owner described; all editable
    ("Famille", "#ffd2a1", "Les gens qui comptent: horaires, activités, moments ensemble."),
    ("Santé", "#c8b6ff", "Énergie, sommeil, sport, rendez-vous."),
    ("Maison", "#a6dcff", "Le foyer: épicerie, entretien, achats."),
    ("Vision au travail", "#a9d4ff", "Développer la vision: idées, stratégie, apprentissages."),
]


def _check_date(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    if not DATE.match(str(value)):
        raise ValueError("dates use YYYY-MM-DD")
    date.fromisoformat(str(value))
    return str(value)


def seed_structure(conn: sqlite3.Connection) -> bool:
    """Creates the four starter areas and a grocery list once. Never touches existing spaces."""
    if database.get_setting(conn, "seeded_structure_v1"):
        return False
    existing = {r["name"].casefold() for r in conn.execute("SELECT name FROM spaces")}
    for name, color, why in SEED_AREAS:
        if name.casefold() not in existing:
            s = brain.create_space(conn, name, "area", color=color)
            conn.execute("UPDATE spaces SET why = ? WHERE id = ?", (why, s["id"]))
    home = next((r for r in conn.execute("SELECT id, name FROM spaces") if r["name"].casefold() == "maison"), None)
    has_groceries = any(r["name"].casefold() == "épicerie" for r in conn.execute("SELECT name FROM checklists"))
    if home and not has_groceries:
        create_checklist(conn, "Épicerie", home["id"])
    database.set_setting(conn, "seeded_structure_v1", True)
    return True


def update_space(conn: sqlite3.Connection, space_id: str, **fields: Any) -> dict[str, Any]:
    space = brain.get_space(conn, space_id)
    allowed = {"name", "kind", "color", "icon", "goal", "why", "due_date", "status", "area_id", "instructions"}
    changes = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if space["kind"] == "inbox" and ({"kind", "name"} & set(changes)):
        raise ValueError("the Inbox cannot be renamed or changed")
    if "kind" in changes and changes["kind"] not in ("project", "area", "resource", "archive"):
        raise ValueError("invalid kind")
    if "status" in changes and changes["status"] not in STATUSES:
        raise ValueError("invalid status")
    if "due_date" in changes:
        changes["due_date"] = _check_date(changes["due_date"])
    if changes.get("area_id"):
        area = brain.get_space(conn, changes["area_id"])
        if area["kind"] != "area":
            raise ValueError("a project's parent must be an area")
    if "name" in changes and not str(changes["name"]).strip():
        raise ValueError("name is empty")
    if changes:
        changes["updated_at"] = utc_now()
        sets = ", ".join(f"{k} = :{k}" for k in changes)
        conn.execute(f"UPDATE spaces SET {sets} WHERE id = :id", {**changes, "id": space_id})
    return brain.get_space(conn, space_id)


def create_project(conn: sqlite3.Connection, name: str, area_id: str | None = None, goal: str | None = None,
                   due_date: str | None = None, color: str | None = None) -> dict[str, Any]:
    s = brain.create_space(conn, name, "project", color=color)
    return update_space(conn, s["id"], area_id=area_id, goal=goal, due_date=due_date)


def _task_row(r: sqlite3.Row) -> dict[str, Any]:
    return {k: r[k] for k in r.keys()}


def tasks(conn: sqlite3.Connection, space_id: str | None = None, include_done: bool = False) -> list[dict[str, Any]]:
    sql = ("SELECT n.id, n.title, n.space_id, s.name AS space_name, n.due_date, n.status, n.done_at, n.updated_at"
           " FROM notes n JOIN spaces s ON s.id = n.space_id WHERE n.kind = 'task'")
    args: list[Any] = []
    if not include_done:
        sql += " AND n.status = 'active'"
    if space_id:
        sql += " AND n.space_id = ?"
        args.append(space_id)
    sql += " ORDER BY n.due_date IS NULL, n.due_date, n.updated_at DESC"
    return [_task_row(r) for r in conn.execute(sql, args)]


def add_task(conn: sqlite3.Connection, title: str, space_id: str | None = None, due_date: str | None = None,
             source: str = "typed") -> dict[str, Any]:
    n = brain.create_note(conn, title, "", space_id, kind="task", source=source)
    if due_date:
        conn.execute("UPDATE notes SET due_date = ? WHERE id = ?", (_check_date(due_date), n["id"]))
    return brain.get_note(conn, n["id"])


def set_task(conn: sqlite3.Connection, note_id: str, done: bool | None = None, due_date: str | None = "__keep__") -> dict[str, Any]:
    n = brain.get_note(conn, note_id)
    now = utc_now()
    if done is not None:
        conn.execute("UPDATE notes SET status = ?, done_at = ?, updated_at = ? WHERE id = ?",
                     ("done" if done else "active", now if done else None, now, note_id))
    if due_date != "__keep__":
        conn.execute("UPDATE notes SET due_date = ?, updated_at = ? WHERE id = ?", (_check_date(due_date), now, note_id))
    return brain.get_note(conn, n["id"])


# -------------------------------------------------------------- checklists
def create_checklist(conn: sqlite3.Connection, name: str, space_id: str | None = None) -> dict[str, Any]:
    if not name.strip():
        raise ValueError("name is empty")
    brain.ensure_inbox(conn)
    brain.get_space(conn, space_id or brain.INBOX_ID)
    cid = uuid.uuid4().hex[:16]
    now = utc_now()
    conn.execute("INSERT INTO checklists (id, space_id, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                 (cid, space_id or brain.INBOX_ID, name.strip(), now, now))
    return get_checklist(conn, cid)


def get_checklist(conn: sqlite3.Connection, checklist_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT c.*, s.name AS space_name FROM checklists c JOIN spaces s ON s.id = c.space_id"
                       " WHERE c.id = ?", (checklist_id,)).fetchone()
    if row is None:
        raise brain.NotFound(f"checklist {checklist_id}")
    out = dict(row)
    out["items"] = [dict(r) for r in conn.execute(
        "SELECT id, text, done, source, created_at, done_at FROM checklist_items WHERE checklist_id = ?"
        " ORDER BY done, position, id", (checklist_id,))]
    return out


def list_checklists(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [get_checklist(conn, r["id"]) for r in conn.execute("SELECT id FROM checklists ORDER BY name")]


def find_checklist(conn: sqlite3.Connection, name_or_id: str) -> dict[str, Any]:
    # SQLite's lower() ignores accents (É); compare in Python so "épicerie" finds "Épicerie".
    wanted = name_or_id.strip().casefold()
    for row in conn.execute("SELECT id, name FROM checklists"):
        if row["id"] == name_or_id or row["name"].casefold() == wanted:
            return get_checklist(conn, row["id"])
    raise brain.NotFound(f"checklist {name_or_id}")


def add_items(conn: sqlite3.Connection, checklist_id: str, texts: list[str], source: str = "typed") -> dict[str, Any]:
    cl = get_checklist(conn, checklist_id)
    have = {i["text"].lower() for i in cl["items"] if not i["done"]}
    pos = conn.execute("SELECT COALESCE(MAX(position), 0) FROM checklist_items WHERE checklist_id = ?",
                       (checklist_id,)).fetchone()[0]
    now = utc_now()
    for t in texts:
        t = t.strip()
        if not t or t.lower() in have:
            continue
        pos += 1
        have.add(t.lower())
        conn.execute("INSERT INTO checklist_items (checklist_id, text, position, source, created_at)"
                     " VALUES (?, ?, ?, ?, ?)", (checklist_id, t[:200], pos, source, now))
    conn.execute("UPDATE checklists SET updated_at = ? WHERE id = ?", (now, checklist_id))
    return get_checklist(conn, checklist_id)


def set_item(conn: sqlite3.Connection, item_id: int, done: bool | None = None, text: str | None = None) -> dict[str, Any]:
    row = conn.execute("SELECT checklist_id FROM checklist_items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise brain.NotFound(f"item {item_id}")
    if done is not None:
        conn.execute("UPDATE checklist_items SET done = ?, done_at = ? WHERE id = ?",
                     (1 if done else 0, utc_now() if done else None, item_id))
    if text is not None and text.strip():
        conn.execute("UPDATE checklist_items SET text = ? WHERE id = ?", (text.strip()[:200], item_id))
    return get_checklist(conn, row["checklist_id"])


def delete_item(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("DELETE FROM checklist_items WHERE id = ?", (item_id,))


def clear_done(conn: sqlite3.Connection, checklist_id: str) -> dict[str, Any]:
    conn.execute("DELETE FROM checklist_items WHERE checklist_id = ? AND done = 1", (checklist_id,))
    return get_checklist(conn, checklist_id)


# ------------------------------------------------------------- overviews
def structure(conn: sqlite3.Connection) -> dict[str, Any]:
    spaces = brain.list_spaces(conn)
    open_tasks: dict[str, int] = {}
    for r in conn.execute("SELECT space_id, COUNT(*) c FROM notes WHERE kind = 'task' AND status = 'active' GROUP BY space_id"):
        open_tasks[r["space_id"]] = r["c"]
    for s in spaces:
        s["open_tasks"] = open_tasks.get(s["id"], 0)
    areas = [s for s in spaces if s["kind"] == "area"]
    projects = [s for s in spaces if s["kind"] == "project"]
    for a in areas:
        a["projects"] = [p for p in projects if p.get("area_id") == a["id"]]
    return {"inbox": next((s for s in spaces if s["kind"] == "inbox"), None), "areas": areas,
            "loose_projects": [p for p in projects if not p.get("area_id")],
            "resources": [s for s in spaces if s["kind"] == "resource"],
            "archive": [s for s in spaces if s["kind"] == "archive"]}


def today(conn: sqlite3.Connection, horizon_days: int = 7) -> dict[str, Any]:
    d0 = date.today()
    soon = (d0 + timedelta(days=horizon_days)).isoformat()
    all_open = tasks(conn)
    overdue = [t for t in all_open if t["due_date"] and t["due_date"] < d0.isoformat()]
    due_today = [t for t in all_open if t["due_date"] == d0.isoformat()]
    due_soon = [t for t in all_open if t["due_date"] and d0.isoformat() < t["due_date"] <= soon]
    projects_due = [dict(r) for r in conn.execute(
        "SELECT id, name, due_date FROM spaces WHERE kind = 'project' AND status = 'active' AND due_date IS NOT NULL"
        " AND due_date <= ? ORDER BY due_date", (soon,))]
    # Next action per active project: its earliest open task
    next_actions = []
    for p in conn.execute("SELECT id, name FROM spaces WHERE kind = 'project' AND status = 'active' ORDER BY name"):
        t = tasks(conn, p["id"])
        if t:
            next_actions.append({**t[0], "project": p["name"], "remaining": len(t)})
    stuck = [dict(r) for r in conn.execute(
        "SELECT s.id, s.name FROM spaces s WHERE s.kind = 'project' AND s.status = 'active' AND NOT EXISTS"
        " (SELECT 1 FROM notes n WHERE n.space_id = s.id AND n.kind = 'task' AND n.status = 'active') ORDER BY s.name")]
    inbox = conn.execute("SELECT COUNT(*) FROM notes WHERE space_id = 'inbox' AND status = 'active'").fetchone()[0]
    return {"date": d0.isoformat(), "overdue": overdue, "today": due_today, "soon": due_soon,
            "projects_due": projects_due, "next_actions": next_actions, "projects_without_next_action": stuck,
            "inbox_count": inbox, "checklists": list_checklists(conn)}


def card(conn: sqlite3.Connection, space_id: str) -> dict[str, Any]:
    s = brain.get_space(conn, space_id)
    s["tasks"] = tasks(conn, space_id, include_done=True)[:50]
    s["notes"] = [n for n in brain.list_notes(conn, space_id, 30) if n["kind"] != "task"]
    s["decisions"] = [dict(r) for r in conn.execute(
        "SELECT n.id, n.title, n.updated_at FROM notes n JOIN note_tags nt ON nt.note_id = n.id JOIN tags t ON t.id = nt.tag_id"
        " WHERE n.space_id = ? AND t.name IN ('decision', 'décision') ORDER BY n.updated_at DESC LIMIT 20", (space_id,))]
    s["checklists"] = [get_checklist(conn, r["id"]) for r in conn.execute("SELECT id FROM checklists WHERE space_id = ?", (space_id,))]
    if s["kind"] == "area":
        s["projects"] = [dict(r) for r in conn.execute(
            "SELECT id, name, status, due_date, goal FROM spaces WHERE area_id = ? ORDER BY status, due_date", (space_id,))]
    return s
