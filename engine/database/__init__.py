"""SQLite persistence. Stdlib only so the bootstrap can migrate before deps exist."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from engine.events import utc_now
from engine.paths import MIGRATIONS_DIR


class MigrationError(RuntimeError):
    pass


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def session(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def available_migrations(directory: Path = MIGRATIONS_DIR) -> list[tuple[int, str, Path]]:
    found = []
    for path in sorted(directory.glob("*.sql")):
        head = path.stem.split("_", 1)[0]
        if not head.isdigit():
            continue
        found.append((int(head), path.stem, path))
    versions = [v for v, _, _ in found]
    if len(versions) != len(set(versions)):
        raise MigrationError("duplicate migration version numbers")
    return found


def _checksum(path: Path) -> str:
    # Line endings are normalised: a Windows checkout with CRLF must not look
    # like an edited migration. (Same hash as before for LF files.)
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def migrate(db_path: Path, directory: Path = MIGRATIONS_DIR) -> dict[str, Any]:
    """Apply pending migrations. Idempotent; refuses edited migrations."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version INTEGER PRIMARY KEY, name TEXT NOT NULL,"
            " checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        conn.commit()
        applied = {
            row["version"]: row for row in conn.execute("SELECT * FROM schema_migrations")
        }
        newly: list[str] = []
        for version, name, path in available_migrations(directory):
            checksum = _checksum(path)
            if version in applied:
                if applied[version]["checksum"] != checksum:
                    raise MigrationError(
                        f"migration {name} changed after it was applied; add a new migration instead"
                    )
                continue
            try:
                conn.execute("BEGIN")
                # executescript would commit implicitly; run statements one by one.
                for statement in _split_sql(path.read_text(encoding="utf-8")):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, checksum, applied_at)"
                    " VALUES (?, ?, ?, ?)",
                    (version, name, checksum, utc_now()),
                )
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                raise MigrationError(f"migration {name} failed: {exc}") from exc
            newly.append(name)
        version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        return {"applied": newly, "schema_version": version or 0}
    finally:
        conn.close()


def _split_sql(script: str) -> list[str]:
    lines = [ln for ln in script.splitlines() if not ln.strip().startswith("--")]
    statements, buf = [], []
    for ln in lines:
        buf.append(ln)
        candidate = "\n".join(buf).strip()
        if candidate.endswith(";") and sqlite3.complete_statement(candidate):
            statements.append(candidate)
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def schema_version(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    with session(db_path) as conn:
        try:
            row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        except sqlite3.OperationalError:
            return 0
        return row[0] or 0


def record_event(conn: sqlite3.Connection, event: dict[str, Any]) -> None:
    details = event.get("details")
    conn.execute(
        "INSERT INTO system_events (timestamp, run_id, component, stage, status, message, progress, details)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            event["timestamp"],
            event.get("run_id"),
            event["component"],
            event["stage"],
            event["status"],
            event["message"],
            event.get("progress"),
            json.dumps(details, ensure_ascii=False) if details else None,
        ),
    )


def recent_events(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM system_events ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),)
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["details"] = json.loads(item["details"]) if item["details"] else None
        out.append(item)
    return out


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO application_settings (key, value, updated_at) VALUES (?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, json.dumps(value), utc_now()),
    )


def get_setting(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value FROM application_settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def upsert_service_status(conn: sqlite3.Connection, service: str, **fields: Any) -> None:
    allowed = {"status", "pid", "port", "started_at", "last_check_at", "message"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"unknown service_status fields: {unknown}")
    existing = conn.execute("SELECT * FROM service_status WHERE service = ?", (service,)).fetchone()
    merged = dict(existing) if existing else {"service": service, "status": "unknown"}
    merged.update(fields)
    conn.execute(
        "INSERT OR REPLACE INTO service_status (service, status, pid, port, started_at, last_check_at, message)"
        " VALUES (:service, :status, :pid, :port, :started_at, :last_check_at, :message)",
        {k: merged.get(k) for k in ("service", "status", "pid", "port", "started_at", "last_check_at", "message")},
    )


def service_statuses(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM service_status ORDER BY service")]
