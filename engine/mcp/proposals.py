"""What MCP clients propose (Loop MCP-B1). The archivist is the only door: a client never writes, it proposes.

- `propose_item`: an item to add. Checked here (format, size, a reason, duplicates); once applied it enters as a
  capture and the archivist files it with the user's own instructions and model (the client's suggested place is a
  hint, the archivist decides).
- `propose_change`: move, link, unlink, set fields, trash. Checked against the archivist's rules (existing places
  only, nothing erased, the item not changed since the client read it).

A trusted client's proposals are applied at once; otherwise they wait for the user's approval in the app. Either
way the client gets a receipt. Every applied action is journaled with its author, so Undo works for it too.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from collections import defaultdict, deque
from typing import Any

from engine.events import utc_now

ACTIONS = ("move", "link", "unlink", "set_fields", "trash")
PER_MINUTE = 60
PER_DAY = 500
_recent: dict[str, deque] = defaultdict(lambda: deque(maxlen=PER_DAY))


class Refused(ValueError):
    """A proposal that cannot be accepted; the message says why, in words the client can act on."""


def _rate(client_id: str) -> None:
    now = time.time()
    q = _recent[client_id]
    if sum(1 for t in q if now - t < 60) >= PER_MINUTE:
        raise Refused(f"too many proposals: at most {PER_MINUTE} a minute; wait a little")
    if sum(1 for t in q if now - t < 86400) >= PER_DAY:
        raise Refused(f"too many proposals today (at most {PER_DAY})")
    q.append(now)


def _text(v: Any, n: int) -> str:
    return str(v or "").strip()[:n]


def check_item(conn: sqlite3.Connection, args: dict[str, Any]) -> dict[str, Any]:
    from engine.brain import types
    title = _text(args.get("title"), 200)
    content = str(args.get("content") or "").strip()
    reason = _text(args.get("reason"), 500)
    missing = [k for k, v in (("title", title), ("content", content), ("reason", reason)) if not v]
    if missing:
        raise Refused("a proposal needs " + ", ".join(missing) + " (title, content, reason; source and suggested_place are optional)")
    if len(content) > 20_000:
        raise Refused("content too long (20,000 characters at most): propose a summary and give the source")
    source = _text(args.get("source"), 2000)
    if source and not re.match(r"^(https?://|file:|[A-Za-z]:\\|/)", source):
        raise Refused("source must be a web address or a file path")
    dup = next((r for r in conn.execute("SELECT id, title FROM notes WHERE status != 'archived'")
                if r["title"].casefold() == title.casefold()), None)
    if dup:
        raise Refused(f"already in the Brain: « {dup['title']} » ({dup['id']}); propose a change to it instead")
    out = {"title": title, "content": content, "reason": reason, "source": source or None,
           "suggested_place": _text(args.get("suggested_place"), 80) or None}
    if args.get("type"):
        t = types.get_type(conn, str(args["type"]))
        if t is None:
            raise Refused(f"unknown type « {args['type']} »: see item_types")
        out["type"] = t["id"]
        out["fields"] = types.clean_props(t, dict(args.get("fields") or {}))
    return out


def check_change(conn: sqlite3.Connection, args: dict[str, Any], llm: Any = None) -> dict[str, Any]:
    from engine.assistant import actions as act
    from engine.brain import types
    action = _text(args.get("action"), 20)
    if action not in ACTIONS:
        raise Refused(f"action must be one of {', '.join(ACTIONS)}")
    reason = _text(args.get("reason"), 500)
    if not reason:
        raise Refused("a change needs a reason (one sentence: why)")
    hit = act.resolve_item(conn, _text(args.get("item"), 300), llm)
    if "id" not in hit:
        raise Refused("item not found or ambiguous: pass its id (from search or get_item)")
    n = conn.execute("SELECT id, title, updated_at, source FROM notes WHERE id = ?", (hit["id"],)).fetchone()
    seen = _text(args.get("version"), 40)
    if seen and seen != n["updated_at"]:
        raise Refused(f"« {n['title']} » changed since you read it: read it again (get_item) and propose again")
    out: dict[str, Any] = {"action": action, "item": n["id"], "title": n["title"], "reason": reason, "version": n["updated_at"]}
    if action == "move":
        p = act.resolve_place(conn, _text(args.get("target"), 120))
        if p is None:
            raise Refused("move needs an existing place as target (see list_places); new places are the user's to create")
        if p["kind"] == "archive":
            raise Refused("items are not moved into the archive: propose trash if it should go")
        out["target"], out["target_name"] = p["id"], p["name"]
    elif action in ("link", "unlink"):
        other = act.resolve_item(conn, _text(args.get("target"), 300), llm)
        if "id" not in other or other["id"] == n["id"]:
            raise Refused(f"{action} needs another existing item as target")
        out["target"] = other["id"]
        out["target_name"] = conn.execute("SELECT title FROM notes WHERE id = ?", (other["id"],)).fetchone()["title"]
    elif action == "set_fields":
        current = types.get_props(conn, n["id"])
        type_id = _text(args.get("type"), 40) or (current or {}).get("type") or ""
        t = types.get_type(conn, type_id) if type_id else None
        if t is None:
            raise Refused("set_fields needs the item's type (see item_types)")
        fields = types.clean_props(t, dict(args.get("fields") or {}))
        if not fields:
            raise Refused("no valid field in this change")
        out["type"], out["fields"] = t["id"], fields
    return out


def propose(conn: sqlite3.Connection, client: dict[str, Any], kind: str, args: dict[str, Any], llm: Any = None) -> dict[str, Any]:
    """Checks a proposal; applies it now (direct client) or keeps it for the user's approval. Returns the receipt."""
    _rate(client["id"])
    payload = check_item(conn, args) if kind == "item" else check_change(conn, args, llm)
    # The same proposal sent again (a retry) while the first still waits: one proposal, not two items once approved.
    for row in conn.execute("SELECT id, payload FROM mcp_proposals WHERE client_id = ? AND kind = ? AND status = 'pending'",
                            (client["id"], kind)).fetchall():
        old = json.loads(row["payload"])
        same = (str(old.get("title", "")).casefold() == str(payload.get("title", "")).casefold()) if kind == "item" else old == payload
        if same:
            return {"proposal": row["id"], "status": "pending", "receipt": "already waiting for the user's approval "
                    "(proposal " + row["id"] + "); not proposed twice. Check later with my_proposals"}
    pid = "p" + uuid.uuid4().hex[:10]
    conn.execute("INSERT INTO mcp_proposals (id, client_id, client_name, kind, payload, status, created_at)"
                 " VALUES (?, ?, ?, ?, ?, 'pending', ?)", (pid, client["id"], client["name"], kind,
                                                           json.dumps(payload, ensure_ascii=False), utc_now()))
    direct = conn.execute("SELECT direct FROM mcp_clients WHERE id = ?", (client["id"],)).fetchone()
    if direct and direct["direct"]:
        return apply(conn, pid, llm)
    return {"proposal": pid, "status": "pending",
            "receipt": "waiting for the user's approval in the app (proposal " + pid + "); check later with my_proposals"}


