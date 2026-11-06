"""Backups, restore and starting fresh (Loop 29).

Layout of a destination folder (another disk, OneDrive, a USB key; <data>/backups until one is chosen):

  <destination>/brain-<id>/
    snapshots/<UTC stamp>-<kind>/brain.sqlite3    the whole database, copied while the app runs (SQLite backup:
                                                  consistent), conversations, agents, undo history and settings
                                                  included; never the API keys (they stay in the credential store)
    snapshots/<…>/manifest.json                   what it holds: counts, checksum, schema version, originals used
    originals/<xx>/<sha256>.<ext>                 the kept files (PDFs, pages, pictures), copied ONCE: their name
                                                  is their fingerprint, so a daily backup only adds new files

Every backup is reopened and checked before it counts. Rotation keeps the newest of each of the last 7 days,
4 weeks and 6 months, the last 5 manual backups, and the safety copies of the last 30 days; files no backup uses
any more are removed.

Restoring copies the chosen backup's files back, replaces the database, and applies the newer migrations when
the backup is older. Starting fresh replaces it with a new Brain. Both take a verified backup first: no backup,
no change. The app-level state (browser pairing, bookmark key: engine/appstate.py) and the settings file stay.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from engine import VERSION, appstate, database
from engine.paths import Layout

FORMAT = "sbgd-backup"
FORMAT_VERSION = 1
KINDS = ("auto", "manual", "before-restore", "before-fresh")
DEFAULTS = {"destination": "", "every_hours": 24, "enabled": True}
KEEP_DAYS, KEEP_WEEKS, KEEP_MONTHS, KEEP_SAFETY_DAYS, KEEP_MANUAL = 7, 4, 6, 30, 5
COUNTED = ("notes", "spaces", "links", "sources", "source_images", "assistant_messages", "assistant_actions")
_LOCK = threading.Lock()  # one backup, restore or fresh start at a time


class BackupError(RuntimeError):
    pass


# ---------------------------------------------------------------- settings and places
def settings(layout: Layout) -> dict[str, Any]:
    from engine.installer.state import load_config

    out = dict(DEFAULTS)
    out.update({k: v for k, v in (load_config(layout).get("backups") or {}).items() if k in DEFAULTS})
    return out


def save_settings(layout: Layout, **changes: Any) -> dict[str, Any]:
    from engine.installer.state import atomic_write_json, load_config

    if "destination" in changes and changes["destination"]:
        dest = Path(str(changes["destination"])).expanduser()
        dest.mkdir(parents=True, exist_ok=True)
        probe = dest / ".sbgd-write-test"
        try:
            probe.write_text("ok")
            probe.unlink()
        except OSError as exc:
            raise BackupError(f"cannot write in {dest}: {exc}") from exc
        changes["destination"] = str(dest.resolve())
    if "every_hours" in changes:
        changes["every_hours"] = max(1, min(24 * 30, int(changes["every_hours"])))
    config = load_config(layout)
    config["backups"] = {**settings(layout), **{k: v for k, v in changes.items() if k in DEFAULTS}}
    atomic_write_json(layout.config_file, config)
    return settings(layout)


def brain_id(layout: Layout) -> str:
    bid = appstate.get(layout.root, "brain_id")
    if not bid:
        bid = uuid.uuid4().hex[:12]
        appstate.set(layout.root, "brain_id", bid)
    return str(bid)


def destination(layout: Layout) -> Path:
    chosen = settings(layout)["destination"]
    return Path(chosen) if chosen else layout.root / "backups"


def base_dir(layout: Layout) -> Path:
    return destination(layout) / f"brain-{brain_id(layout)}"


def same_disk(layout: Layout) -> bool:
    """True when the backups sit on the disk the Brain is on: they protect against mistakes, not a dead disk."""
    dest = destination(layout)
    probe = dest if dest.exists() else dest.parent
    try:
        return probe.resolve().anchor == layout.root.resolve().anchor and _device(probe) == _device(layout.root)
    except OSError:
        return True


def _device(path: Path) -> int:
    while not path.exists():
        path = path.parent
    return path.stat().st_dev


# ---------------------------------------------------------------- helpers
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    out = {}
    for table in COUNTED:
        try:
            out[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        except sqlite3.OperationalError:  # an older schema without that table
            out[table] = 0
    return out


def _originals_used(conn: sqlite3.Connection) -> list[str]:
    rels = {r[0] for r in conn.execute("SELECT original FROM sources WHERE original IS NOT NULL")}
    try:
        rels |= {r[0] for r in conn.execute("SELECT original FROM source_images")}
    except sqlite3.OperationalError:
        pass
    return sorted(r for r in rels if r and r.startswith("originals/") and ".." not in r)


def _copy_sqlite(src_path: Path, dst_path: Path) -> None:
    """A consistent copy of a live database (SQLite's online backup), into a new file."""
    src = sqlite3.connect(str(src_path), timeout=30)
    dst = sqlite3.connect(str(dst_path))
    try:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode = DELETE")  # one self-contained file, no -wal next to it
    finally:
        dst.close()
        src.close()


def _replace_live(layout: Layout, new_db: Path) -> None:
    """The live database takes the content of new_db, in place: the engine keeps running, its next queries
    see the new Brain."""
    src = sqlite3.connect(str(new_db), timeout=30)
    dst = sqlite3.connect(str(layout.database), timeout=30)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


# ---------------------------------------------------------------- backup
def backup(layout: Layout, kind: str = "manual") -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unknown backup kind {kind}")
    with _LOCK:
        return _backup(layout, kind)


def _backup(layout: Layout, kind: str) -> dict[str, Any]:
    started = time.monotonic()
    base = base_dir(layout)
    stamp = _now().strftime("%Y%m%dT%H%M%S%fZ")[:-4] + "Z"
    snap_id = f"{stamp}-{kind}"
    final = base / "snapshots" / snap_id
    partial = base / "snapshots" / (snap_id + ".partial")
    partial.mkdir(parents=True, exist_ok=False)
    try:
        db_copy = partial / "brain.sqlite3"
        _copy_sqlite(layout.database, db_copy)
        conn = sqlite3.connect(str(db_copy))
        try:
            counts = _counts(conn)
            used = _originals_used(conn)
            schema = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        finally:
            conn.close()
        copied = missing = 0
        total_bytes = 0
        for rel in used:
            src = layout.root / rel
            dst = base / rel
            if not src.is_file():
                missing += 1  # a file already gone from the Brain: the backup notes it, nothing to copy
                continue
            size = src.stat().st_size
            total_bytes += size
            if not dst.is_file() or dst.stat().st_size != size:
                dst.parent.mkdir(parents=True, exist_ok=True)
                tmp = dst.with_suffix(dst.suffix + ".part")
                shutil.copyfile(src, tmp)
                tmp.replace(dst)
                copied += 1
        manifest = {"format": FORMAT, "version": FORMAT_VERSION, "id": snap_id, "kind": kind,
                    "created_at": _now().strftime("%Y-%m-%dT%H:%M:%SZ"), "app_version": VERSION,
                    "schema_version": schema, "brain_id": brain_id(layout), "counts": counts,
                    "db_bytes": db_copy.stat().st_size, "db_sha256": _sha256(db_copy),
                    "originals": used, "originals_bytes": total_bytes, "originals_missing_in_brain": missing}
        (partial / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        problems = _verify(base, partial, manifest)
        if problems:
            raise BackupError("the backup did not read back correctly: " + "; ".join(problems[:3]))
        partial.replace(final)
    except Exception:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    out = {**{k: manifest[k] for k in ("id", "kind", "created_at", "counts", "db_bytes", "originals_bytes")},
           "originals": len(used), "originals_copied": copied, "seconds": round(time.monotonic() - started, 2),
           "path": str(final)}
    appstate.set(layout.root, "last_backup", {"id": snap_id, "at": manifest["created_at"], "kind": kind, "ok": True})
    rotate(layout)
    _record(layout, "ok", f"Backup {kind}: {counts['notes']} items, {len(used)} files ({copied} new), "
                          f"{out['seconds']} s → {final}", out)
    return out


def _record(layout: Layout, status: str, message: str, details: dict[str, Any] | None = None) -> None:
    from engine.events import utc_now

    try:
        with database.session(layout.database) as conn:
            database.record_event(conn, {"timestamp": utc_now(), "component": "backup", "stage": "backup",
                                         "status": status, "message": message, "details": details})
    except Exception:  # an event is never worth failing a backup
        pass


# ---------------------------------------------------------------- verify, list
def _verify(base: Path, snap: Path, manifest: dict[str, Any], deep: bool = False) -> list[str]:
    problems = []
    db = snap / "brain.sqlite3"
    if not db.is_file():
        return ["no database in the backup"]
    if db.stat().st_size != manifest.get("db_bytes") or _sha256(db) != manifest.get("db_sha256"):
        problems.append("the database file changed since it was written")
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            check = conn.execute("PRAGMA quick_check").fetchone()[0]
            if check != "ok":
                problems.append(f"database check: {check}")
            if _counts(conn) != manifest.get("counts"):
                problems.append("the database does not hold what the manifest says")
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        problems.append(f"the database cannot be read: {exc}")
    for rel in manifest.get("originals", []):
        f = base / rel
        if not f.is_file():
            if manifest.get("originals_missing_in_brain"):
                continue  # it was already missing from the Brain when the backup was taken
            problems.append(f"missing file {rel}")
        elif deep and _sha256(f) != Path(rel).stem:
            problems.append(f"damaged file {rel}")
    return problems


def _manifest(snap: Path) -> dict[str, Any] | None:
    try:
        m = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
        return m if m.get("format") == FORMAT else None
    except (OSError, ValueError):
        return None


def list_backups(layout: Layout) -> list[dict[str, Any]]:
    snaps = base_dir(layout) / "snapshots"
    out = []
    for d in sorted(snaps.glob("*"), reverse=True) if snaps.is_dir() else []:
        if d.name.endswith(".partial") or not d.is_dir():
            continue
        m = _manifest(d)
        if m:
            out.append({k: m.get(k) for k in ("id", "kind", "created_at", "schema_version", "app_version", "counts",
                                              "db_bytes", "originals_bytes")} | {"originals": len(m.get("originals", []))})
    return out


def verify(layout: Layout, snap_id: str, deep: bool = True) -> list[str]:
    base = base_dir(layout)
    snap = _snapshot_dir(base, snap_id)
    m = _manifest(snap)
    return ["not a backup"] if m is None else _verify(base, snap, m, deep=deep)


def _snapshot_dir(base: Path, snap_id: str) -> Path:
    if "/" in snap_id or "\\" in snap_id or ".." in snap_id or snap_id.endswith(".partial"):
        raise BackupError("not a backup id")
    return base / "snapshots" / snap_id


def status(layout: Layout) -> dict[str, Any]:
    last = appstate.get(layout.root, "last_backup")
    s = settings(layout)
    age_h = None
    if last and last.get("at"):
        age_h = round((_now() - datetime.strptime(last["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc))
                      .total_seconds() / 3600, 1)
    return {"settings": s, "destination": str(destination(layout)), "chosen": bool(s["destination"]),
            "same_disk": same_disk(layout), "last": last, "age_hours": age_h,
            "overdue": bool(s["enabled"]) and (age_h is None or age_h > max(48, 2 * s["every_hours"])),
            "backups": list_backups(layout)}


# ---------------------------------------------------------------- rotation
def keep_set(manifests: list[dict[str, Any]], now: datetime | None = None) -> set[str]:
    """Which backups stay: the newest of each of the last days, weeks and months, the recent safety copies,
    and always the newest one."""
    now = now or _now()
    dated = sorted(((datetime.strptime(m["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc), m)
                    for m in manifests), key=lambda t: t[0], reverse=True)
    keep: set[str] = set()
    if dated:
        keep.add(dated[0][1]["id"])
    for buckets, key_fn in ((KEEP_DAYS, lambda d: d.date()), (KEEP_WEEKS, lambda d: tuple(d.isocalendar()[:2])),
                            (KEEP_MONTHS, lambda d: (d.year, d.month))):
        seen: list[Any] = []
        for when, m in dated:
            if m["kind"].startswith("before-"):
                continue
            k = key_fn(when)
            if k not in seen:
                if len(seen) >= buckets:
                    break
                seen.append(k)
                keep.add(m["id"])
    for when, m in dated:
        if m["kind"].startswith("before-") and now - when <= timedelta(days=KEEP_SAFETY_DAYS):
            keep.add(m["id"])
    keep |= {m["id"] for _, m in dated if m["kind"] == "manual"}.intersection(
        [m["id"] for _, m in dated if m["kind"] == "manual"][:KEEP_MANUAL])  # the ones you asked for, even on the same day
    return keep


def rotate(layout: Layout) -> dict[str, int]:
    base = base_dir(layout)
    snaps = base / "snapshots"
    manifests = [m for d in snaps.glob("*") if d.is_dir() and not d.name.endswith(".partial") and (m := _manifest(d))]
    keep = keep_set(manifests)
    removed = 0
    for m in manifests:
        if m["id"] not in keep:
            shutil.rmtree(snaps / m["id"], ignore_errors=True)
            removed += 1
    used = {rel for m in manifests if m["id"] in keep for rel in m.get("originals", [])}
    files = 0
    for f in (base / "originals").rglob("*") if (base / "originals").is_dir() else []:
        if f.is_file() and f.relative_to(base).as_posix() not in used:
            f.unlink()
            files += 1
    return {"removed": removed, "files_removed": files}


# ---------------------------------------------------------------- restore, start fresh
def restore(layout: Layout, snap_id: str) -> dict[str, Any]:
    with _LOCK:
        base = base_dir(layout)
        snap = _snapshot_dir(base, snap_id)
        m = _manifest(snap)
        if m is None:
            raise BackupError("this backup does not exist")
        problems = _verify(base, snap, m, deep=True)
        if problems:
            raise BackupError("this backup is damaged, nothing was changed: " + "; ".join(problems[:3]))
        safety = _backup(layout, "before-restore")  # raises when it fails: then nothing is touched
        for rel in m.get("originals", []):
            src, dst = base / rel, layout.root / rel
            if src.is_file() and (not dst.is_file() or dst.stat().st_size != src.stat().st_size):
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
        with tempfile.TemporaryDirectory(prefix="sbgd-restore-") as tmp:  # never touch the backup itself
            work = Path(tmp) / "brain.sqlite3"
            shutil.copyfile(snap / "brain.sqlite3", work)
            database.migrate(work)  # an older backup gets the newer migrations before it becomes the Brain
            _replace_live(layout, work)
        migrated = database.migrate(layout.database)
        kept = set(m.get("originals", []))
        for f in (layout.root / "originals").rglob("*") if (layout.root / "originals").is_dir() else []:
            if f.is_file() and f.relative_to(layout.root).as_posix() not in kept:
                f.unlink()  # a file of the replaced Brain: it is in the safety copy
        _clear_caches(layout)
        _record(layout, "ok", f"Restored the backup of {m['created_at']} (safety copy {safety['id']})",
                {"restored": snap_id, "safety": safety["id"]})
        return {"restored": snap_id, "created_at": m["created_at"], "safety": safety["id"],
                "schema_version": migrated.get("schema_version"), "counts": m["counts"]}


def start_fresh(layout: Layout) -> dict[str, Any]:
    from engine.brain.seed import seed_for_app

    with _LOCK:
        safety = _backup(layout, "before-fresh")  # raises when it fails: then nothing is erased
        with tempfile.TemporaryDirectory(prefix="sbgd-fresh-") as tmp:
            new = Path(tmp) / "brain.sqlite3"
            database.migrate(new)
            with database.session(new) as conn:
                seed_for_app(conn)
            _replace_live(layout, new)
        originals = layout.root / "originals"
        removed = 0
        if originals.is_dir():  # every file is in the safety backup
            for f in originals.rglob("*"):
                if f.is_file():
                    f.unlink()
                    removed += 1
        _clear_caches(layout)
        _record(layout, "ok", f"Started fresh (safety copy {safety['id']}, {removed} files cleared)",
                {"safety": safety["id"], "files_removed": removed})
        return {"safety": safety["id"], "files_removed": removed}


def _clear_caches(layout: Layout) -> None:
    shutil.rmtree(layout.runtime / "pages", ignore_errors=True)  # rendered pages of the previous Brain


# ---------------------------------------------------------------- automatic
class Worker(threading.Thread):
    """Takes the automatic backup when the last one is older than the chosen interval (checked every 15 min,
    first a minute after the engine starts, so starting stays fast)."""

    def __init__(self, layout: Layout, first_s: float = 60.0, every_s: float = 900.0):
        super().__init__(name="backup-worker", daemon=True)
        self.layout, self.first_s, self.every_s = layout, first_s, every_s
        self.stopped = threading.Event()
        self.last: dict[str, Any] = {}

    def stop(self) -> None:
        self.stopped.set()

    def due(self) -> bool:
        s = settings(self.layout)
        if not s["enabled"]:
            return False
        st = status(self.layout)
        return st["age_hours"] is None or st["age_hours"] >= s["every_hours"]

    def run(self) -> None:
        if self.stopped.wait(self.first_s):
            return
        while not self.stopped.is_set():
            try:
                if self.due():
                    self.last = backup(self.layout, "auto")
            except Exception as exc:  # never kill the engine over a backup; the engine room shows it
                self.last = {"error": str(exc)[:300]}
                appstate.set(self.layout.root, "last_backup_error", {"at": _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                                     "error": str(exc)[:300]})
                _record(self.layout, "error", f"Automatic backup failed: {str(exc)[:200]}")
            if self.stopped.wait(self.every_s):
                return


# ---------------------------------------------------------------- one file, to move to another computer
EXPORT_PREFIX = "sbgd-backup/"
MAX_IMPORT_BYTES = 20 * 1024 ** 3      # unpacked, all files together
MAX_IMPORT_FILES = 200_000


def export_file(layout: Layout, out_dir: Path | None = None) -> dict[str, Any]:
    """A fresh backup, packed into one zip: its database, manifest and every file it uses."""
    import zipfile

    snap = backup(layout, "manual")
    base = base_dir(layout)
    m = _manifest(base / "snapshots" / snap["id"])
    out_dir = out_dir or layout.root / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"second-brain-backup-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.zip"  # local time: what the user reads
    tmp = path.with_suffix(".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        z.write(base / "snapshots" / snap["id"] / "manifest.json", EXPORT_PREFIX + "manifest.json")
        z.write(base / "snapshots" / snap["id"] / "brain.sqlite3", EXPORT_PREFIX + "brain.sqlite3")
        for rel in (m or {}).get("originals", []):
            f = base / rel
            if f.is_file():
                z.write(f, EXPORT_PREFIX + rel, compress_type=zipfile.ZIP_STORED)  # PDFs and pictures are already packed
    tmp.replace(path)
    return {"path": str(path), "bytes": path.stat().st_size, "backup": snap["id"], "counts": snap["counts"]}


def import_file(layout: Layout, path: Path) -> dict[str, Any]:
    """Reads a backup file (from another computer) into this Brain's backups, checked, ready to restore.
    Careful with what it reads: only its own entries, no path outside, sizes capped, every file must hash to
    its name, and the result is verified like any backup. Nothing of the current Brain changes here."""
    import re
    import zipfile

    allowed = re.compile(r"^sbgd-backup/(manifest\.json|brain\.sqlite3|originals/[0-9a-f]{2}/[0-9a-f]{64}\.[a-z0-9]{1,8})$")
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise BackupError(f"not a backup file: {exc}") from exc
    with z:
        infos = z.infolist()
        if len(infos) > MAX_IMPORT_FILES or sum(i.file_size for i in infos) > MAX_IMPORT_BYTES:
            raise BackupError("this backup file is too large")
        names = {i.filename for i in infos if not i.is_dir()}
        if any(not allowed.match(n) for n in names) or EXPORT_PREFIX + "manifest.json" not in names:
            raise BackupError("not a Second Brain GD backup file")
        try:
            m = json.loads(z.read(EXPORT_PREFIX + "manifest.json"))
        except ValueError as exc:
            raise BackupError("its manifest cannot be read") from exc
        if m.get("format") != FORMAT or int(m.get("version", 0)) > FORMAT_VERSION:
            raise BackupError("this backup was made by a newer version of the app: update the app first")
        base = base_dir(layout)
        snap_id = f"{str(m.get('id', 'backup'))[:24]}-imported"
        snap_id = "".join(c for c in snap_id if c.isalnum() or c in "-_")
        target = base / "snapshots" / snap_id
        if target.exists():
            return {"id": snap_id, "already": True, "created_at": m.get("created_at"), "counts": m.get("counts")}
        partial = base / "snapshots" / (snap_id + ".partial")
        shutil.rmtree(partial, ignore_errors=True)
        partial.mkdir(parents=True)
        try:
            for name in sorted(names):
                rel = name[len(EXPORT_PREFIX):]
                if rel.startswith("originals/"):
                    dst = base / rel
                    if dst.is_file():
                        continue
                    data = z.read(name)
                    if hashlib.sha256(data).hexdigest() != Path(rel).stem:
                        raise BackupError(f"a file in the backup is damaged ({Path(rel).name[:12]}…)")
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(data)
                else:
                    with z.open(name) as src, (partial / rel).open("wb") as out:
                        shutil.copyfileobj(src, out)
            m["kind"] = m.get("kind", "manual")
            problems = _verify(base, partial, m, deep=False)
            if problems:
                raise BackupError("the backup file does not read back correctly: " + "; ".join(problems[:3]))
            m["id"] = snap_id
            (partial / "manifest.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
            partial.replace(target)
        except Exception:
            shutil.rmtree(partial, ignore_errors=True)
            raise
    return {"id": snap_id, "already": False, "created_at": m.get("created_at"), "counts": m.get("counts")}
