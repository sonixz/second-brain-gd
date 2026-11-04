"""Originals (Loop 12): the Brain keeps a copy of every file and web page it receives.

Stored under <data>/originals/<first 2 hex>/<sha256>.<ext>, so the same file is kept once
whatever its name, and moving or deleting the file on disk never loses a source.
"""
from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path

CHUNK = 1 << 20


def data_root(conn: sqlite3.Connection) -> Path:
    """<data> folder of this database (<data>/data/second_brain.sqlite3 -> <data>). A database outside a
    data/ folder (tests, tools) keeps its originals next to itself."""
    db = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    return db.parent.parent if db.parent.name == "data" else db.parent


def _rel(digest: str, ext: str) -> str:
    ext = "".join(c for c in ext.lower().lstrip(".") if c.isalnum())[:8] or "bin"
    return f"originals/{digest[:2]}/{digest}.{ext}"


def keep_bytes(root: Path, data: bytes, ext: str) -> tuple[str, int]:
    rel = _rel(hashlib.sha256(data).hexdigest(), ext)
    target = root / rel
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(target)
    return rel, len(data)


def keep_file(root: Path, path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    rel = _rel(h.hexdigest(), path.suffix)
    target = root / rel
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        shutil.copyfile(path, tmp)
        tmp.replace(target)
    return rel, path.stat().st_size


def resolve(root: Path, rel: str | None) -> Path | None:
    """Absolute path of a kept original, only if it really is inside <data>/originals."""
    if not rel:
        return None
    p = (root / rel).resolve()
    base = (root / "originals").resolve()
    if base not in p.parents or not p.is_file():
        return None
    return p
