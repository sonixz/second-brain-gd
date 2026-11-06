"""Backups, restore and starting fresh (Loop 29): everything comes back, nothing is erased without a verified
backup, damage is caught, and the browser pairing survives."""
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from engine import appstate, backups, brain, database
from engine.brain import packs
from engine.brain.seed import seed_if_empty
from engine.paths import Layout
from engine.sources import core as sources, render

SKIP = {"system_events", "schema_migrations", "sqlite_sequence"}  # each Brain logs its own backups


def picture(w=320, h=200):
    return render.png(bytes([80, 120, 200, 255]) * (w * h), w, h)


def tables(db: Path) -> dict[str, list]:
    conn = sqlite3.connect(str(db))
    try:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '%_fts%'")]
        return {n: sorted(map(repr, conn.execute(f"SELECT * FROM {n}"))) for n in names if n not in SKIP}
    finally:
        conn.close()


class Brain:
    """A throwaway Brain with a bit of everything: items, a page with a picture, a conversation, a pairing."""

    def __init__(self, root: Path, dest: Path):
        self.layout = Layout(root)
        root.mkdir(parents=True, exist_ok=True)
        database.migrate(self.layout.database)
        backups.save_settings(self.layout, destination=str(dest))

    def fill(self):
        with mock.patch.dict(os.environ, {"SBGD_OCR": "off"}), database.session(self.layout.database) as conn:
            seed_if_empty(conn)
            sp = brain.create_space(conn, "Kitchen renovation")
            brain.create_note(conn, "Quartz or butcher block", "Quartz needs no sealing.", sp["id"])
            sources.ingest_page(conn, None, "https://example.org/hp", "Heat pumps",
                                "<html><body><main>" + "<p>Heat pumps move heat.</p>" * 20 + "</main></body></html>", "",
                                None, [{"url": "https://example.org/a.png", "alt": "Diagram of the cycle", "caption": "",
                                        "data": picture()}])
            conn.execute("INSERT INTO assistant_messages (conversation, role, content, created_at) VALUES "
                         "('daily-x', 'user', 'hello', '2026-11-05T10:00:00Z')")
            appstate.set(conn, "browser_tokens", [{"id": "t1", "hash": "abc", "browser": "Edge 156"}])
            appstate.set(conn, "capture_key", "keep-me")
        return self


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"SBGD_SEED": ""})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_back_up_then_restore_into_an_empty_folder_gives_everything_back(self):
        a = Brain(self.dir / "a", self.dir / "dest").fill()
        out = backups.backup(a.layout, "manual")
        self.assertEqual(out["originals"], 2)  # the page's html and its picture
        self.assertEqual(backups.verify(a.layout, out["id"]), [])
        # another computer: an empty Brain pointing at the same backups
        b = Brain(self.dir / "b", self.dir / "dest")
        appstate.set(b.layout.root, "brain_id", backups.brain_id(a.layout))
        restored = backups.restore(b.layout, out["id"])
        self.assertTrue(restored["safety"].endswith("before-restore"))
        self.assertEqual(tables(a.layout.database), tables(b.layout.database))
        conn = sqlite3.connect(str(b.layout.database))
        rels = [r[0] for r in conn.execute("SELECT original FROM sources UNION SELECT original FROM source_images")]
        conn.close()
        for rel in rels:
            self.assertEqual((b.layout.root / rel).read_bytes(), (a.layout.root / rel).read_bytes())

    def test_a_second_backup_copies_only_new_files(self):
        a = Brain(self.dir / "a", self.dir / "dest").fill()
        first = backups.backup(a.layout, "manual")
        second = backups.backup(a.layout, "manual")
        self.assertEqual((first["originals_copied"], second["originals_copied"]), (2, 0))

    def test_start_fresh_keeps_a_verified_copy_and_the_pairing(self):
        a = Brain(self.dir / "a", self.dir / "dest").fill()
        res = backups.start_fresh(a.layout)
        self.assertEqual(backups.verify(a.layout, res["safety"]), [])
        conn = sqlite3.connect(str(a.layout.database))
        titles = [r[0] for r in conn.execute("SELECT title FROM notes")]
        conn.close()
        self.assertNotIn("Quartz or butcher block", titles)
        self.assertFalse([f for f in (a.layout.root / "originals").rglob("*") if f.is_file()])
        self.assertEqual(appstate.get(a.layout.root, "capture_key"), "keep-me")  # the bookmark still works
        self.assertEqual(appstate.get(a.layout.root, "browser_tokens")[0]["browser"], "Edge 156")
        # and the old Brain comes back from that safety copy
        backups.restore(a.layout, res["safety"])
        conn = sqlite3.connect(str(a.layout.database))
        self.assertIn("Quartz or butcher block", [r[0] for r in conn.execute("SELECT title FROM notes")])
        conn.close()

    def test_no_backup_no_erase(self):
        a = Brain(self.dir / "a", self.dir / "dest").fill()
        before = tables(a.layout.database)
        with mock.patch.object(backups, "_verify", return_value=["simulated: the disk is full"]):
            with self.assertRaises(backups.BackupError):
                backups.start_fresh(a.layout)
        self.assertEqual(tables(a.layout.database), before)
        self.assertEqual(backups.list_backups(a.layout), [])  # the failed copy left nothing behind

    def test_a_damaged_backup_is_caught_and_never_restored(self):
        a = Brain(self.dir / "a", self.dir / "dest").fill()
        out = backups.backup(a.layout, "manual")
        snap = backups.base_dir(a.layout) / "snapshots" / out["id"]
        with (snap / "brain.sqlite3").open("r+b") as fh:
            fh.seek(200)
            fh.write(b"\x00garbage\x00")
        self.assertTrue(backups.verify(a.layout, out["id"]))
        before = tables(a.layout.database)
        with self.assertRaises(backups.BackupError):
            backups.restore(a.layout, out["id"])
        self.assertEqual(tables(a.layout.database), before)

    def test_a_missing_file_is_caught(self):
        a = Brain(self.dir / "a", self.dir / "dest").fill()
        out = backups.backup(a.layout, "manual")
        f = next(p for p in (backups.base_dir(a.layout) / "originals").rglob("*") if p.is_file())
        f.unlink()
        self.assertTrue(any("missing file" in p for p in backups.verify(a.layout, out["id"])))

    def test_an_older_backup_gets_the_newer_migrations(self):
        old_dir = self.dir / "migrations-12"
        shutil.copytree(database.MIGRATIONS_DIR if hasattr(database, "MIGRATIONS_DIR") else
                        Path(database.__file__).parent / "migrations", old_dir)
        newest = sorted(old_dir.glob("*.sql"))[-1]
        newest.unlink()
        a = Brain(self.dir / "a", self.dir / "dest")
        a.layout.database.unlink()
        for suffix in ("-wal", "-shm"):
            Path(str(a.layout.database) + suffix).unlink(missing_ok=True)
        old_version = database.migrate(a.layout.database, old_dir)["schema_version"]
        out = backups.backup(a.layout, "manual")
        database.migrate(a.layout.database)
        res = backups.restore(a.layout, out["id"])
        self.assertGreater(res["schema_version"], old_version)
        self.assertEqual(database.schema_version(a.layout.database), res["schema_version"])

    def test_rotation_keeps_days_weeks_months_and_recent_safety_copies(self):
        now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
        fake = []
        for d in range(200):  # one automatic backup a day for 200 days
            when = now - timedelta(days=d)
            fake.append({"id": f"auto-{d}", "kind": "auto", "created_at": when.strftime("%Y-%m-%dT%H:%M:%SZ")})
        fake.append({"id": "safety-recent", "kind": "before-fresh", "created_at": (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")})
        fake.append({"id": "safety-old", "kind": "before-restore", "created_at": (now - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")})
        keep = backups.keep_set(fake, now)
        self.assertTrue({f"auto-{d}" for d in range(7)} <= keep)
        self.assertIn("safety-recent", keep)
        self.assertNotIn("safety-old", keep)
        self.assertNotIn("auto-199", keep)
        self.assertLessEqual(len(keep), 7 + 4 + 6 + 1)

    def test_files_no_backup_uses_any_more_are_removed(self):
        a = Brain(self.dir / "a", self.dir / "dest").fill()
        out = backups.backup(a.layout, "manual")
        stray = backups.base_dir(a.layout) / "originals" / "zz" / ("0" * 64 + ".png")
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_bytes(b"x")
        backups.rotate(a.layout)
        self.assertFalse(stray.exists())
        self.assertEqual(backups.verify(a.layout, out["id"]), [])

    def test_the_automatic_backup_runs_when_due(self):
        a = Brain(self.dir / "a", self.dir / "dest").fill()
        w = backups.Worker(a.layout)
        self.assertTrue(w.due())
        backups.backup(a.layout, "auto")
        self.assertFalse(w.due())
        backups.save_settings(a.layout, enabled=False)
        self.assertFalse(w.due())

    def test_the_status_tells_when_backups_share_the_brains_disk(self):
        a = Brain(self.dir / "a", self.dir / "dest")
        st = backups.status(a.layout)
        self.assertTrue(st["same_disk"])
        self.assertTrue(st["overdue"])

    def test_a_backup_id_cannot_reach_outside_the_backups(self):
        a = Brain(self.dir / "a", self.dir / "dest")
        with self.assertRaises(backups.BackupError):
            backups.restore(a.layout, "../../etc")


class AppStateTests(unittest.TestCase):
    def test_pairing_moves_out_of_the_database_on_first_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "data" / "second_brain.sqlite3"
            db.parent.mkdir()
            database.migrate(db)
            with database.session(db) as conn:
                database.set_setting(conn, "capture_key", "old-key")
                self.assertEqual(appstate.get(conn, "capture_key"), "old-key")
                self.assertIsNone(database.get_setting(conn, "capture_key"))
            self.assertEqual(json.loads((Path(tmp) / "app_state.json").read_text())["capture_key"], "old-key")


class PackPictureTests(unittest.TestCase):
    def test_a_pages_pictures_travel_in_its_pack(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"SBGD_OCR": "off", "SBGD_SEED": ""}):
            a = Brain(Path(tmp) / "a", Path(tmp) / "dest").fill()
            out = packs.export(a.layout.database, {"all": True}, Path(tmp) / "out", "Everything")
            b = Brain(Path(tmp) / "b", Path(tmp) / "dest")
            packs.import_pack(b.layout.database, Path(out["path"]))
            conn = sqlite3.connect(str(b.layout.database))
            rels = [r[0] for r in conn.execute("SELECT original FROM source_images")]
            conn.close()
            self.assertEqual(len(rels), 1)
            self.assertTrue((b.layout.root / rels[0]).is_file())
