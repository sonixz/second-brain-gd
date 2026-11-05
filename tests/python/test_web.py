"""Internet access (2026-11-04): search, read a page, add it only when asked; web content stays data."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import brain, database
from engine.assistant import core
from engine.assistant.llm import FakeChat, parse_web_search
from engine.brain.seed import seed_if_empty
from engine.sources import extract

PAGE = "Offre: Analyste DevSecOps à Montréal. Azure, Sentinel, Bicep. Hybride, 2 jours au bureau. " * 8


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "w.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_if_empty(self.conn)
        self.client = FakeChat()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_search_answers_with_sources_and_adds_nothing(self):
        before = self.conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        out = core.chat(self.conn, self.client, "Cherche sur le web des offres DevSecOps à Montréal")
        self.assertIn("Sur le web", out["reply"])
        self.assertEqual([s["url"] for s in out["sources"]], ["https://example.com/emplois/devsecops", "https://example.org/guide"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0], before)
        saved = core.history(self.conn, core.today_conversation())[-1]
        self.assertEqual(len(saved["meta"]["sources"]), 2)  # the links come back with the conversation
        self.assertTrue(self.conn.execute("SELECT 1 FROM system_events WHERE stage = 'web_search'").fetchone())

    def test_read_a_page_without_keeping_it(self):
        actions = []
        with mock.patch.object(extract, "from_url", return_value=("Analyste DevSecOps", PAGE, "text/html", len(PAGE))):
            out = core.run_tool(self.conn, "read_web_page", {"url": "https://jobs.example.com/1"}, actions)
        self.assertIn("Sentinel", out["text"])
        self.assertEqual(actions, [])
        self.assertIsNone(self.conn.execute("SELECT 1 FROM sources").fetchone())

    def test_add_a_page_when_asked_files_it_and_undo_removes_it(self):
        actions = []
        raw = ("<html><title>Analyste DevSecOps</title><body><p>" + PAGE + "</p></body></html>").encode()
        with mock.patch.object(extract, "from_url_raw", return_value=("Analyste DevSecOps", PAGE, "text/html", len(raw), raw)):
            core._CLIENT["c"] = self.client
            out = core.run_tool(self.conn, "add_web_page", {"url": "https://jobs.example.com/1"}, actions)
        self.assertEqual(out["changed"], 1)
        nid = actions[0]["note_id"]
        self.assertNotEqual(brain.get_note(self.conn, nid)["space_id"], "inbox")  # the archivist filed it
        core.undo(self.conn, actions[0]["action_id"])
        self.assertIsNone(self.conn.execute("SELECT 1 FROM notes WHERE id = ?", (nid,)).fetchone())
        self.assertIsNone(self.conn.execute("SELECT 1 FROM sources").fetchone())  # its document went too

    def test_a_site_that_blocks_reading_becomes_a_reference_card(self):
        actions = []
        core._CLIENT["c"] = self.client
        with mock.patch.object(extract, "from_url_raw", side_effect=extract.ExtractError("HTTP 403")):
            refused = core.run_tool(self.conn, "add_web_page", {"url": "https://jobs.example.com/2"}, actions)
            self.assertEqual(refused["changed"], 0)
            out = core.run_tool(self.conn, "add_web_page", {"url": "https://jobs.example.com/2", "title": "Développeur DevSecOps — Groupe SII",
                                                            "summary": "Poste senior, hybride, publié le 8 octobre 2026."}, actions)
        self.assertEqual(out["changed"], 1)
        note = brain.get_note(self.conn, actions[0]["note_id"])
        self.assertIn("https://jobs.example.com/2", note["body"])
        self.assertIn("refuse la lecture", note["body"])

    def test_internet_can_be_turned_off(self):
        database.set_setting(self.conn, "web_access", False)
        out = core.run_tool(self.conn, "web_search", {"query": "x"}, [])
        self.assertIn("turned off", out["error"])

    def test_private_addresses_are_refused(self):
        out = core.run_tool(self.conn, "read_web_page", {"url": "http://127.0.0.1:8765/brain/graph"}, [])
        self.assertIn("error", out)

    def test_openai_citations_become_clean_sources(self):
        data = {"output": [{"type": "message", "content": [{
            "text": "Astek recrute ([emplois.ca](https://www.emplois.ca/x?utm_source=openai)).",
            "annotations": [{"type": "url_citation", "url": "https://www.emplois.ca/x?utm_source=openai", "title": "Astek"}]}]}],
            "usage": {"input_tokens": 5, "output_tokens": 2}}
        out = parse_web_search(data, "gpt-4o-mini")
        self.assertEqual(out["text"], "Astek recrute.")
        self.assertEqual(out["sources"], [{"title": "Astek", "url": "https://www.emplois.ca/x"}])


if __name__ == "__main__":
    unittest.main()
