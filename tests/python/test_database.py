import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine import database
from engine.paths import MIGRATIONS_DIR


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "db" / "test.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_migrate_creates_required_tables(self):
        result = database.migrate(self.db)
        expected = [name for _, name, _ in database.available_migrations()]
        self.assertEqual(result["applied"], expected)
        self.assertEqual(result["schema_version"], len(expected))
        with database.session(self.db) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("application_settings", "schema_migrations", "system_events", "service_status",
                  "spaces", "notes", "links", "tags", "note_tags", "notes_fts"):
            self.assertIn(t, tables)

    def test_migrate_is_idempotent_and_keeps_data(self):
        database.migrate(self.db)
        with database.session(self.db) as conn:
            database.set_setting(conn, "k", {"a": 1})
        again = database.migrate(self.db)
        self.assertEqual(again["applied"], [])
        with database.session(self.db) as conn:
            self.assertEqual(database.get_setting(conn, "k"), {"a": 1})
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0],
                             len(database.available_migrations()))

    def test_upgrade_from_loop0_keeps_data(self):
        """An install made by Loop 0 (schema 1) upgrades in place."""
        v1 = Path(self.tmp.name) / "v1"
        v1.mkdir()
        (v1 / "0001_initial.sql").write_text((MIGRATIONS_DIR / "0001_initial.sql").read_text())
        database.migrate(self.db, v1)
        with database.session(self.db) as conn:
            database.set_setting(conn, "installed_at", "2026-11-02T00:00:00Z")
        result = database.migrate(self.db)
        self.assertIn("0002_knowledge", result["applied"])
        with database.session(self.db) as conn:
            self.assertEqual(database.get_setting(conn, "installed_at"), "2026-11-02T00:00:00Z")

    def test_edited_migration_is_refused(self):
        mig_dir = Path(self.tmp.name) / "migs"
        mig_dir.mkdir()
        src = (MIGRATIONS_DIR / "0001_initial.sql").read_text()
        (mig_dir / "0001_initial.sql").write_text(src)
        database.migrate(self.db, mig_dir)
        (mig_dir / "0001_initial.sql").write_text(src + "\n-- edited\nCREATE TABLE x (a);")
        with self.assertRaises(database.MigrationError):
            database.migrate(self.db, mig_dir)

    def test_crlf_checkout_is_not_an_edit(self):
        mig_dir = Path(self.tmp.name) / "crlf"
        mig_dir.mkdir()
        src = (MIGRATIONS_DIR / "0001_initial.sql").read_bytes().replace(b"\r\n", b"\n")
        (mig_dir / "0001_initial.sql").write_bytes(src)
        database.migrate(self.db, mig_dir)
        (mig_dir / "0001_initial.sql").write_bytes(src.replace(b"\n", b"\r\n"))
        self.assertEqual(database.migrate(self.db, mig_dir)["applied"], [])

    def test_failed_migration_rolls_back(self):
        mig_dir = Path(self.tmp.name) / "migs"
        mig_dir.mkdir()
        (mig_dir / "0001_ok.sql").write_text("CREATE TABLE a (x INTEGER);")
        (mig_dir / "0002_bad.sql").write_text("CREATE TABLE b (x INTEGER);\nTHIS IS NOT SQL;")
        with self.assertRaises(database.MigrationError):
            database.migrate(self.db, mig_dir)
        with database.session(self.db) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("a", tables)
            self.assertNotIn("b", tables)
            self.assertEqual(conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 1)

    def test_events_and_service_status(self):
        database.migrate(self.db)
        with database.session(self.db) as conn:
            database.record_event(conn, {"timestamp": "2026-01-01T00:00:00Z", "component": "c", "stage": "s",
                                         "status": "ok", "message": "m", "details": {"x": 1}})
            database.upsert_service_status(conn, "api", status="running", pid=12, port=8765)
            database.upsert_service_status(conn, "api", last_check_at="t")
            events = database.recent_events(conn, 10)
            services = database.service_statuses(conn)
        self.assertEqual(events[0]["details"], {"x": 1})
        self.assertEqual(services[0]["pid"], 12)
        self.assertEqual(services[0]["last_check_at"], "t")
        with self.assertRaises(ValueError):
            with database.session(self.db) as conn:
                database.upsert_service_status(conn, "api", bogus=1)


class EventsTests(unittest.TestCase):
    def test_event_schema(self):
        from engine.events import EventWriter

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "e.jsonl"
            w = EventWriter(path, "run1", echo=False)
            w.emit("venv", "create", "progress", "half", 0.5, extra=1)
            w.emit("venv", "create", "ok", "done")
            with self.assertRaises(ValueError):
                w.emit("venv", "x", "nope", "bad")
            w.close()
            lines = [json.loads(ln) for ln in path.read_text().splitlines()]
        self.assertEqual(len(lines), 2)
        for key in ("timestamp", "component", "stage", "status", "message", "run_id", "v"):
            self.assertIn(key, lines[0])
        self.assertEqual(lines[0]["progress"], 0.5)
        self.assertNotIn("progress", lines[1])
        self.assertTrue(lines[0]["timestamp"].endswith("Z"))


if __name__ == "__main__":
    unittest.main()
