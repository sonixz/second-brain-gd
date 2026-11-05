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
            self.assertIn({"action": "synthesis_draft", "agent": "sparring"}, first["ui_actions"])
            self.assertEqual(agents.pending(self.conn, "sparring")["title"], "Agent vocal Sparring")
            second = core.chat(self.conn, FakeChat(), "Oui, parfait, vas-y", agent="sparring")
        self.assertEqual(filed.call_count, 1)  # the archivist files it
        row = self.conn.execute("SELECT id, kind, source, body FROM notes WHERE title = 'Agent vocal Sparring'").fetchone()
        self.assertEqual((row["kind"], row["source"]), ("idea", "agent"))
        self.assertIn("Synthèse d'une conversation avec Sparring", row["body"])
        self.assertIsNone(agents.pending(self.conn, "sparring"))
        core.undo(self.conn, second["actions"][0]["action_id"])  # and it can be undone
        self.assertIsNone(self.conn.execute("SELECT 1 FROM notes WHERE id = ?", (row["id"],)).fetchone())

    def test_synthesise_and_save_in_one_go_and_refusals(self):
        self.assertTrue(agents.SAVE_RE.search("synthétise et enregistre ça dans le brain"))
        self.assertTrue(agents.SAVE_RE.search("injecte-la"))
        self.assertTrue(agents.APPROVE_RE.search("oui"))
        self.assertTrue(agents.REFUSE_RE.search("oui mais change le titre"))
        self.assertIsNone(agents.APPROVE_RE.search("non, attends"))
        self.assertEqual(agents.save(self.conn, "sparring", None, core._journal, [], "oui")["changed"], 0)  # nothing drafted

    def test_the_archivist_does_not_get_the_synthesis_tools(self):
        names = [t["function"]["name"] for t in agents.tools(self.conn, "archivist", core.TOOLS + agents.SYNTHESIS_TOOLS)]
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


