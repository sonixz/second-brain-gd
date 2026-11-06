"""Loop 39: importing a folder of notes (an Obsidian vault, linked notes, plain Markdown) as a layer."""
import json
import tempfile
import unittest
from pathlib import Path

from engine import brain, database
from engine.brain import packs
from engine.brain.seed import seed_all
from engine.sources import folder_import as fi

VAULT = {
    ".obsidian/app.json": "{}",
    ".trash/old.md": "# deleted",
    "Welcome.md": "Start with [[Kitchen plan]] and [[Health]]. A #Getting-Started note. #1 is not a tag.",
    "1. Projects/Kitchen/Kitchen plan.md": (
        "---\ntags: [home, renovation]\naliases:\n  - Kitchen\ncreated: 2026-03-02\ntype: idea\n"
        "summary: \"Redo the kitchen before winter\"\nurl: https://example.org/kitchen\n---\n"
        "Budget in [[Budget#Kitchen|the budget]]. See [[Areas/Health]] and [[#Steps]].\n\n## Steps\n"
        "Also [[Missing idea]] and [[Missing idea]] and ![[sketch.png]].\n```\n[[Not a link]] #nottag\n```\n"),
    "1. Projects/Kitchen/sketch.png": "png",
    "Areas/Health.md": "Knee exercises. Linked from [[Kitchen]] by alias. #health/knee",
    "Areas/Budget.md": "---\ntags: money\n---\n# Kitchen\n18 000 $ cap.",
    "Resources/Budget.md": "Another note named Budget, in Resources.",
    "Daily/2026-11-01.md": "Talked about [[Kitchen plan]].",
    "Recipes/Café — notes (v2).md": "---\nbroken: [unclosed\n  weird\n: nope\n---\nGood coffee. [[Welcome]]",
    "Recipes/report.pdf": "%PDF",
}


def write_vault(root: Path, files=VAULT):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


class FolderImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.vault = base / "MyVault"
        write_vault(self.vault)
        self.db = base / "b.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_all(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def note(self, title, layer=None):
        rows = self.conn.execute("SELECT * FROM notes WHERE title = ?" + (" AND layer_id = ?" if layer else ""),
                                 (title, layer) if layer else (title,)).fetchall()
        self.assertEqual(len(rows), 1, title)
        return dict(rows[0])

    def links_from(self, nid):
        return {r["title"] for r in self.conn.execute(
            "SELECT n.title FROM links l JOIN notes n ON n.id = l.to_note WHERE l.from_note = ?", (nid,))}

    def test_front_matter_and_links_parse(self):
        props, body, bad = fi.front_matter("---\ntags: [a, b]\naliases:\n  - X\ntitle: 'Q'\n---\nHi")
        self.assertEqual((props["tags"], props["aliases"], props["title"], body, bad), (["a", "b"], ["X"], "Q", "Hi", False))
        self.assertTrue(fi.front_matter("---\nno end\n")[2])
        self.assertEqual(fi.parse_link("Folder/Note.md#Head|shown"), ("Folder/Note", "Head", "shown"))
        self.assertEqual(fi.parse_link("Note^block"), ("Note^block", "", ""))
        self.assertEqual(fi.parse_link("Note\\|shown in a table"), ("Note", "", "shown in a table"))
        self.assertEqual(fi.parse_link("Note#^abc"), ("Note", "abc", ""))
        self.assertEqual(fi._clean_place("1. Projects"), "Projects")

    def test_scan_detects_and_counts_without_importing(self):
        out = fi.scan(self.conn, str(self.vault))
        self.assertEqual((out["kind"], out["label"]), ("obsidian", "Obsidian vault"))
        self.assertEqual(out["notes"], 7)  # .trash and .obsidian skipped
        self.assertEqual(out["unresolved"], 1)
        self.assertEqual(out["unresolved_list"], [{"target": "Missing idea", "count": 2}])
        self.assertEqual(out["embeds"], 1)
        self.assertEqual(out["documents"], 1)
        self.assertGreater(out["cost_usd"], 0)
        self.assertLess(out["cost_usd"], 0.01)
        self.assertIn({"name": "Kitchen", "kind": "project"}, out["places"])
        self.assertIn({"name": "Areas", "kind": "area"}, out["places"])
        self.assertIn({"name": "MyVault", "kind": "resource"}, out["places"])
        self.assertIn("Recipes/Café — notes (v2).md", out["malformed"])
        self.assertIsNone(out["again"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM pack_layers").fetchone()[0], 0)
        plain = Path(self.tmp.name) / "Plain"
        write_vault(plain, {"a.md": "just text", "b/c.md": "more"})
        self.assertEqual(fi.scan(self.conn, str(plain))["kind"], "markdown")
        linked = Path(self.tmp.name) / "Linked"
        write_vault(linked, {"a.md": "[[b]]", "b.md": "x"})
        self.assertEqual(fi.scan(self.conn, str(linked))["kind"], "linked")
        logseq = Path(self.tmp.name) / "Graph"
        write_vault(logseq, {"logseq/config.edn": "{}", "pages/a.md": "- x"})
        self.assertEqual(fi.scan(self.conn, str(logseq))["kind"], "logseq")
        with self.assertRaises(ValueError):
            fi.scan(self.conn, str(Path(self.tmp.name) / "nope"))

    def test_run_imports_items_places_links_and_themes_as_a_layer(self):
        out = fi.run(self.conn, str(self.vault))
        layer = out["layer_id"]
        self.assertEqual((out["created"], out["updated"], out["unchanged"]), (7, 0, 0))
        plan = self.note("Kitchen plan")
        self.assertEqual(plan["layer_id"], layer)
        self.assertEqual(plan["source"], "import")
        self.assertEqual(plan["created_at"][:10], "2026-03-02")
        self.assertEqual(plan["kind"], "idea")
        place = self.conn.execute("SELECT name, kind, layer_id FROM spaces WHERE id = ?", (plan["space_id"],)).fetchone()
        self.assertEqual(tuple(place), ("Kitchen", "project", layer))
        # [[Budget#Kitchen|the budget]] from Projects resolves to one of two « Budget » notes; [[Areas/Health]] by path
        self.assertIn("Health", self.links_from(plan["id"]))
        self.assertIn("Budget", self.links_from(plan["id"]))
        self.assertIn("[[Budget|the budget]]", plan["body"])
        self.assertIn("[[Missing idea]]", plan["body"])  # unresolved: kept as written
        self.assertIn("![[sketch.png]]", plan["body"])
        self.assertIn("#home #renovation", plan["body"])  # front-matter tags kept as a line
        self.assertEqual(self.links_from(self.note("Health")["id"]), {"Kitchen plan"})  # [[Kitchen]] is an alias
        self.assertEqual(self.links_from(self.note("Welcome")["id"]), {"Kitchen plan", "Health"})
        meta = self.conn.execute("SELECT * FROM item_meta WHERE note_id = ?", (plan["id"],)).fetchone()
        self.assertEqual(meta["summary"], "Redo the kitchen before winter")
        self.assertEqual(meta["origin_uri"], "https://example.org/kitchen")
        self.assertEqual(json.loads(meta["proposal"])["path"], "1. Projects/Kitchen/Kitchen plan.md")
        tags = {r["name"] for r in self.conn.execute(
            "SELECT t.name FROM note_tags nt JOIN tags t ON t.id = nt.tag_id WHERE nt.note_id = ?", (plan["id"],))}
        self.assertEqual(tags, {"home", "renovation"})  # not « nottag » from the code block
        welcome_tags = {r["name"] for r in self.conn.execute(
            "SELECT t.name FROM note_tags nt JOIN tags t ON t.id = nt.tag_id WHERE nt.note_id = ?", (self.note("Welcome")["id"],))}
        self.assertEqual(welcome_tags, {"getting-started"})
        daily = self.note("2026-11-01")
        self.assertEqual(daily["kind"], "journal")
        self.assertEqual(self.conn.execute("SELECT item_type FROM item_meta WHERE note_id = ?", (daily["id"],)).fetchone()[0], "journal")
        root_place = self.conn.execute("SELECT name FROM spaces WHERE id = ?", (self.note("Welcome")["space_id"],)).fetchone()[0]
        self.assertEqual(root_place, "MyVault")
        g = brain.graph(self.conn)
        self.assertIn(plan["id"], {n["id"] for n in g["nodes"]})
        # Switched off, merged or removed like a pack.
        packs.set_enabled(self.conn, layer, False)
        self.assertNotIn(plan["id"], {n["id"] for n in brain.graph(self.conn)["nodes"]})
        packs.set_enabled(self.conn, layer, True)
        self.assertEqual(packs.remove(self.conn, layer)["removed"], 7)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM notes WHERE title = 'Kitchen plan'").fetchone()[0], 0)

    def test_import_again_adds_only_what_changed(self):
        first = fi.run(self.conn, str(self.vault))
        again = fi.scan(self.conn, str(self.vault))["again"]
        self.assertEqual((again["layer_id"], again["new"], again["changed"], again["same"]), (first["layer_id"], 0, 0, 7))
        out = fi.run(self.conn, str(self.vault))
        self.assertEqual((out["layer_id"], out["created"], out["updated"], out["unchanged"]), (first["layer_id"], 0, 0, 7))
        (self.vault / "Areas/Health.md").write_text("Knee and back exercises. [[Welcome]]", encoding="utf-8")
        (self.vault / "New idea.md").write_text("Fresh. [[Missing idea]]", encoding="utf-8")
        (self.vault / "Daily/2026-11-01.md").unlink()
        out = fi.run(self.conn, str(self.vault))
        self.assertEqual((out["created"], out["updated"], out["unchanged"], out["missing_in_folder"]), (1, 1, 5, 1))
        health = self.note("Health")
        self.assertIn("back exercises", health["body"])
        self.assertEqual(self.links_from(health["id"]), {"Welcome"})
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM pack_layers").fetchone()[0], 1)

    def test_everything_to_the_inbox_when_folders_are_not_kept(self):
        out = fi.run(self.conn, str(self.vault), keep_folders=False)
        self.assertEqual(out["places"], 1)
        self.assertEqual(self.note("Kitchen plan")["space_id"], brain.INBOX_ID)
        self.assertEqual(self.conn.execute("SELECT filed FROM item_meta WHERE note_id = ?", (self.note("Kitchen plan")["id"],)).fetchone()[0], 0)

    def test_an_edit_after_import_keeps_links_and_tags(self):
        fi.run(self.conn, str(self.vault))
        plan = self.note("Kitchen plan")
        brain.update_note(self.conn, plan["id"], body=plan["body"] + "\nEdited.")
        self.assertIn("Health", self.links_from(plan["id"]))
        tags = {r["name"] for r in self.conn.execute(
            "SELECT t.name FROM note_tags nt JOIN tags t ON t.id = nt.tag_id WHERE nt.note_id = ?", (plan["id"],))}
        self.assertTrue({"home", "renovation"} <= tags)

    def test_empty_folder_and_routes(self):
        empty = Path(self.tmp.name) / "Empty"
        empty.mkdir()
        self.assertEqual(fi.scan(self.conn, str(empty))["kind"], "empty")
        with self.assertRaises(ValueError):
            fi.run(self.conn, str(empty))
        from engine.api.brain_routes import FolderIn
        self.assertTrue(FolderIn(path="C:/x").keep_folders)


if __name__ == "__main__":
    unittest.main()


class SpokenFolderTests(unittest.TestCase):
    def test_by_voice_the_named_folder_or_the_vault_obsidian_knows(self):
        import os
        from unittest import mock

        from engine.assistant import core

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "Documents/Notes").mkdir(parents=True)
            vault = home / "Vaults/Mine"
            vault.mkdir(parents=True)
            (home / "obsidian").mkdir()
            (home / "obsidian/obsidian.json").write_text(json.dumps({"vaults": {
                "a": {"path": str(home / "gone"), "ts": 9}, "b": {"path": str(vault), "ts": 5, "open": True}}}), encoding="utf-8")
            with mock.patch.object(Path, "home", return_value=home), mock.patch.dict(os.environ, {"APPDATA": str(home)}):
                self.assertEqual(fi.spoken_path("Documents/Notes"), str(home / "Documents/Notes"))
                self.assertEqual(fi.spoken_path(str(home / "Documents/Notes")), str(home / "Documents/Notes"))
                self.assertEqual(fi.spoken_path("Nowhere"), "")
                self.assertEqual(fi.obsidian_vaults(), [str(vault)])  # the missing one is left out
                self.assertEqual(fi.spoken_path("", obsidian=True), str(vault))
                self.assertEqual(fi.spoken_path(""), "")
                core._UI["actions"] = []
                act = core._ui_tool(None, "ui_import_folder", {"obsidian": True})
                self.assertEqual(core._UI["actions"][-1], {"action": "import_folder", "path": str(vault)})
                self.assertTrue(act)
