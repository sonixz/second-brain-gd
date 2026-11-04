"""The assistant's graph actions (2026-11-04 owner test): find items by what they are called, move them, unlink,
delete, and never report a change that did not happen."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import brain, database
from engine.assistant import actions as act
from engine.assistant import core
from engine.assistant.llm import FakeChat
from engine.brain.seed import seed_if_empty


def call(name, **args):
    return {"id": "c-" + name, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class GraphActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "g.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_if_empty(self.conn)
        self.job = brain.create_space(self.conn, "Recherche d'emploi")
        self.cv1 = brain.create_note(self.conn, "Résumé de carrière de Pierre-Yves Forget - Français", "Azure, 17 ans.", None, "reference")
        self.cv2 = brain.create_note(self.conn, "Profil professionnel de Pierre-Yves Forget - Français", "Architecte.", None, "reference")
        self.voice = brain.create_note(self.conn, "Deux CV pour Airudi et Beneva", "un pour Airudi, l'autre pour Beneva",
                                       self.job["id"], "note", source="voice")
        self.actions = []

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def run_tool(self, name, **args):
        return core.run_tool(self.conn, name, args, self.actions)

    def test_find_lists_what_waits_in_the_inbox_with_places(self):
        out = self.run_tool("find_items", place="Inbox")
        titles = [i["title"] for i in out["items"]]
        self.assertIn(self.cv1["title"], titles)
        self.assertNotIn(self.voice["title"], titles)
        self.assertEqual(out["place"], "Inbox")

    def test_move_by_title_moves_exactly_those_and_says_so(self):
        out = self.run_tool("move_items", items=["Résumé de carrière", "profil professionnel de pierre-yves forget"],
                            place="Recherche d’emploi")  # curly apostrophe, partial and lower-case titles
        self.assertEqual(out["changed"], 2)
        self.assertEqual(sorted(out["moved"]), sorted([self.cv1["title"], self.cv2["title"]]))
        self.assertEqual(out["place"], "Projets › Recherche d'emploi")
        for n in (self.cv1, self.cv2):
            self.assertEqual(brain.get_note(self.conn, n["id"])["space_id"], self.job["id"])
        again = self.run_tool("move_items", items=["Résumé de carrière"], place="Recherche d'emploi")
        self.assertEqual((again["changed"], again["already_there"]), (0, [self.cv1["title"]]))
        core.undo(self.conn, self.actions[0]["action_id"])  # each move is undoable
        self.assertEqual(brain.get_note(self.conn, self.actions[0]["note_id"])["space_id"], "inbox")

    def test_unknown_place_moves_nothing_and_lists_the_real_ones(self):
        out = self.run_tool("move_items", items=["Résumé de carrière"], place="Carrière")
        self.assertIn("error", out)
        self.assertIn("Projets › Recherche d'emploi", out["existing_places"])
        self.assertEqual(brain.get_note(self.conn, self.cv1["id"])["space_id"], "inbox")

    def test_ambiguous_and_missing_items_are_reported_not_guessed(self):
        out = self.run_tool("move_items", items=["Pierre-Yves Forget", "Lettre pour Desjardins"], place="Recherche d'emploi")
        self.assertEqual(out["changed"], 0)
        self.assertEqual(len(out["ambiguous"][0]["candidates"]), 2)
        self.assertEqual(out["not_found"], ["Lettre pour Desjardins"])

    def test_unlink_and_undo(self):
        self.run_tool("link_items", item="Deux CV pour Airudi", other="Résumé de carrière")
        self.assertEqual(len(act._link_rows(self.conn, self.voice["id"], self.cv1["id"])), 1)
        out = self.run_tool("unlink_items", item="Deux CV pour Airudi et Beneva", other="Résumé de carrière")
        self.assertEqual(out["changed"], 1)
        self.assertEqual(act._link_rows(self.conn, self.voice["id"], self.cv1["id"]), [])
        core.undo(self.conn, self.actions[-1]["action_id"])
        self.assertEqual(len(act._link_rows(self.conn, self.voice["id"], self.cv1["id"])), 1)

    def test_unlinking_a_written_link_keeps_the_words(self):
        n = brain.create_note(self.conn, "Plan", "Voir [[Deux CV pour Airudi et Beneva]] demain.")
        out = self.run_tool("unlink_items", item="Plan", other="Deux CV pour Airudi et Beneva")
        self.assertEqual(out["changed"], 1)
        self.assertEqual(brain.get_note(self.conn, n["id"])["body"], "Voir Deux CV pour Airudi et Beneva demain.")

    def test_unlinking_items_that_only_share_a_tag_explains_it(self):
        a = brain.create_note(self.conn, "Note A", "x #carriere")
        b = brain.create_note(self.conn, "Note B", "y #carriere")
        out = self.run_tool("unlink_items", item="Note A", other="Note B")
        self.assertEqual(out["changed"], 0)
        self.assertEqual(out["shared"]["tags"], ["carriere"])
        self.run_tool("remove_tag", item="Note B", tag="#carriere")
        self.assertNotIn("#carriere", brain.get_note(self.conn, b["id"])["body"])

    def test_trash_and_undo(self):
        out = self.run_tool("trash_items", items=["Deux CV pour Airudi et Beneva"])
        self.assertEqual(out["changed"], 1)
        self.assertNotIn(self.voice["id"], {n["id"] for n in brain.graph(self.conn)["nodes"]})
        core.undo(self.conn, self.actions[-1]["action_id"])
        self.assertIn(self.voice["id"], {n["id"] for n in brain.graph(self.conn)["nodes"]})

    def test_remove_a_place_items_back_in_inbox_and_undo(self):
        area = brain.create_space(self.conn, "Carrière", "area")
        self.conn.execute("UPDATE spaces SET area_id = ? WHERE id = ?", (area["id"], self.job["id"]))
        out = self.run_tool("remove_place", place="recherche d'emploi")
        self.assertEqual((out["changed"], out["removed_place"], out["items_back_in_inbox"]), (1, "Recherche d'emploi", 1))
        self.assertEqual(brain.get_note(self.conn, self.voice["id"])["space_id"], "inbox")
        self.assertNotIn(self.job["id"], {s["id"] for s in brain.list_spaces(self.conn)})
        self.assertEqual(self.run_tool("remove_place", place="Inbox")["changed"], 0)
        gone_area = self.run_tool("remove_place", place="Carrière")
        self.assertEqual(gone_area["changed"], 1)
        core.undo(self.conn, self.actions[0]["action_id"])  # the place and its item come back
        self.assertEqual(brain.get_note(self.conn, self.voice["id"])["space_id"], self.job["id"])
        self.assertIn(self.job["id"], {s["id"] for s in brain.list_spaces(self.conn)})
        core.undo(self.conn, self.actions[1]["action_id"])  # and the project is back under its area
        self.assertEqual(brain.get_space(self.conn, self.job["id"])["area_id"], area["id"])

    def test_update_that_changes_nothing_says_so(self):
        out = self.run_tool("update_note", note_id=self.voice["id"], space_id=self.job["id"])
        self.assertEqual(out["changed"], 0)
        self.assertEqual(self.actions, [])  # nothing journalled, nothing to claim


class AssistantHonestyTests(unittest.TestCase):
    """The exact failures of 2026-11-04, replayed with a scripted model."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "h.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_if_empty(self.conn)
        self.job = brain.create_space(self.conn, "Recherche d'emploi")
        self.cv = brain.create_note(self.conn, "Résumé de carrière", "CV", None, "reference")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def script(self, replies):
        seen = []
        it = iter(replies)

        def fake(self_, model, messages, **kw):
            seen.append(messages[-1])
            return {**next(it), "usage": {}, "model": model}
        return fake, seen

    def test_a_false_success_is_corrected(self):
        fake, seen = self.script([
            {"message": {"role": "assistant", "content": None, "tool_calls": [call("update_note", note_id=self.cv["id"], space_id="inbox")]}},
            {"message": {"role": "assistant", "content": "Les deux CV ont été détachés de l'Inbox."}},
            {"message": {"role": "assistant", "content": None, "tool_calls": [call("move_items", items=["Résumé de carrière"], place="Recherche d'emploi")]}},
            {"message": {"role": "assistant", "content": "« Résumé de carrière » est maintenant dans Recherche d'emploi."}},
        ])
        with mock.patch.object(FakeChat, "complete", fake):
            out = core.chat(self.conn, FakeChat(), "détache mes CV de l'Inbox")
        self.assertTrue(any(m.get("content") == core.CHANGE_NUDGE for m in seen))
        self.assertEqual(brain.get_note(self.conn, self.cv["id"])["space_id"], self.job["id"])
        self.assertIn("maintenant dans", out["reply"])

    def test_clipboard_is_not_captured_unless_asked(self):
        fake, seen = self.script([
            {"message": {"role": "assistant", "content": None, "tool_calls": [call("ui_capture_clipboard")]}},
            {"message": {"role": "assistant", "content": "Je n'ai rien fait pour l'instant: quel élément veux-tu classer?"}},
        ])
        with mock.patch.object(FakeChat, "complete", fake):
            out = core.chat(self.conn, FakeChat(), "Qu'est-ce que tu veux dire?")
        self.assertEqual(out["ui_actions"], [])
        self.assertIn("refused", json.loads(seen[1]["content"]))
        fake2, _ = self.script([
            {"message": {"role": "assistant", "content": None, "tool_calls": [call("ui_capture_clipboard")]}},
            {"message": {"role": "assistant", "content": "J'ajoute ce que tu as copié."}},
        ])
        with mock.patch.object(FakeChat, "complete", fake2):
            out = core.chat(self.conn, FakeChat(), "ajoute ce que j'ai copié au Brain")
        self.assertEqual(out["ui_actions"][0]["action"], "capture_clipboard")

    def test_answers_that_change_nothing_and_claim_nothing_pass(self):
        with mock.patch.object(FakeChat, "complete", return_value={
                "message": {"role": "assistant", "content": "Tu as un CV dans l'Inbox."}, "usage": {}, "model": "m"}) as m:
            core.chat(self.conn, FakeChat(), "qu'est-ce qui attend dans l'Inbox?")
        self.assertEqual(m.call_count, 1)


if __name__ == "__main__":
    unittest.main()
