import tempfile
import unittest
from pathlib import Path

from engine import brain, database
from engine.brain.seed import seed_if_empty


class BrainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "b.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_seed_runs_once_and_builds_a_graph(self):
        self.assertTrue(seed_if_empty(self.conn))
        self.assertFalse(seed_if_empty(self.conn))
        g = brain.graph(self.conn)
        types = {n["type"] for n in g["nodes"]}
        self.assertEqual(types, {"space", "note", "tag"})
        self.assertTrue(any(e["type"] == "link" for e in g["edges"]))

    def test_note_defaults_to_inbox(self):
        n = brain.create_note(self.conn, "  A thought  ")
        self.assertEqual(n["space_id"], brain.INBOX_ID)
        self.assertEqual(n["title"], "A thought")
        with self.assertRaises(ValueError):
            brain.create_note(self.conn, "   ")

    def test_wikilinks_resolve_both_ways(self):
        a = brain.create_note(self.conn, "Alpha", "see [[Beta]] and [[beta|alias]]")
        self.assertEqual(a["links_out"], [])  # Beta does not exist yet
        b = brain.create_note(self.conn, "Beta")
        a = brain.get_note(self.conn, a["id"])
        self.assertEqual([l["id"] for l in a["links_out"]], [b["id"]])
        self.assertEqual([l["id"] for l in brain.get_note(self.conn, b["id"])["links_in"]], [a["id"]])
        brain.update_note(self.conn, a["id"], body="no links any more")
        self.assertEqual(brain.get_note(self.conn, a["id"])["links_out"], [])

    def test_tags_are_parsed_and_cleaned(self):
        n = brain.create_note(self.conn, "T", "#Work on #idea-1, not a#tag")
        self.assertEqual(n["tags"], ["idea-1", "work"])
        brain.update_note(self.conn, n["id"], body="#work only")
        self.assertEqual(brain.get_note(self.conn, n["id"])["tags"], ["work"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0], 1)

    def test_search_prefix_and_accents(self):
        brain.create_note(self.conn, "Réunion équipe", "Planifier la stratégie produit")
        brain.create_note(self.conn, "Groceries", "milk")
        self.assertEqual([r["title"] for r in brain.search(self.conn, "reunion")], ["Réunion équipe"])
        self.assertEqual([r["title"] for r in brain.search(self.conn, "strat")], ["Réunion équipe"])
        self.assertEqual(brain.search(self.conn, "   "), [])
        self.assertEqual(brain.search(self.conn, 'bad "query" OR'), [])

    def test_spaces_and_moves(self):
        s = brain.create_space(self.conn, "Client X", "project")
        n = brain.create_note(self.conn, "Kickoff", space_id=s["id"])
        counts = {x["name"]: x["note_count"] for x in brain.list_spaces(self.conn)}
        self.assertEqual(counts["Client X"], 1)
        brain.update_note(self.conn, n["id"], space_id=brain.INBOX_ID)
        with self.assertRaises(brain.NotFound):
            brain.update_note(self.conn, n["id"], space_id="nope")
        with self.assertRaises(ValueError):
            brain.create_space(self.conn, "x", "inbox")

    def test_briefing_tracks_visits(self):
        first = brain.briefing(self.conn)
        self.assertIsNone(first["previous_visit_at"])
        self.conn.commit()
        second = brain.briefing(self.conn)
        self.assertIsNotNone(second["previous_visit_at"])
        self.assertEqual(second["created"], [])

    def test_delete_cascades(self):
        a = brain.create_note(self.conn, "A", "#x")
        b = brain.create_note(self.conn, "B", "[[A]]")
        brain.delete_note(self.conn, a["id"])
        self.assertEqual(brain.get_note(self.conn, b["id"])["links_out"], [])
        self.assertNotIn(a["id"], [r["id"] for r in brain.search(self.conn, "A")])


class AccentedLinkTests(unittest.TestCase):
    def test_wikilink_to_a_title_starting_with_an_accented_capital(self):
        d = Path(tempfile.mkdtemp()) / "x.sqlite3"
        database.migrate(d)
        with database.session(d) as conn:
            brain.ensure_inbox(conn)
            e = brain.create_note(conn, "Économie", "x")
            n = brain.create_note(conn, "Boucle", "Voir [[économie]]")
            self.assertEqual(conn.execute("SELECT to_note FROM links WHERE from_note = ?", (n["id"],)).fetchone()[0], e["id"])
