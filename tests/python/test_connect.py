"""Loop 14: how items connect (paths), and the user's answers to related-idea suggestions."""
import tempfile
import unittest
from pathlib import Path

from engine import brain, database
from engine.assistant import core
from engine.assistant.llm import FakeChat
from engine.brain import connect, meaning
from engine.brain.seed import seed_brain


class ConnectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "c.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_brain(self.conn)
        sp = brain.create_space(self.conn, "Jardin", "resource")
        self.compost = brain.create_note(self.conn, "Compost", "Restes de cuisine #sol", sp["id"])["id"]
        self.potager = brain.create_note(self.conn, "Potager", "Tomates et basilic. Voir [[Compost]]", sp["id"])["id"]
        self.pluie = brain.create_note(self.conn, "Récupérer la pluie", "Baril #sol")["id"]
        self.lonely = brain.create_note(self.conn, "Recette", "Pain")["id"]

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_direct_link_is_the_shortest_path(self):
        out = connect.path(self.conn, self.potager, self.compost)
        self.assertTrue(out["found"])
        self.assertEqual(out["ids"], [self.potager, self.compost])
        self.assertEqual(out["steps"][0]["type"], "link")
        self.assertIn("1 étape", out["explanation"])

    def test_a_shared_theme_connects_two_items(self):
        out = connect.path(self.conn, self.pluie, self.compost)
        self.assertEqual(out["ids"], [self.pluie, "tag:sol", self.compost])
        self.assertIn("le thème #sol", out["explanation"])

    def test_items_in_different_places_with_nothing_shared_still_meet_through_places(self):
        out = connect.path(self.conn, self.lonely, self.potager)
        self.assertTrue(out["found"])  # Inbox and Jardin are both places; the route says so
        self.assertNotIn(self.lonely, out["ids"][1:])

    def test_resolve_by_title_any_case(self):
        self.assertEqual(connect.resolve(self.conn, "récupérer la PLUIE"), self.pluie)
        self.assertIsNone(connect.resolve(self.conn, ""))

    def test_kept_or_dismissed_suggestions_are_not_suggested_again(self):
        for a, b in ((self.compost, self.pluie), (self.potager, self.lonely)):
            self.conn.execute("INSERT INTO note_related (owner, other, score) VALUES (?, ?, 0.5)", (a, b))
        self.assertEqual(len(meaning.related_edges(self.conn)), 2)
        connect.choose_related(self.conn, self.compost, self.pluie, "kept")
        connect.choose_related(self.conn, self.lonely, self.potager, "dismissed")
        self.assertEqual(meaning.related_edges(self.conn), [])
        kept = self.conn.execute("SELECT kind, created_by FROM links WHERE from_note = ? AND to_note = ?",
                                 (self.compost, self.pluie)).fetchone()
        self.assertEqual(tuple(kept), ("related", "user"))
        with self.assertRaises(brain.NotFound):
            connect.choose_related(self.conn, self.compost, "nope", "kept")

    def test_by_voice(self):
        client = FakeChat()
        out = core.chat(self.conn, client, "Comment Récupérer la pluie est relié à Compost ?")
        self.assertEqual(out["ui_actions"][0]["action"], "path")
        self.assertEqual(out["ui_actions"][0]["ids"][0], self.pluie)
        self.assertIn("#sol", out["reply"])
        self.conn.execute("INSERT INTO note_related (owner, other, score) VALUES (?, ?, 0.5)", (self.compost, self.lonely))
        out = core.chat(self.conn, client, "Enlève l'idée liée avec Recette", open_note=self.compost)
        self.assertEqual(meaning.related_edges(self.conn), [])
        out = core.chat(self.conn, client, "Cherche à l'écran compost")
        self.assertEqual(out["ui_actions"], [{"action": "search", "query": "compost"}])


if __name__ == "__main__":
    unittest.main()
