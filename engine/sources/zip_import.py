"""A .zip of notes (Loop 37): a vault, a GitHub download or a Notion export, imported like a folder.

The zip is unpacked into the app's own folder (<data>/imports/zips/<key>/), never next to the download, then
the folder import reads it as usual. Only notes, pictures, documents and the few files that tell what the folder
is (.obsidian, logseq) come out; nothing is run. A member whose path would leave that folder (« ../ », a drive,
an absolute path) or that is a link is refused. Sizes are counted while unpacking, not trusted from the zip's
header, so a « zip bomb » stops at the limit. Zips inside the zip (Notion splits big exports) are unpacked once.
Unpacked folders are removed after a day; the same zip at the same place unpacks to the same folder, so
importing it again updates the same layer.
"""
from __future__ import annotations

import hashlib
import shutil
import stat
import time
import zipfile
from pathlib import Path, PurePosixPath

MAX_TOTAL = 1_000_000_000      # bytes unpacked, all files together
MAX_FILE = 200_000_000         # one file
MAX_MEMBERS = 60_000
KEEP_S = 86_400                # unpacked folders older than this are removed
CHUNK = 1 << 20


class ZipRefused(ValueError):
    """The zip cannot be imported; the message says why, in plain words."""


def _wanted(name: str) -> bool:
    from engine.sources.folder_import import ATTACH_SUFFIXES, DOC_SUFFIXES

    p = PurePosixPath(name)
    suf = p.suffix.lower()
    if any(part in (".obsidian", "logseq") for part in p.parts[:-1]):
        return suf in (".json", ".edn", ".css")
    return suf in {".md", ".markdown", ".zip"} | ATTACH_SUFFIXES | DOC_SUFFIXES


def _safe_parts(name: str) -> tuple[str, ...] | None:
    """The member's path as safe parts under the target, or None when it would leave it."""
    n = name.replace("\\", "/")
    if n.startswith("/") or (len(n) > 1 and n[1] == ":"):
        return None
    parts = tuple(p for p in n.split("/") if p not in ("", "."))
    if not parts or any(p == ".." or ":" in p for p in parts):
        return None
    return parts


class _Budget:
    def __init__(self) -> None:
        self.total = 0
        self.members = 0


def _unpack(zf: zipfile.ZipFile, target: Path, budget: _Budget, depth: int) -> int:
    """Unpacks the wanted members of zf into target. Returns how many members were refused as unsafe."""
    refused = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        budget.members += 1
        if budget.members > MAX_MEMBERS:
            raise ZipRefused(f"more than {MAX_MEMBERS} files in this zip")
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            refused += 1
            continue
        parts = _safe_parts(info.filename)
        if parts is None:
            refused += 1
            continue
        if not _wanted(info.filename):
            continue
        dest = target.joinpath(*parts)
        if target.resolve() not in dest.resolve().parents:
            refused += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with zf.open(info) as src, open(dest, "wb") as out:
            while True:
                block = src.read(CHUNK)
                if not block:
                    break
                written += len(block)
                budget.total += len(block)
                if written > MAX_FILE:
                    raise ZipRefused(f"a file in this zip is bigger than {MAX_FILE // 1_000_000} MB: {info.filename}")
                if budget.total > MAX_TOTAL:
                    raise ZipRefused(f"this zip holds more than {MAX_TOTAL // 1_000_000_000} GB once unpacked")
                out.write(block)
        if dest.suffix.lower() == ".zip":
            if depth >= 1:
                dest.unlink()
                continue
            inner_dir = dest.with_suffix("")
            try:
                with zipfile.ZipFile(dest) as inner:
                    refused += _unpack(inner, inner_dir, budget, depth + 1)
            except zipfile.BadZipFile:
                pass
            dest.unlink()
    return refused


def _sweep(base: Path) -> None:
    if not base.is_dir():
        return
    now = time.time()
    for d in base.iterdir():
        try:
            if d.is_dir() and now - d.stat().st_mtime > KEEP_S:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def unpack(zip_path: Path, data_root: Path) -> tuple[Path, int]:
    """(the folder to import, members refused as unsafe). The folder is named after the zip; a zip that holds a
    single folder (a GitHub download: « repo-main/ ») gives that folder."""
    if not zipfile.is_zipfile(zip_path):
        raise ZipRefused("this file is not a zip")
    base = data_root / "imports" / "zips"
    _sweep(base)
    key = hashlib.sha256(str(zip_path.resolve()).casefold().encode("utf-8")).hexdigest()[:16]
    target = base / key / (zip_path.stem.strip() or "zip")
    if target.parent.exists():
        shutil.rmtree(target.parent, ignore_errors=True)
    target.mkdir(parents=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            refused = _unpack(zf, target, _Budget(), 0)
    except zipfile.BadZipFile as exc:
        shutil.rmtree(target.parent, ignore_errors=True)
        raise ZipRefused("this zip is damaged") from exc
    except ZipRefused:
        shutil.rmtree(target.parent, ignore_errors=True)
        raise
    root = target
    kids = [k for k in root.iterdir() if not k.name.startswith(".")]
    if len(kids) == 1 and kids[0].is_dir() and not (root / ".obsidian").is_dir():
        root = kids[0]  # one folder at the top (« repo-main/ »): that one; its own subfolders stay places
    return root, refused