class AgentProfileTests(unittest.TestCase):
    """Loop 2: agents are profiles (instructions, capabilities, model) stored in the Brain."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "p.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_if_empty(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_every_tool_belongs_to_a_capability(self):
        grouped = {t for c in agents.CAPABILITIES.values() for t in c["tools"]}
        names = {t["function"]["name"] for t in core.TOOLS + agents.SYNTHESIS_TOOLS}
        self.assertEqual(names - grouped, set())  # a new tool must join a capability

    def test_builtins_can_be_adjusted_and_reset(self):
        agents.update(self.conn, "sparring", {"instructions": "Tu es Sparring, plus direct. " * 3})
        p = agents.profile(self.conn, "sparring")
        self.assertTrue(p["modified"])
        self.assertIn("plus direct", agents.persona(self.conn, "sparring"))
        self.assertIn("draft_synthesis", agents.persona(self.conn, "sparring"))  # synthesis rules follow the capability
        agents.reset(self.conn, "sparring")
        self.assertFalse(agents.profile(self.conn, "sparring")["modified"])
        with self.assertRaises(KeyError):
            agents.delete(self.conn, "archivist")

    def test_a_custom_agent_has_its_tools_conversation_and_model(self):
        p = agents.create(self.conn, {"name": "Coach entrevue", "instructions": "Tu prépares mes entrevues d'embauche. " * 4,
                                      "capabilities": ["read_brain", "internet", "organise_typo"]})
        self.assertEqual((p["id"], p["letter"], p["capabilities"]), ("coach-entrevue", "C", ["read_brain", "internet"]))
        self.assertIn("web_search", p["tools"])
        self.assertNotIn("move_items", p["tools"])
        self.assertTrue(agents.allowed(self.conn, "coach-entrevue", "end_conversation"))
        self.assertEqual(agents.conversation("coach-entrevue")[:15], "coach-entrevue-")
        with mock.patch.object(FakeChat, "complete", return_value={"message": {"role": "assistant", "content": "Prêt."},
                                                                    "usage": {}, "model": "gpt-6-sol"}) as m:
            core.chat(self.conn, FakeChat(), "Prépare-moi", agent="coach-entrevue")
        self.assertEqual(m.call_args[0][0], "gpt-6-sol")
        self.assertIn("entrevues", m.call_args[0][1][0]["content"])
        agents.delete(self.conn, "coach-entrevue")
        self.assertEqual(agents.name(self.conn, "coach-entrevue"), "archivist")  # unknown agents fall back to the archivist


class AgentBuilderTests(unittest.TestCase):
    """Loop 3: the Agent Builder interviews, drafts rich instructions, and creates or changes an agent on « yes »."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "b.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_if_empty(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_builder_is_an_agent_with_the_agents_capability_only(self):
        p = agents.profile(self.conn, "builder")
        self.assertEqual(p["capabilities"], ["read_brain", "agents", "interface"])
        self.assertNotIn("agents", agents.profile(self.conn, "archivist")["capabilities"])
        self.assertIn("draft_agent", p["tools"])

    def test_interview_draft_and_create_on_yes(self):
        c = FakeChat()
        first = core.chat(self.conn, c, "Je veux créer un nouvel agent.", agent="builder")
        self.assertIn("À quoi", first["reply"])
        drafted = core.chat(self.conn, c, "Un coach pour préparer mes entrevues, direct mais bienveillant.", agent="builder")
        self.assertIn({"action": "agent_draft"}, drafted["ui_actions"])
        self.assertNotIn("coach-entrevue", [p["id"] for p in agents.profiles(self.conn)])  # nothing created yet
        self.assertEqual(agents.save_agent(self.conn, "non, change le ton")["changed"], 0)
        done = core.chat(self.conn, c, "Oui, crée-le.", agent="builder")
        made = agents.profile(self.conn, "coach-entrevue")
        self.assertEqual((made["name"], made["capabilities"]), ("Coach entrevue", ["read_brain", "internet"]))
        self.assertIn({"action": "agents_changed", "agent": "coach-entrevue", "name": "Coach entrevue"}, done["ui_actions"])

    def test_changing_an_existing_agent_needs_approval_and_rich_text(self):
        self.assertIn("error", agents.draft_agent(self.conn, {"agent_id": "sparring", "instructions": "trop court"}))
        rich = "Tu es Sparring, version plus directe. " * 10
        self.assertTrue(agents.draft_agent(self.conn, {"agent_id": "sparring", "instructions": rich})["draft_ready"])
        self.assertEqual(agents.save_agent(self.conn, "hmm, je ne sais pas")["changed"], 0)
        out = agents.save_agent(self.conn, "Oui, applique")
        self.assertEqual((out["mode"], out["agent"]), ("update", "sparring"))
        self.assertTrue(agents.profile(self.conn, "sparring")["modified"])

    def test_the_archivist_hands_over_to_the_builder(self):
        out = core.chat(self.conn, FakeChat(), "Crée-moi un agent pour mes entrevues")
        self.assertEqual(out["ui_actions"][0], {"action": "open_agent", "agent": "builder"})


class EnglishApprovalTest(unittest.TestCase):
    """The website shows English phrases: approvals and refusals work in English as in French."""

    def test_synthesis_approval_in_both_languages(self):
        for yes in ("yes, save it", "Looks good", "perfect, save it", "Sum it up and save it", "oui, sauvegarde", "parfait"):
            self.assertTrue(agents.approved(yes), yes)
        for no in ("no, not yet", "change the part about risks", "wait", "non, pas encore", "change la partie sur…"):
            self.assertFalse(agents.approved(no), no)

    def test_agent_creation_approval_in_both_languages(self):
        for yes in ("yes, create it", "create it", "apply it", "oui, crée-le", "applique"):
            self.assertTrue(agents.BUILD_OK_RE.search(yes) and not agents.REFUSE_RE.search(yes), yes)
        for no in ("not yet", "no, make it tougher first", "pas encore"):
            self.assertTrue(agents.REFUSE_RE.search(no) or not agents.BUILD_OK_RE.search(no), no)

    def test_an_english_false_success_is_caught(self):
        self.assertTrue(core.CHANGE_RE.search("The two CVs have been detached."))
        self.assertTrue(core.CHANGE_RE.search("I've moved it to Job search."))
        self.assertFalse(core.CHANGE_RE.search("This note is linked to the kitchen project."))

    def test_a_french_false_success_is_caught_but_not_a_description(self):
        for claim in ("Les deux CV ont été détachés.", "J'ai classé la note dans Finances.", "C’est classé dans Projets.",
                      "Classé dans Ressources › Articles.", "Voilà. Ajoutée à ta liste d'épicerie.", "Je les ai déplacés."):
            self.assertTrue(core.CHANGE_RE.search(claim), claim)
        for description in ("Le Brain, c’est ton espace pour garder tes idées sous forme de notes reliées entre elles.",
                            "Tu as trois éléments classés dans Cuisine.", "La note créée hier parle du compost."):
            self.assertFalse(core.CHANGE_RE.search(description), description)