def _journal_as(author: str):
    from engine.assistant import core

    def journal(conn: sqlite3.Connection, kind: str, note_id: str | None, before: Any, after: Any, reason: str) -> int:
        aid = core._journal(conn, kind, note_id, before, after, reason)
        conn.execute("UPDATE assistant_actions SET author = ? WHERE id = ?", (author, aid))
        return aid
    return journal


def apply(conn: sqlite3.Connection, pid: str, llm: Any = None, file_now: bool = True) -> dict[str, Any]:
    """Applies one proposal through the archivist; its receipt says what happened.
    file_now=False (approvals from the app): the item is created at once and the archivist files it afterwards, in the
    background (one OpenAI call each, the slow part); the result then carries « to_file »."""
    from engine import brain
    from engine.assistant import actions as act
    from engine.brain import archivist, types

    r = conn.execute("SELECT * FROM mcp_proposals WHERE id = ?", (pid,)).fetchone()
    if r is None:
        raise Refused("unknown proposal")
    if r["status"] != "pending":
        return {"proposal": pid, "status": r["status"], "receipt": r["receipt"]}
    p = json.loads(r["payload"])
    author = "mcp:" + r["client_name"]
    journal = _journal_as(author)
    done: list = []
    note_id = None
    to_file = None
    try:
        from engine.brain import timeline
        timeline.ensure_session_point(conn, author)  # a client's first write of a session: a restore point first
        if r["kind"] == "item":
            body = p["content"]
            if p.get("source"):
                body += f"\n\nSource: {p['source']}"
            from engine.assistant.core import ui_language
            en = ui_language(conn) == "en"  # these two lines are read in the item: in the app's language
            body += (f"\n\n(Proposed by {r['client_name']}: {p['reason']})" if en
                     else f"\n\n(Proposé par {r['client_name']} : {p['reason']})")
            if p.get("suggested_place"):
                body += (f"\n(Suggested place: {p['suggested_place']})" if en
                         else f"\n(Lieu suggéré : {p['suggested_place']})")
            note = brain.create_note(conn, p["title"], body, None, kind="note", source="agent")
            note_id = note["id"]
            journal(conn, "create_note", note_id, None, {"title": note["title"]}, f"proposée par {r['client_name']}")
            if p.get("type"):
                types.set_props(conn, note_id, p["type"], p.get("fields") or {}, merge=False)
            if llm is not None and not file_now:
                receipt = "added to the Inbox; the archivist is filing it"
                to_file = note_id
            elif llm is not None:
                filed = archivist.file_item(conn, llm, note_id)
                receipt = str(filed.get("receipt") or "added to the Inbox; the archivist will file it")
            else:
                receipt = "added to the Inbox (no OpenAI key: the archivist files it once one is set)"
        else:
            cur = conn.execute("SELECT updated_at FROM notes WHERE id = ?", (p["item"],)).fetchone()
            if cur is None:
                raise Refused("the item no longer exists")
            if cur["updated_at"] != p["version"]:
                raise Refused(f"« {p['title']} » changed after the proposal: propose again")
            note_id = p["item"]
            a = p["action"]
            if a == "move":
                out = act.move_items(conn, llm, journal, done, [p["item"]], p["target_name"])
                receipt = f"moved « {p['title']} » to {out.get('place', p['target_name'])}"
            elif a == "link":
                act.link_items(conn, llm, journal, done, p["item"], p["target"])
                receipt = f"linked « {p['title']} » and « {p['target_name']} »"
            elif a == "unlink":
                act.unlink_items(conn, llm, journal, done, p["item"], p["target"])
                receipt = f"unlinked « {p['title']} » and « {p['target_name']} »"
            elif a == "set_fields":
                before = types.get_props(conn, p["item"])
                types.set_props(conn, p["item"], p["type"], p["fields"], merge=True, rewrite_body=True)
                journal(conn, "set_fields", p["item"], before, types.get_props(conn, p["item"]), "champs modifiés")
                receipt = f"updated « {p['title']} »: " + ", ".join(p["fields"])
            else:
                act.trash_items(conn, llm, journal, done, [p["item"]])
                receipt = f"« {p['title']} » went to the trash (the user can undo it)"
        status = "applied"
    except Refused as exc:
        status, receipt = "failed", str(exc)
    conn.execute("UPDATE mcp_proposals SET status = ?, receipt = ?, note_id = ?, decided_at = ? WHERE id = ?",
                 (status, receipt, note_id, utc_now(), pid))
    out = {"proposal": pid, "status": status, "receipt": receipt, "item": note_id}
    if to_file and status == "applied":
        out["to_file"] = to_file
    return out


