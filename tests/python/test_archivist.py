"""Loop 9: the archivist files any item, creating places on a fresh Brain, with a receipt."""
import json
import tempfile
import unittest
from pathlib import Path

from engine import brain, database
from engine.assistant import core
from engine.assistant.llm import FakeChat
from engine.brain import archivist
from engine.brain.seed import seed_brain


class ArchivistTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "a.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_brain(self.conn)
        self.client = FakeChat()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def capture(self, title, body=""):
        return brain.create_note(self.conn, title, body)["id"]

    def test_fresh_brain_has_no_preset_areas(self):
        kinds = [r["kind"] for r in self.conn.execute("SELECT kind FROM spaces WHERE archived_at IS NULL")]
        self.assertEqual(sorted(kinds), ["inbox", "resource"])  # Inbox + Getting started only
        self.assertIn("Getting started", [s["name"] for s in brain.list_spaces(self.conn)])

    def test_files_into_a_new_place_when_none_fits(self):
        nid = self.capture("Recette de pain au levain", "Farine, eau, sel, levain. Pétrir 10 minutes.")
        out = archivist.file_item(self.conn, self.client, nid)
        self.assertTrue(out["applied"])
        self.assertTrue(out["created_space"])
        sp = brain.get_space(self.conn, out["created_space"])
        self.assertEqual((sp["name"], sp["kind"]), ("Recette", "resource"))
        self.assertIn("Ressources › Recette", out["receipt"])
        item = out["item"]
        self.assertTrue(item["filed"])
        self.assertEqual(item["place"], "Resources › Recette")  # the interface is in English; the receipt follows the item
        self.assertIn("recette", item["themes"])
        # the next related item reuses the place instead of creating another
        nid2 = self.capture("Recette de brioche", "Beurre et oeufs")
        out2 = archivist.file_item(self.conn, self.client, nid2)
        self.assertIsNone(out2["created_space"])
        self.assertEqual(out2["proposal"]["space_id"], out["created_space"])

    def test_unsure_stays_in_inbox_with_a_question(self):
        nid = self.capture("??? truc", "")
        out = archivist.file_item(self.conn, self.client, nid)
        self.assertFalse(out["applied"])
        self.assertEqual(out["question"], "C'est pour quel projet?")
        self.assertEqual(brain.get_note(self.conn, nid)["space_id"], "inbox")
        self.assertFalse(out["item"]["filed"])

    def test_working_context_guides_filing(self):
        ctx = archivist.set_context(self.conn, name="Lancement du site")
        self.assertEqual(ctx["kind"], "project")
        nid = self.capture("Choisir un hébergeur", "comparer les prix")
        out = archivist.file_item(self.conn, self.client, nid)
        self.assertEqual(out["proposal"]["space_id"], ctx["id"])
        self.assertIsNone(archivist.set_context(self.conn))
        self.assertIsNone(archivist.get_context(self.conn))

    def test_undo_restores_and_removes_the_created_place(self):
        nid = self.capture("Photographie de nuit", "ISO, pose longue")
        out = archivist.file_item(self.conn, self.client, nid)
        core.undo(self.conn, out["action_id"])
        self.assertEqual(brain.get_note(self.conn, nid)["space_id"], "inbox")
        self.assertNotIn(out["created_space"], [s["id"] for s in brain.list_spaces(self.conn)])

    def test_feed_lists_items_newest_first_without_the_guide(self):
        a = self.capture("Premier élément")
        b = self.capture("Deuxième élément")
        archivist.file_item(self.conn, self.client, b)
        feed = archivist.feed(self.conn)
        self.assertEqual([i["id"] for i in feed][:2], [b, a])
        self.assertTrue(all(i["title"] != "Bienvenue dans ton Second Brain" for i in feed))
        self.assertTrue(feed[0]["receipt"])

    def test_prompt_is_data_oriented_and_carries_the_structure(self):
        nid = self.capture("Note")
        archivist.file_item(self.conn, self.client, nid)
        system = FakeChat.last_messages[0]["content"]
        self.assertIn("AUCUNE opinion", system)
        ctx = json.loads(FakeChat.last_messages[1]["content"])
        self.assertTrue({"item", "places", "themes", "candidates"} <= set(ctx))


if __name__ == "__main__":
    unittest.main()
