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


def forget_unused(conn: sqlite3.Connection, rels: list[str]) -> int:
    """Deletes kept originals that no document refers to any more (after an item is deleted)."""
    root = data_root(conn)
    gone = 0
    for rel in rels:
        if conn.execute("SELECT 1 FROM sources WHERE original = ? UNION ALL SELECT 1 FROM source_images WHERE original = ?",
                        (rel, rel)).fetchone():
            continue  # the same file is still used by another document (or kept as a page's picture)
        path = resolve(root, rel)
        if path is not None and path.is_file():
            try:
                path.unlink()
                gone += 1
            except OSError:
                pass
    return gone


def purge_orphans(conn: sqlite3.Connection) -> dict[str, int]:
    """Documents whose item was deleted before deletions cascaded (up to 2026-11-04): their passages and files go too."""
    rows = conn.execute("SELECT id, original FROM sources WHERE note_id IS NULL OR note_id NOT IN (SELECT id FROM notes)").fetchall()
    if not rows:
        return {"sources": 0, "files": 0}
    ids = [r["id"] for r in rows]
    marks = ",".join("?" * len(ids))
    pictures = [r["original"] for r in conn.execute(f"SELECT original FROM source_images WHERE source_id IN ({marks})", ids)]
    conn.execute(f"DELETE FROM source_images WHERE source_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM source_chunks WHERE source_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM sources WHERE id IN ({marks})", ids)
    files = forget_unused(conn, [r["original"] for r in rows if r["original"]] + pictures)
    return {"sources": len(ids), "files": files}
