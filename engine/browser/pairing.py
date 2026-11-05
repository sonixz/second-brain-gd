"""Pairing an extension: a short one-time code shown in the app becomes a dedicated, revocable browser token.

Only hashes are stored. A code lives 10 minutes, works once, and dies after 5 wrong attempts.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
from typing import Any

from engine import database
from engine.events import utc_now

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L
CODE_TTL_S = 600
MAX_ATTEMPTS = 5


class PairingError(ValueError):
    pass


def _h(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _norm(code: str) -> str:
    return "".join(c for c in (code or "").upper() if c.isalnum())


def start(conn: sqlite3.Connection) -> dict[str, Any]:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(8))
    database.set_setting(conn, "browser_pair_code", {"hash": _h(raw), "expires": time.time() + CODE_TTL_S, "attempts": 0})
    return {"code": f"{raw[:4]}-{raw[4:]}", "expires_in": CODE_TTL_S}


def complete(conn: sqlite3.Connection, code: str, browser: str = "") -> str:
    pending = database.get_setting(conn, "browser_pair_code")
    if not isinstance(pending, dict) or time.time() > float(pending.get("expires", 0)):
        database.set_setting(conn, "browser_pair_code", None)
        raise PairingError("no pairing code is active: open the app and ask for a new one")
    if not secrets.compare_digest(_h(_norm(code)), str(pending.get("hash"))):
        pending["attempts"] = int(pending.get("attempts", 0)) + 1
        database.set_setting(conn, "browser_pair_code", None if pending["attempts"] >= MAX_ATTEMPTS else pending)
        raise PairingError("wrong code")
    database.set_setting(conn, "browser_pair_code", None)  # one use
    token = secrets.token_urlsafe(32)
    tokens = [t for t in (database.get_setting(conn, "browser_tokens") or []) if isinstance(t, dict)]
    tokens.append({"id": secrets.token_hex(4), "hash": _h(token), "browser": browser[:80], "created_at": utc_now(),
                   "last_seen": None})
    database.set_setting(conn, "browser_tokens", tokens[-5:])  # a few browsers at most (Edge, Chrome, a laptop)
    return token


def verify(conn: sqlite3.Connection, token: str) -> dict[str, Any] | None:
    if not token:
        return None
    h = _h(token)
    for t in database.get_setting(conn, "browser_tokens") or []:
        if isinstance(t, dict) and secrets.compare_digest(h, str(t.get("hash"))):
            return t
    return None


def paired(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [{k: t.get(k) for k in ("id", "browser", "created_at")} for t in database.get_setting(conn, "browser_tokens") or []
            if isinstance(t, dict)]


def revoke_all(conn: sqlite3.Connection) -> int:
    n = len(database.get_setting(conn, "browser_tokens") or [])
    database.set_setting(conn, "browser_tokens", [])
    database.set_setting(conn, "browser_pair_code", None)
    return n
