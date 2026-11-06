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


def png(w=40, h=30):
    import struct
    import zlib
    raw = b"".join(b"\x00" + b"\x80\x40\x20" * w for _ in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class ImportBTests(unittest.TestCase):
    """Loop 40: pictures inside notes, Markdown links, Logseq graphs and Notion exports."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.db = self.base / "b.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_all(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def links_from(self, title):
        nid = self.conn.execute("SELECT id FROM notes WHERE title = ?", (title,)).fetchone()[0]
        return {r[0] for r in self.conn.execute(
            "SELECT n.title FROM links l JOIN notes n ON n.id = l.to_note WHERE l.from_note = ?", (nid,))}

    def test_pictures_are_attached_to_their_note(self):
        v = self.base / "Pics"
        write_vault(v, {".obsidian/app.json": "{}", "Trip.md": "Day one ![[beach.png]] and ![a map](img/map.png) ![[missing.png]] ![[doc.pdf]]",
                        "Other.md": "![[beach.png|the beach]]"})
        (v / "Attachments").mkdir()
        (v / "Attachments/beach.png").write_bytes(png())
        (v / "img").mkdir()
        (v / "img/map.png").write_bytes(png(20, 20))
        (v / "doc.pdf").write_bytes(b"%PDF-1.4")
        scan = fi.scan(self.conn, str(v))
        self.assertEqual(scan["pictures"], 3)
        out = fi.run(self.conn, str(v))
        self.assertEqual(out["pictures"], 3)
        nid = self.conn.execute("SELECT id FROM notes WHERE title = 'Trip'").fetchone()[0]
        src = self.conn.execute("SELECT id, mime, original FROM sources WHERE note_id = ?", (nid,)).fetchone()
        self.assertEqual(src["mime"], "text/markdown")
        pics = self.conn.execute("SELECT alt, mime, width FROM source_images WHERE source_id = ? ORDER BY idx", (src["id"],)).fetchall()
        self.assertEqual([(p["alt"], p["mime"], p["width"]) for p in pics], [("beach", "image/png", 40), ("a map", "image/png", 20)])
        from engine.brain import archivist
        self.assertEqual(archivist.item(self.conn, nid)["source"]["images"], 2)
        fi.run(self.conn, str(v))  # unchanged: the pictures are not attached twice
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sources WHERE note_id = ?", (nid,)).fetchone()[0], 1)
        packs.remove(self.conn, out["layer_id"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sources WHERE uri LIKE 'vault:%'").fetchone()[0], 0)

    def test_markdown_links_between_notes(self):
        v = self.base / "Foam"
        write_vault(v, {"index.md": "See [the plan](projects/plan.md) and [web](https://x.org) and [gone](nope.md).",
                        "projects/plan.md": "Back to [home](../index.md)."})
        out = fi.scan(self.conn, str(v))
        self.assertEqual((out["kind"], out["links"], out["resolved"], out["unresolved"]), ("linked", 3, 2, 1))
        fi.run(self.conn, str(v))
        self.assertEqual(self.links_from("index"), {"plan"})
        self.assertEqual(self.links_from("plan"), {"index"})
        body = self.conn.execute("SELECT body FROM notes WHERE title = 'index'").fetchone()[0]
        self.assertIn("[[plan|the plan]]", body)
        self.assertIn("[gone](nope.md)", body)

    def test_a_logseq_graph(self):
        v = self.base / "Graph"
        write_vault(v, {"logseq/config.edn": "{}",
                        "pages/Gardening.md": "tags:: hobby, [[outdoors]]\nalias:: Garden\n- Tomatoes need sun #[[summer crops]]\n- See [[Compost]]",
                        "pages/Compost.md": "- Brown and green. Used in [[Garden]]",
                        "pages/projects___house.md": "title:: projects/house\n- Roof in spring",
                        "journals/2026_11_01.md": "- Turned the [[Compost]]"})
        out = fi.scan(self.conn, str(v))
        self.assertEqual((out["kind"], out["label"], out["notes"], out["unresolved"]), ("logseq", "Logseq graph", 4, 0))
        fi.run(self.conn, str(v))
        titles = {r[0] for r in self.conn.execute("SELECT title FROM notes WHERE source = 'import'")}
        self.assertEqual(titles, {"Gardening", "Compost", "projects/house", "2026-11-01"})
        self.assertEqual(self.links_from("Compost"), {"Gardening"})  # through the alias
        self.assertEqual(self.links_from("2026-11-01"), {"Compost"})
        g = self.conn.execute("SELECT id, body, kind FROM notes WHERE title = 'Gardening'").fetchone()
        tags = {r[0] for r in self.conn.execute("SELECT t.name FROM note_tags nt JOIN tags t ON t.id = nt.tag_id WHERE nt.note_id = ?", (g["id"],))}
        self.assertEqual(tags, {"hobby", "outdoors", "summer-crops"})
        self.assertNotIn("alias::", g["body"])
        day = self.conn.execute("SELECT n.kind, s.name FROM notes n JOIN spaces s ON s.id = n.space_id WHERE n.title = '2026-11-01'").fetchone()
        self.assertEqual(tuple(day), ("journal", "Journals"))

    def test_a_notion_export(self):
        v = self.base / "Export"
        h1, h2, h3 = "a" * 32, "b" * 32, "c" * 32
        write_vault(v, {f"Home {h1}.md": f"# Home\n\nWelcome. See [Recipes](Home%20{h1}/Recipes%20{h2}.md).",
                        f"Home {h1}/Recipes {h2}.md": f"# Recipes\n\nBack [Home](../Home%20{h1}.md). [Soup](Recipes%20{h2}/Soup%20{h3}.md)",
                        f"Home {h1}/Recipes {h2}/Soup {h3}.md": "# Soup\n\nCarrots.",
                        f"Home {h1}/Recipes {h2}.csv": "Name,Tags\nSoup,winter"})
        out = fi.scan(self.conn, str(v))
        self.assertEqual((out["kind"], out["notes"], out["resolved"], out["unresolved"]), ("notion", 3, 3, 0))
        fi.run(self.conn, str(v))
        titles = {r[0] for r in self.conn.execute("SELECT title FROM notes WHERE source = 'import'")}
        self.assertEqual(titles, {"Home", "Recipes", "Soup"})
        self.assertEqual(self.links_from("Recipes"), {"Home", "Soup"})
        soup = self.conn.execute("SELECT n.body, s.name FROM notes n JOIN spaces s ON s.id = n.space_id WHERE n.title = 'Soup'").fetchone()
        self.assertEqual(soup["body"], "Carrots.")  # the repeated « # Soup » title is gone
        self.assertEqual(soup["name"], "Home")  # folders without their ids
