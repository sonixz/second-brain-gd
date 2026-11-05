"""Sparring, the thinking partner (2026-11-04): reads, argues, never changes the Brain, except a synthesis the user
asked for and approved."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import brain, database
from engine.assistant import agents, core
from engine.assistant.llm import FakeChat
from engine.brain.seed import seed_if_empty
from engine.voice import live


def call(name, **args):
    return {"id": "c-" + name, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class SparringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "s.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_if_empty(self.conn)
        self.job = brain.create_space(self.conn, "Recherche d'emploi")
        self.cv = brain.create_note(self.conn, "CV Azure", "CV", None, "reference")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def script(self, replies):
        seen, it = [], iter(replies)

        def fake(self_, model, messages, **kw):
            seen.append({"model": model, "tools": [t["function"]["name"] for t in kw.get("tools") or []], "last": messages[-1],
                         "system": messages[0]["content"]})
            return {**next(it), "usage": {}, "model": model}
        return fake, seen

    def test_its_own_role_model_tools_and_conversation(self):
        fake, seen = self.script([{"message": {"role": "assistant", "content": "Qu'est-ce qui te fait douter?"}}])
        with mock.patch.object(FakeChat, "complete", fake):
            out = core.chat(self.conn, FakeChat(), "J'ai une idée d'agent vocal.", agent="sparring")
        self.assertEqual(seen[0]["model"], "gpt-6-sol")
        self.assertIn("Sparring", seen[0]["system"])
        self.assertIn("web_search", seen[0]["tools"])
        for forbidden in ("move_items", "trash_items", "create_note", "update_note", "add_web_page", "remove_place"):
            self.assertNotIn(forbidden, seen[0]["tools"])
        self.assertEqual([m["role"] for m in core.history(self.conn, agents.conversation("sparring"))], ["user", "assistant"])
        self.assertEqual(core.history(self.conn, agents.conversation("archivist")), [])  # separate conversations
        self.assertIn("douter", out["reply"])

    def test_it_cannot_change_the_graph_even_if_it_tries(self):
        fake, seen = self.script([
            {"message": {"role": "assistant", "content": None, "tool_calls": [call("move_items", items=["CV Azure"], place="Recherche d'emploi")]}},
            {"message": {"role": "assistant", "content": "Je ne peux pas classer; l'archiviste peut le faire."}}])
        with mock.patch.object(FakeChat, "complete", fake):
            core.chat(self.conn, FakeChat(), "Classe mon CV", agent="sparring")
        self.assertEqual(brain.get_note(self.conn, self.cv["id"])["space_id"], "inbox")
        self.assertIn("not available to Sparring", seen[1]["last"]["content"])

    def test_a_synthesis_is_saved_only_after_approval(self):
        body = "## L'idée\\nUn agent vocal de réflexion.\\n## Décidé\\nIl ne modifie rien sauf la synthèse approuvée."
        fake, _ = self.script([
            {"message": {"role": "assistant", "content": None, "tool_calls": [call("draft_synthesis", title="Agent vocal Sparring", body=body)]}},
            {"message": {"role": "assistant", "content": None, "tool_calls": [call("save_synthesis")]}},  # tries to save unasked
            {"message": {"role": "assistant", "content": "Voici l'essentiel. Je l'enregistre?"}},
            {"message": {"role": "assistant", "content": None, "tool_calls": [call("save_synthesis")]}},
            {"message": {"role": "assistant", "content": "C'est dans ton Brain."}}])
        from engine.brain import archivist
        with mock.patch.object(FakeChat, "complete", fake), \
                mock.patch.object(archivist, "file_item", return_value={"receipt": "Idée classée dans Ressources › IA."}) as filed:
            first = core.chat(self.conn, FakeChat(), "Résume-moi tout ça", agent="sparring")
            self.assertIsNone(self.conn.execute("SELECT 1 FROM notes WHERE title = 'Agent vocal Sparring'").fetchone())
            self.assertIn({"action": "synthesis_draft"}, first["ui_actions"])
            self.assertEqual(database.get_setting(self.conn, "sparring_draft")["title"], "Agent vocal Sparring")
            second = core.chat(self.conn, FakeChat(), "Oui, parfait, vas-y", agent="sparring")
        self.assertEqual(filed.call_count, 1)  # the archivist files it
        row = self.conn.execute("SELECT id, kind, source, body FROM notes WHERE title = 'Agent vocal Sparring'").fetchone()
        self.assertEqual((row["kind"], row["source"]), ("idea", "agent"))
        self.assertIn("Synthèse d'une conversation avec Sparring", row["body"])
        self.assertIsNone(database.get_setting(self.conn, "sparring_draft"))
        core.undo(self.conn, second["actions"][0]["action_id"])  # and it can be undone
        self.assertIsNone(self.conn.execute("SELECT 1 FROM notes WHERE id = ?", (row["id"],)).fetchone())

    def test_synthesise_and_save_in_one_go_and_refusals(self):
        self.assertTrue(agents.SAVE_RE.search("synthétise et enregistre ça dans le brain"))
        self.assertTrue(agents.SAVE_RE.search("injecte-la"))
        self.assertTrue(agents.APPROVE_RE.search("oui"))
        self.assertTrue(agents.REFUSE_RE.search("oui mais change le titre"))
        self.assertIsNone(agents.APPROVE_RE.search("non, attends"))
        self.assertEqual(agents.save(self.conn, None, core._journal, [], "oui")["changed"], 0)  # nothing drafted

    def test_the_archivist_does_not_get_the_synthesis_tools(self):
        names = [t["function"]["name"] for t in agents.tools("archivist", core.TOOLS + agents.SYNTHESIS_TOOLS)]
        self.assertIn("move_items", names)
        self.assertNotIn("save_synthesis", names)

    def test_live_sparring_has_only_its_tools(self):
        sess = live.LiveSession(self.db, None, {}, "marin", None, None, None, agent="sparring")
        names = [t["name"] for t in sess.tools()]
        self.assertIn("draft_synthesis", names)
        self.assertIn("end_conversation", names)
        self.assertNotIn("move_items", names)
        self.assertIn("Sparring", sess.instructions())
        sess.last_user = "Classe mon CV"
        result, _ = sess._run_tool("move_items", {"items": ["CV Azure"], "place": "Recherche d'emploi"})
        self.assertIn("not available", result["error"])


if __name__ == "__main__":
    unittest.main()
