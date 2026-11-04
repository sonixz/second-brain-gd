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
        self.assertIsNone(estimate_cost("gpt-6-sol", {"prompt_tokens": 10, "completion_tokens": 10}))


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

    def test_weekly_review(self):
        from engine.brain import structure
        p = structure.create_project(self.conn, "Atlas")
        t = structure.add_task(self.conn, "Envoyer", p["id"])
        structure.set_task(self.conn, t["id"], done=True)
        out = core.weekly_review(self.conn, self.client)
        self.assertTrue(out["text"])
        self.assertEqual(out["projects"], 1)
        hist = core.history(self.conn, core.today_conversation())
        self.assertEqual(hist[-1]["meta"]["kind"], "weekly_review")

    def test_project_mode_uses_card_instructions_and_scope(self):
        from engine.brain import structure
        p = structure.create_project(self.conn, "Atlas", goal="Signer le mandat")
        structure.update_space(self.conn, p["id"], instructions="Toujours répondre en anglais au client.")
        structure.add_task(self.conn, "Envoyer la proposition", p["id"], "2030-01-10")
        core.chat(self.conn, self.client, "Où en est le projet?", p["id"])
        system = FakeChat.last_messages[0]["content"]
        for expected in ("MODE PROJET", "Signer le mandat", "Toujours répondre en anglais", "Envoyer la proposition (due 2030-01-10)"):
            self.assertIn(expected, system)
        other = brain.create_space(self.conn, "Autre")
        brain.create_note(self.conn, "Atlas dans un autre espace", "", other["id"])
        brain.create_note(self.conn, "Atlas dans le projet", "", p["id"])
        res = core.run_tool(self.conn, "search_notes", {"query": "Atlas", "space_ids": [p["id"]]}, [])
        self.assertEqual([r["title"] for r in res["results"]], ["Atlas dans le projet"])
        self.assertEqual(res["scope"], "project + shared resources")

    def test_briefing_facts_include_structure(self):
        self.assertTrue(core.briefing(self.conn, self.client)["text"])


class HandsFreeTests(unittest.TestCase):
    """Loop 7a: the assistant drives the interface (Godot performs the returned ui_actions)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "h.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_if_empty(self.conn)
        self.client = FakeChat()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_open_view_by_voice_returns_ui_action(self):
        out = core.chat(self.conn, self.client, "Ouvre ma journée d'aujourd'hui")
        self.assertEqual(out["ui_actions"], [{"action": "open_view", "view": "today"}])
        self.assertEqual(out["actions"], [])  # nothing changed in the brain
        again = core.chat(self.conn, self.client, "bonjour")
        self.assertEqual(again["ui_actions"], [])  # actions never leak into the next turn

    def test_replay_and_voice_speed_by_voice(self):
        out = core.chat(self.conn, self.client, "Relis-moi ça")
        self.assertEqual(out["ui_actions"], [{"action": "replay", "which": "last"}])
        out = core.chat(self.conn, self.client, "Parle plus vite s'il te plaît")
        self.assertEqual(out["ui_actions"], [{"action": "set_voice_speed", "change": "faster"}])
        self.assertIn("error", core.run_tool(self.conn, "ui_set_voice_speed", {"change": "warp"}, []))
        core._UI["actions"] = []
        core.run_tool(self.conn, "ui_replay", {"which": "review"}, [])
        self.assertEqual(core._UI["actions"], [{"action": "replay", "which": "review"}])

    def test_clipboard_and_working_context_by_voice(self):
        out = core.chat(self.conn, self.client, "Ajoute ça au Brain")
        self.assertEqual(out["ui_actions"], [{"action": "capture_clipboard"}])
        out = core.chat(self.conn, self.client, "Je veux structurer le projet Lancement")
        ctx = out["ui_actions"][0]["context"]
        self.assertEqual((out["ui_actions"][0]["action"], ctx["name"], ctx["kind"]), ("context", "Lancement", "project"))
        self.assertIn("Lancement", out["reply"])

    def test_spoken_messages_ask_for_a_short_answer(self):
        core.chat(self.conn, self.client, "bonjour", spoken=True)
        self.assertIn("VOIX", FakeChat.last_messages[0]["content"])
        core.chat(self.conn, self.client, "bonjour")
        self.assertNotIn("VOIX", FakeChat.last_messages[0]["content"])

    def test_ui_tools_validate_ids_and_values(self):
        acts = []
        self.assertIn("error", core.run_tool(self.conn, "ui_open_project", {"space_id": "nope"}, acts))
        self.assertIn("error", core.run_tool(self.conn, "ui_open_note", {"note_id": "nope"}, acts))
        self.assertIn("error", core.run_tool(self.conn, "ui_set_theme", {"theme": "neon"}, acts))
        self.assertIn("error", core.run_tool(self.conn, "ui_open_view", {"view": "settings"}, acts))
        n = brain.create_note(self.conn, "Plan Atlas")
        core._UI["actions"] = []
        out = core.run_tool(self.conn, "ui_open_note", {"note_id": n["id"]}, acts)
        self.assertTrue(out["done"])
        self.assertEqual(core._UI["actions"][0]["title"], "Plan Atlas")

    def test_undo_last_action_by_voice(self):
        core.run_tool(self.conn, "create_note", {"title": "À défaire"}, [])
        self.assertTrue(self.conn.execute("SELECT 1 FROM notes WHERE title = 'À défaire'").fetchone())
        out = core.chat(self.conn, self.client, "Annule ça")
        self.assertIn({"action": "refresh"}, out["ui_actions"])
        row = self.conn.execute("SELECT status FROM notes WHERE title = 'À défaire'").fetchone()
        self.assertTrue(row is None or row["status"] == "archived")
        nothing = core.run_tool(self.conn, "undo_last_action", {}, [])
        self.assertFalse(nothing["undone"])


class ClaimGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "g.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_if_empty(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_claimed_action_without_tool_gets_one_nudge(self):
        replies = iter([
            {"message": {"role": "assistant", "content": "D'accord, j'annule ça."}},
            {"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "u1", "type": "function", "function": {"name": "undo_last_action", "arguments": "{}"}}]}},
            {"message": {"role": "assistant", "content": "Il n'y avait rien à annuler."}},
        ])
        seen = []

        def fake(self_, model, messages, **kw):
            seen.append(messages[-1]["content"])
            return {**next(replies), "usage": {}, "model": model}

        with mock.patch.object(FakeChat, "complete", fake):
            out = core.chat(self.conn, FakeChat(), "annule ça")
        self.assertEqual(out["reply"], "Il n'y avait rien à annuler.")
        self.assertIn(core.CLAIM_NUDGE, seen)

    def test_plain_answers_are_not_nudged(self):
        with mock.patch.object(FakeChat, "complete", return_value={
                "message": {"role": "assistant", "content": "Bonjour! Comment je peux t'aider?"}, "usage": {}, "model": "m"}) as m:
            core.chat(self.conn, FakeChat(), "salut")
        self.assertEqual(m.call_count, 1)
