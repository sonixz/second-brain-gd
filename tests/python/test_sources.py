import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from engine import brain, database
from engine.assistant import core as assistant
from engine.assistant.llm import FakeChat
from engine.brain.seed import seed_all
from engine.sources import core, extract
from engine.sources.core import search_any

DOC = ("La migration de données du client Atlas doit se faire en deux phases.\n\n"
       "Phase 1: inventaire des tables. Phase 2: bascule un dimanche.\n\n" + "Détail technique. " * 200)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = self.dir / "s.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_all(self.conn)
        self.client = FakeChat()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_chunking_overlaps_and_covers(self):
        chunks = extract.chunk(DOC, size=500, overlap=50)
        self.assertGreater(len(chunks), 3)
        self.assertTrue(all(len(c) <= 560 for c in chunks))
        self.assertIn("Phase 1", chunks[0])

    def test_html_docx_text_extraction(self):
        title, text = extract.html_to_text("<html><head><title>Atlas &amp; co</title><script>x()</script></head>"
                                           "<body><nav>menu</nav><p>Bonjour <b>monde</b></p><p>Deux</p></body></html>")
        self.assertEqual(title, "Atlas & co")
        self.assertIn("Bonjour monde", text)
        self.assertNotIn("menu", text)
        self.assertNotIn("x()", text)
        docx = self.dir / "a.docx"
        with zipfile.ZipFile(docx, "w") as z:
            z.writestr("word/document.xml", "<w:document><w:body><w:p><w:r><w:t>Plan Atlas</w:t></w:r></w:p>"
                                            "<w:p><w:r><w:t>Phase deux</w:t></w:r></w:p></w:body></w:document>")
        self.assertEqual(extract.from_file(docx)[1], "Plan Atlas\nPhase deux")
        with self.assertRaises(extract.ExtractError):
            extract.from_file(self.dir / "nope.exe")

    def test_url_guard_refuses_local_networks(self):
        for url in ("http://127.0.0.1:8765/system/status", "http://localhost/", "file:///etc/passwd", "http://192.168.1.1/"):
            with self.assertRaises(extract.ExtractError, msg=url):
                extract.from_url(url)

    def test_ingest_file_summary_note_search_dedupe(self):
        f = self.dir / "atlas-plan.md"
        f.write_text(DOC, encoding="utf-8")
        src = core.ingest_file(self.conn, self.client, str(f))
        self.assertEqual(src["status"], "ready")
        self.assertGreater(src["chunks"], 1)
        note = brain.get_note(self.conn, src["note_id"])
        self.assertEqual((note["kind"], note["source"]), ("reference", "import"))
        self.assertIn("Résumé de test.", note["body"])
        self.assertIn("test-source", note["tags"])
        hits = core.search_chunks(self.conn, "migration bascule")
        self.assertTrue(hits and hits[0]["source_id"] == src["id"])
        again = core.ingest_file(self.conn, self.client, str(f))
        self.assertTrue(again["duplicate"])
        core.delete_source(self.conn, src["id"])
        self.assertEqual(core.search_chunks(self.conn, "migration"), [])
        with self.assertRaises(brain.NotFound):
            brain.get_note(self.conn, src["note_id"])

    def test_without_key_still_ingests(self):
        f = self.dir / "n.txt"
        f.write_text(DOC, encoding="utf-8")
        src = core.ingest_file(self.conn, None, str(f))
        self.assertIn("migration", brain.get_note(self.conn, src["note_id"])["body"])

    def test_embeddings_and_meaning_search(self):
        f = self.dir / "a.txt"
        f.write_text(DOC, encoding="utf-8")
        core.ingest_file(self.conn, self.client, str(f))
        self.assertGreater(core.embed_pending(self.conn, self.client, "fake-embed")["embedded"], 0)
        database.set_setting(self.conn, "embeddings_model", "fake-embed")
        res = search_any(self.conn, self.client, "migration Atlas phases", 3)
        self.assertEqual(res[0]["match"], "meaning")

    def test_embeddings_unavailable_is_recorded(self):
        f = self.dir / "a.txt"
        f.write_text(DOC, encoding="utf-8")
        core.ingest_file(self.conn, self.client, str(f))
        with mock.patch.object(FakeChat, "embed", side_effect=RuntimeError("403 no access")):
            out = core.embed_pending(self.conn, self.client, "text-embedding-3-small")
        self.assertEqual(out["embedded"], 0)
        self.assertFalse(database.get_setting(self.conn, "embeddings_status")["available"])
        self.assertEqual(search_any(self.conn, self.client, "migration")[0]["match"], "words")

    def test_assistant_tool_searches_sources(self):
        f = self.dir / "a.txt"
        f.write_text(DOC, encoding="utf-8")
        core.ingest_file(self.conn, self.client, str(f))
        assistant._CLIENT["c"] = self.client
        out = assistant.run_tool(self.conn, "search_sources", {"query": "bascule dimanche"}, [])
        self.assertTrue(out["results"])
        self.assertIn("dimanche", out["results"][0]["excerpt"])


if __name__ == "__main__":
    unittest.main()