# ---------------------------------------------------------------- filing in the background (after approvals)
FILING: dict[str, Any] = {"total": 0, "done": 0, "running": False, "last": ""}


def file_later(db_path: Any, llm: Any, jobs: list[tuple[str, str]], connect: Any) -> None:
    """The archivist files approved items one by one, each in its own transaction; the proposal's receipt then says
    where it went. jobs: (proposal id, item id). Runs in a thread; FILING is what the app shows."""
    import threading

    from engine.brain import archivist

    def run() -> None:
        for pid, note_id in jobs:
            try:
                conn = connect(db_path)
                try:
                    filed = archivist.file_item(conn, llm, note_id)
                    receipt = str(filed.get("receipt") or "added to the Inbox; the archivist will file it")
                    conn.execute("UPDATE mcp_proposals SET receipt = ? WHERE id = ?", (receipt, pid))
                    conn.commit()
                    FILING["last"] = receipt
                finally:
                    conn.close()
            except Exception as exc:  # the item stays in the Inbox, never lost
                FILING["last"] = f"left in the Inbox ({str(exc)[:80]})"
            FILING["done"] += 1
        FILING["running"] = FILING["done"] < FILING["total"]

    if not jobs:
        return
    if not FILING["running"]:
        FILING.update(total=0, done=0)
    FILING["total"] += len(jobs)
    FILING["running"] = True
    threading.Thread(target=run, daemon=True, name="archivist-filing").start()


def reject(conn: sqlite3.Connection, pid: str, why: str = "") -> dict[str, Any]:
    receipt = "rejected by the user" + (f": {why}" if why else "")
    conn.execute("UPDATE mcp_proposals SET status = 'rejected', receipt = ?, decided_at = ? WHERE id = ? AND status = 'pending'",
                 (receipt, utc_now(), pid))
    return {"proposal": pid, "status": "rejected", "receipt": receipt}


def listing(conn: sqlite3.Connection, status: str = "pending", client_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    sql = "SELECT * FROM mcp_proposals WHERE 1 = 1"
    args: list[Any] = []
    if status:
        sql += " AND status = ?"
        args.append(status)
    if client_id:
        sql += " AND client_id = ?"
        args.append(client_id)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    out = []
    for r in conn.execute(sql, args):
        d = dict(r)
        d["payload"] = json.loads(d["payload"])
        out.append(d)
    return out


def summary(p: dict[str, Any]) -> str:
    """One line for the approval card."""
    x = p["payload"]
    if p["kind"] == "item":
        return f"+ « {x['title']} »" + (f" → {x['suggested_place']}" if x.get("suggested_place") else "")
    a = x["action"]
    return {"move": f"« {x['title']} » → {x.get('target_name', '')}", "link": f"« {x['title']} » ↔ « {x.get('target_name', '')} »",
            "unlink": f"« {x['title']} » ✕ « {x.get('target_name', '')} »",
            "set_fields": f"« {x['title']} » : " + ", ".join(f"{k} = {v}" for k, v in (x.get("fields") or {}).items())[:120],
            "trash": f"« {x['title']} » → corbeille"}.get(a, a)
