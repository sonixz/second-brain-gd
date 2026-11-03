-- 0001_initial: system tables needed by the Loop 0 foundation.
-- schema_migrations itself is created by the migration runner.

CREATE TABLE IF NOT EXISTS application_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    run_id      TEXT,
    component   TEXT NOT NULL,
    stage       TEXT NOT NULL,
    status      TEXT NOT NULL,
    message     TEXT NOT NULL,
    progress    REAL,
    details     TEXT
);
CREATE INDEX IF NOT EXISTS idx_system_events_timestamp ON system_events (timestamp);

CREATE TABLE IF NOT EXISTS service_status (
    service       TEXT PRIMARY KEY,
    status        TEXT NOT NULL,
    pid           INTEGER,
    port          INTEGER,
    started_at    TEXT,
    last_check_at TEXT,
    message       TEXT
);
