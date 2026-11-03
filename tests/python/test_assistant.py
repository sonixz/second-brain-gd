import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import brain, database
from engine.assistant import core
from engine.assistant.llm import FakeChat, estimate_cost, make_client
from engine.brain.seed import seed_if_empty


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "a.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_if_empty(self.conn)
        self.atlas = brain.create_space(self.conn, "Client Atlas")
        self.client = FakeChat()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_no_key_no_client(self):
        with mock.patch.dict(os.environ, {"SBGD_ASSISTANT_PROVIDER": ""}):
            with self.assertRaises(PermissionError):
                make_client(None)

    def test_classify_applies_and_undoes(self):
        n = brain.create_note(self.conn, "Appeler client atlas demain")
        res = core.classify(self.conn, self.client, n["id"])
        self.assertTrue(res["applied"])
        moved = brain.get_note(self.conn, n["id"])
        self.assertEqual(moved["space_id"], self.atlas["id"])
        self.assertIn("fake", moved["tags"])
        core.undo(self.conn, res["action_id"])
        back = brain.get_note(self.conn, n["id"])
        self.assertEqual((back["space_id"], back["body"]), (brain.INBOX_ID, ""))
        self.assertEqual(core.undo(self.conn, res["action_id"])["undone"], False)

    def test_classify_low_confidence_leaves_note(self):
        n = brain.create_note(self.conn, "Something vague")
        res = core.classify(self.conn, self.client, n["id"])
        self.assertFalse(res["applied"])
        self.assertEqual(brain.get_note(self.conn, n["id"])["space_id"], brain.INBOX_ID)

    def test_chat_uses_tools_and_cites(self):
        out = core.chat(self.conn, self.client, "cherche constellations")
        self.assertIn("[[", out["reply"])
        self.assertTrue(out["cited"])
        roles = [m["role"] for m in core.history(self.conn, core.today_conversation())]
        self.assertEqual(roles, ["user", "assistant"])

    def test_tools_create_and_update_are_journaled(self):
        actions = []
        created = core.run_tool(self.conn, "create_note", {"title": "From the assistant", "kind": "task"}, actions)
        nid = created["created"]["id"]
        self.assertEqual(brain.get_note(self.conn, nid)["source"], "agent")
        core.run_tool(self.conn, "update_note", {"note_id": nid, "space_id": self.atlas["id"]}, actions)
        self.assertEqual([a["kind"] for a in actions], ["create_note", "update_note"])
        core.undo(self.conn, actions[1]["action_id"])
        self.assertEqual(brain.get_note(self.conn, nid)["space_id"], brain.INBOX_ID)
        core.undo(self.conn, actions[0]["action_id"])
        with self.assertRaises(brain.NotFound):
            brain.get_note(self.conn, nid)
        self.assertIn("error", core.run_tool(self.conn, "get_note", {"note_id": "nope"}, actions))

    def test_briefing_is_cached_per_day(self):
        first = core.briefing(self.conn, self.client)
        second = core.briefing(self.conn, self.client)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(first["text"], second["text"])

    def test_speak_is_cached_and_strips_brackets(self):
        cache = Path(self.tmp.name) / "tts"
        a, hit1 = core.speak(self.conn, self.client, "Voir [[Engine room]]", "morning", cache)
        b, hit2 = core.speak(self.conn, self.client, "Voir [[Engine room]]", "morning", cache)
        self.assertEqual((hit1, hit2), (False, True))
        self.assertEqual(a, b)

    def test_cost_estimate(self):
        self.assertAlmostEqual(estimate_cost("gpt-4o-mini", {"prompt_tokens": 1_000_000, "completion_tokens": 0}), 0.15)


if __name__ == "__main__":
    unittest.main()


class StructureToolTests(unittest.TestCase):
    def setUp(self):
        from engine.brain import structure
        from engine.brain.seed import seed_all
        self.structure = structure
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "s.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_all(self.conn)
        self.client = FakeChat()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_grocery_capture_becomes_list_items_and_undo_restores(self):
        n = brain.create_note(self.conn, "acheter lait, pain")
        res = core.classify(self.conn, self.client, n["id"])
        self.assertTrue(res["applied"])
        self.assertEqual(res["proposal"]["checklist_name"], "Épicerie")
        items = [i["text"] for i in self.structure.find_checklist(self.conn, "Épicerie")["items"]]
        self.assertEqual(items, ["lait", "pain"])
        with self.assertRaises(brain.NotFound):
            brain.get_note(self.conn, n["id"])
        back = core.undo(self.conn, res["action_id"])
        self.assertEqual(self.structure.find_checklist(self.conn, "Épicerie")["items"], [])
        self.assertEqual(brain.get_note(self.conn, back["note_id"])["title"], "acheter lait, pain")

    def test_tools_projects_tasks_lists(self):
        actions = []
        area = next(a for a in self.structure.structure(self.conn)["areas"] if a["name"] == "Famille")
        p = core.run_tool(self.conn, "create_project", {"name": "Fête de Léa", "area_id": area["id"],
                                                         "due_date": "2027-03-01"}, actions)["created_project"]
        t = core.run_tool(self.conn, "add_task", {"title": "Réserver la salle", "space_id": p["id"],
                                                  "due_date": "2027-02-01"}, actions)["created_task"]
        today = core.run_tool(self.conn, "get_today", {}, actions)
        self.assertIn("Réserver la salle", [x["title"] for x in today["next_actions"]])
        core.run_tool(self.conn, "complete_task", {"note_id": t["id"]}, actions)
        self.assertEqual(brain.get_note(self.conn, t["id"])["status"], "done")
        core.undo(self.conn, actions[-1]["action_id"])
        self.assertEqual(brain.get_note(self.conn, t["id"])["status"], "active")
        r = core.run_tool(self.conn, "add_to_checklist", {"checklist": "épicerie", "items": ["Café"]}, actions)
        self.assertEqual(r["added"], 1)
        core.undo(self.conn, actions[-1]["action_id"])
        self.assertEqual(self.structure.find_checklist(self.conn, "Épicerie")["items"], [])
        core.undo(self.conn, actions[0]["action_id"])  # undo the project creation: it is archived
        self.assertNotIn("Fête de Léa", [s["name"] for s in brain.list_spaces(self.conn)])
        self.assertIn("error", core.run_tool(self.conn, "add_task", {"title": "x", "due_date": "demain"}, actions))

    def test_briefing_facts_include_structure(self):
        self.assertTrue(core.briefing(self.conn, self.client)["text"])
