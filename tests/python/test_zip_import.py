"""Loop 37: a .zip of notes (a vault, a GitHub download, a Notion export) imported like a folder, safely."""
import io
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from engine import database
from engine.brain.seed import seed_all
from engine.sources import folder_import as fi
from engine.sources import zip_import as zi
from tests.python.test_folder_import import VAULT


def make_zip(path: Path, files: dict, prefix: str = "") -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, text in files.items():
            z.writestr(prefix + rel, text)
    return path


class ZipImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / "data").mkdir()
        self.db = self.base / "data" / "second_brain.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_all(self.conn)
        self.downloads = self.base / "Downloads"
        self.downloads.mkdir()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_a_github_zip_of_a_vault_imports_like_the_folder(self):
        z = make_zip(self.downloads / "my-vault-main.zip", VAULT, prefix="my-vault-main/")
        before = z.read_bytes()
        scan = fi.scan(self.conn, str(z))
        self.assertEqual(scan["kind"], "obsidian")
        self.assertEqual(scan["name"], "my-vault")
        self.assertEqual(scan["zip"]["name"], "my-vault-main.zip")
        self.assertFalse(scan["inner"])
        self.assertEqual(scan["notes"], 7)
        self.assertTrue(scan["path"].startswith(str(self.base / "imports" / "zips")))
        rep = fi.run(self.conn, str(z))
        self.assertEqual(rep["created"], 7)
        self.assertEqual(z.read_bytes(), before, "the download is never changed")
        self.assertEqual(list(self.downloads.iterdir()), [z], "nothing is unpacked next to the download")
        again = fi.scan(self.conn, str(z))
        self.assertEqual(again["again"]["same"], 7, "the same zip again finds its layer")
        self.assertEqual(fi.run(self.conn, str(z))["created"], 0)

    def test_unsafe_members_are_refused_and_nothing_leaves_the_folder(self):
        z = self.downloads / "evil.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("notes/Good.md", "A good note.")
            zf.writestr("../escaped.md", "should not exist")
            zf.writestr("/abs.md", "absolute")
            zf.writestr("C:/win.md", "drive")
            zf.writestr("notes/../../up.md", "up")
            zf.writestr("run.exe", "MZ")
            link = zipfile.ZipInfo("notes/link.md")
            link.external_attr = (0o120777 << 16)
            zf.writestr(link, "/etc/passwd")
        scan = fi.scan(self.conn, str(z))
        self.assertEqual(scan["notes"], 1)
        self.assertEqual(scan["zip"]["refused"], 5)
        self.assertFalse((self.base / "escaped.md").exists())
        self.assertFalse((self.base / "imports" / "escaped.md").exists())
        self.assertFalse(any(p.name in ("up.md", "run.exe", "link.md") for p in self.base.rglob("*")))

    def test_a_zip_bomb_stops_at_the_limit(self):
        z = self.downloads / "bomb.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("big.md", "0" * 3_000_000)
        old = zi.MAX_FILE
        zi.MAX_FILE = 1_000_000
        try:
            with self.assertRaises(fi.ImportError_) as cm:
                fi.scan(self.conn, str(z))
        finally:
            zi.MAX_FILE = old
        self.assertIn("bigger than", str(cm.exception))
        self.assertFalse(any((self.base / "imports" / "zips").iterdir()), "a refused zip leaves nothing behind")

    def test_a_notion_export_with_zips_inside(self):
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as zf:
            zf.writestr("Home 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d.md", "# Home\nSee [Recipes](Recipes%204d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a.md)")
            zf.writestr("Recipes 4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a.md", "# Recipes\nPaella.")
        outer = self.downloads / "Export-123.zip"
        with zipfile.ZipFile(outer, "w") as zf:
            zf.writestr("Export-123-Part-1.zip", inner.getvalue())
        scan = fi.scan(self.conn, str(outer))
        self.assertEqual(scan["kind"], "notion")
        self.assertEqual(scan["notes"], 2)
        self.assertEqual(scan["resolved"], 1)

    def test_underscore_file_names_are_titles_with_spaces(self):
        z = make_zip(self.downloads / "srd-main.zip", {
            "07_Spells/Spells_Each/Detect_Magic.md": "### Detect Magic\nSee [[Dispel Magic]].",
            "07_Spells/Spells_Each/Dispel_Magic.md": "### Dispel Magic\nAfter [[Detect_Magic]].",
        }, prefix="srd-main/")
        scan = fi.scan(self.conn, str(z))
        self.assertEqual(scan["name"], "srd")
        self.assertEqual((scan["resolved"], scan["links"]), (2, 2))
        self.assertEqual([p["name"] for p in scan["places"]], ["Spells"])
        fi.run(self.conn, str(z))
        titles = {r["title"] for r in self.conn.execute("SELECT title FROM notes WHERE source = 'import'")}
        self.assertEqual(titles, {"Detect Magic", "Dispel Magic"})

    def test_not_a_zip_and_damaged_zip(self):
        bad = self.downloads / "fake.zip"
        bad.write_text("not a zip")
        with self.assertRaises(fi.ImportError_):
            fi.scan(self.conn, str(bad))

    def test_old_unpacked_folders_are_swept(self):
        z = make_zip(self.downloads / "a.zip", {"Note.md": "x"})
        fi.scan(self.conn, str(z))
        zips = self.base / "imports" / "zips"
        old = next(zips.iterdir())
        stale = time.time() - zi.KEEP_S - 60
        import os
        os.utime(old, (stale, stale))
        fi.scan(self.conn, str(make_zip(self.downloads / "b.zip", {"Other.md": "y"})))
        self.assertFalse(old.exists())
        self.assertEqual(len(list(zips.iterdir())), 1)

    def test_a_zip_named_by_voice_in_downloads(self):
        z = make_zip(self.downloads / "vault.zip", {"Note.md": "x"})
        import os
        home = os.environ.get("HOME"), os.environ.get("USERPROFILE")
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(self.base)
        try:
            self.assertEqual(fi.spoken_path("vault.zip"), str(z))
        finally:
            for k, v in zip(("HOME", "USERPROFILE"), home):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
