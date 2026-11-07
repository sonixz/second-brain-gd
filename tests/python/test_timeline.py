"""Loop MCP-B2: the timeline of changes, restore points, « go back to this moment » (all or one author)."""
import tempfile
import unittest
from pathlib import Path

from engine import brain, database
from engine.assistant import actions as act
from engine.brain import timeline, types
from engine.brain.seed import seed_all
from engine.mcp import proposals, server


class TimelineTests(unittest.TestCase):
    def setUp(self):
        proposals._recent.clear()
        timeline.take_pending_backups()
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "data" / "second_brain.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_all(self.conn)
        self.cuisine = brain.create_space(self.conn, "Cuisine", "area")
        self.maison = brain.create_space(self.conn, "Atelier", "area")
        self.a = brain.create_note(self.conn, "Paella du samedi", "Riz.")
        self.b = brain.create_note(self.conn, "Pneus d'hiver", "Garage.")
        self.cc = server.create_client(self.conn, "Claude Code", "propose_changes")
        self.conn.execute("UPDATE mcp_clients SET direct = 1 WHERE id = ?", (self.cc["id"],))

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def propose(self, kind, **args):
        return proposals.propose(self.conn, {"id": self.cc["id"], "name": "Claude Code"}, kind, args)

    def test_a_session_starts_with_a_restore_point_and_a_backup_request(self):
        self.propose("change", action="move", item=self.a["id"], target="Cuisine", reason="recette")
        points = self.conn.execute("SELECT * FROM restore_points").fetchall()
        self.assertEqual(len(points), 1)
        self.assertEqual((points[0]["name"], points[0]["auto"]), ("Avant les changements de Claude Code", 1))
        self.assertEqual(timeline.take_pending_backups(), ["mcp:Claude Code"])
        self.propose("change", action="move", item=self.b["id"], target="Atelier", reason="auto")
        self.assertEqual(len(self.conn.execute("SELECT * FROM restore_points").fetchall()), 1, "one point per session")

    def test_the_timeline_says_who_did_what(self):
        journal = lambda c, k, n, b, a, r: __import__("engine.assistant.core", fromlist=["x"])._journal(c, k, n, b, a, r)  # noqa: E731
        act.move_items(self.conn, None, journal, [], [self.b["id"]], "Atelier")  # the assistant (no author)
        self.propose("change", action="move", item=self.a["id"], target="Cuisine", reason="recette")
        e = timeline.entries(self.conn)
        actions = [x for x in e if x["type"] == "action"]
        self.assertEqual([(x["author"], x["title"]) for x in actions[:2]], [("mcp:Claude Code", "Paella du samedi"), ("assistant", "Pneus d'hiver")])
        self.assertIn("point", [x["type"] for x in e])
        self.assertEqual(timeline.authors(self.conn), ["assistant", "mcp:Claude Code"])
        only = [x for x in timeline.entries(self.conn, "mcp:Claude Code") if x["type"] == "action"]
        self.assertEqual({x["author"] for x in only}, {"mcp:Claude Code"})

    def test_going_back_undoes_one_author_and_keeps_the_rest(self):
        journal = lambda c, k, n, b, a, r: __import__("engine.assistant.core", fromlist=["x"])._journal(c, k, n, b, a, r)  # noqa: E731
        point = timeline.create_point(self.conn, "Avant le grand ménage")
        act.move_items(self.conn, None, journal, [], [self.b["id"]], "Atelier")
        self.propose("change", action="move", item=self.a["id"], target="Cuisine", reason="recette")
        added = self.propose("item", title="Liste de souper", content="Lundi pâtes.", reason="utile")
        types.set_props(self.conn, self.a["id"], "recipe", {"servings": 4})
        out = timeline.rewind_to_point(self.conn, point["id"], "mcp:Claude Code")
        self.assertEqual(out["conflicts"], [])
        self.assertGreaterEqual(out["undone"], 2)
        self.assertNotEqual(brain.get_note(self.conn, self.a["id"])["space_id"], self.cuisine["id"], "Claude Code's move undone")
        self.assertEqual(brain.get_note(self.conn, self.b["id"])["space_id"], self.maison["id"], "the assistant's move kept")
        gone = brain.get_note(self.conn, added["item"])
        self.assertEqual(gone["status"], "archived", "an item created after the moment goes to the trash, never erased")

    def test_a_conflict_is_reported_not_overwritten(self):
        point = timeline.create_point(self.conn, "p")
        self.propose("change", action="move", item=self.a["id"], target="Cuisine", reason="recette")
        brain.update_note(self.conn, self.a["id"], space_id=self.maison["id"])  # the user moved it again, by hand
        out = timeline.rewind_to_point(self.conn, point["id"])
        self.assertEqual(out["undone"], 0)
        self.assertIn("was changed since", out["conflicts"][0]["why"])
        self.assertEqual(brain.get_note(self.conn, self.a["id"])["space_id"], self.maison["id"], "the user's change stays")

    def test_set_fields_can_be_undone(self):
        types.set_props(self.conn, self.a["id"], "recipe", {"servings": 4})
        point = timeline.create_point(self.conn, "p")
        self.propose("change", action="set_fields", item=self.a["id"], fields={"servings": 8}, reason="famille")
        self.assertEqual(types.get_props(self.conn, self.a["id"])["props"]["servings"], 8)
        timeline.rewind_to_point(self.conn, point["id"])
        self.assertEqual(types.get_props(self.conn, self.a["id"])["props"]["servings"], 4)


if __name__ == "__main__":
    unittest.main()
