"""App-level state, outside the Brain's database (Loop 29): what must survive a restore or a fresh start.

<data>/app_state.json holds the browser pairing tokens (hashes), the pending pairing code, the bookmark's capture
key, the Brain's id and the last backup. Restoring a backup or starting fresh replaces the database; these stay,
so the browser stays paired and the bookmark keeps working.

Keys that used to live in the database's settings table move here the first time they are read.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

FILE = "app_state.json"
MOVED_FROM_DATABASE = ("browser_tokens", "browser_pair_code", "capture_key")
_LOCK = threading.RLock()


def _root(where: sqlite3.Connection | Path) -> Path:
    if isinstance(where, Path):
        return where
    from engine.sources import originals

    return originals.data_root(where)


def _read(root: Path) -> dict[str, Any]:
    try:
        data = json.loads((root / FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(root: Path, data: dict[str, Any]) -> None:
    path = root / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # holds pairing hashes: user only
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, path)


def get(where: sqlite3.Connection | Path, key: str, default: Any = None) -> Any:
    with _LOCK:
        root = _root(where)
        data = _read(root)
        if key not in data and key in MOVED_FROM_DATABASE and isinstance(where, sqlite3.Connection):
            from engine import database

            old = database.get_setting(where, key)
            if old is not None:  # first read since Loop 29: move it out of the database
                data[key] = old
                _write(root, data)
                database.set_setting(where, key, None)
        return data.get(key, default)


def set(where: sqlite3.Connection | Path, key: str, value: Any) -> None:  # noqa: A001 (mirrors get)
    with _LOCK:
        root = _root(where)
        data = _read(root)
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
        _write(root, data)
