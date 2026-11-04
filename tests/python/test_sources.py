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

try:  # the PDF libraries live in the engine's venv; a bare system Python skips these tests
    import pypdf, pypdfium2  # noqa: F401
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

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


class OriginalTests(unittest.TestCase):
    """Loop 12: every file and page is kept in <data>/originals, images are described and searchable."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        self.db = self.root / "data" / "second_brain.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_all(self.conn)
        self.client = FakeChat()
        self.fixtures = Path(__file__).resolve().parent.parent / "fixtures" / "docs"

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_original_is_kept_once_and_survives_the_file(self):
        from engine.sources import originals
        f = self.root / "outside" / "plan.md"
        f.parent.mkdir()
        f.write_text("# Plan\n\n" + DOC, encoding="utf-8")
        src = core.ingest_file(self.conn, self.client, str(f))
        rel = core.get_source(self.conn, src["id"])["original"]
        self.assertTrue(rel.startswith("originals/") and rel.endswith(".md"))
        kept = originals.resolve(self.root, rel)
        self.assertEqual(kept.read_text(encoding="utf-8"), f.read_text(encoding="utf-8"))
        copy = self.root / "outside" / "copie.md"
        copy.write_bytes(f.read_bytes())
        f.unlink()  # the user deletes the file: the Brain still has it
        self.assertTrue(kept.is_file())
        self.assertEqual(originals.keep_file(self.root, copy)[0], rel)  # same content, same original
        self.assertEqual(len(list((self.root / "originals").rglob("*.md"))), 1)

    def test_resolve_refuses_paths_outside_originals(self):
        from engine.sources import originals
        (self.root / "secret.txt").write_text("x")
        self.assertIsNone(originals.resolve(self.root, "../secret.txt"))
        self.assertIsNone(originals.resolve(self.root, "originals/../secret.txt"))
        self.assertIsNone(originals.resolve(self.root, None))

    def test_an_image_is_kept_described_and_found(self):
        src = core.ingest_file(self.conn, self.client, str(self.fixtures / "sample.png"))
        row = core.get_source(self.conn, src["id"])
        self.assertEqual((row["mime"], row["pages"]), ("image/png", 1))
        self.assertTrue(row["original"].endswith(".png"))
        note = brain.get_note(self.conn, row["note_id"])
        self.assertIn("schéma", note["body"])  # the vision description is searchable text
        hits = brain.search(self.conn, "schéma", 5)
        self.assertIn(row["note_id"], [h["id"] for h in hits])

    def _picture_pdf(self, pages=2):
        """A PDF whose pages are drawings only (no text layer), like a scan or a pdf-lib image export."""
        objs = []
        def add(b):
            objs.append(b)
            return len(objs)
        pages_id = 1 + 2 * pages
        kids = []
        for i in range(pages):
            draw = b"0.2 0.4 0.8 rg 72 600 %d 120 re f" % (200 + 40 * i)
            c = add(b"<< /Length %d >>\nstream\n" % len(draw) + draw + b"\nendstream")
            kids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 595 842] /Contents %d 0 R >>" % (pages_id, c)))
        add(b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % k for k in kids) + b"] /Count %d >>" % pages)
        cat = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
        out, offs = bytearray(b"%PDF-1.4\n"), []
        for i, body in enumerate(objs, 1):
            offs.append(len(out))
            out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
        x = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
        out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, cat, x)
        f = self.root / "scan.pdf"
        f.write_bytes(bytes(out))
        return f

    def _events(self, stage):
        return self.conn.execute("SELECT COUNT(*) FROM system_events WHERE stage = ?", (stage,)).fetchone()[0]

    def _chunks(self, sid):
        return " ".join(r[0] for r in self.conn.execute("SELECT text FROM source_chunks WHERE source_id = ?", (sid,)))

    @unittest.skipUnless(HAS_PDF, "pypdf/pypdfium2 not installed")
    def test_a_pdf_of_page_images_is_read_locally_first(self):
        src = core.ingest_file(self.conn, self.client, str(self._picture_pdf(2)))
        row = core.get_source(self.conn, src["id"])
        self.assertEqual((row["mime"], row["pages"], row["text_engine"]), ("application/pdf", 2, "ocr-fake"))
        self.assertEqual(self._events("read_scanned_page"), 0)  # nothing sent to the vision model
        self.assertIn("Guide du compost", self._chunks(src["id"]))  # what the OCR read is searchable

    @unittest.skipUnless(HAS_PDF, "pypdf/pypdfium2 not installed")
    def test_ai_mode_sends_the_pages_to_the_vision_model(self):
        database.set_setting(self.conn, "ocr_mode", "ai")
        src = core.ingest_file(self.conn, self.client, str(self._picture_pdf(2)))
        self.assertEqual(core.get_source(self.conn, src["id"])["text_engine"], "ocr-ai")
        self.assertEqual(self._events("read_scanned_page"), 2)  # one vision call per page
        self.assertIn("schéma", self._chunks(src["id"]))

    @unittest.skipUnless(HAS_PDF, "pypdf/pypdfium2 not installed")
    def test_without_local_ocr_the_key_is_the_fallback(self):
        with mock.patch.dict("os.environ", {"SBGD_OCR": "off"}):
            src = core.ingest_file(self.conn, self.client, str(self._picture_pdf(1)))
            self.assertEqual(core.get_source(self.conn, src["id"])["text_engine"], "ocr-ai")
            with self.assertRaises(extract.ExtractError) as ctx:
                core.ingest_file(self.conn, None, str(self._picture_pdf(2)))
        self.assertIn("tesseract", str(ctx.exception))  # says how to get a local OCR

    @unittest.skipUnless(HAS_PDF, "pypdf/pypdfium2 not installed")
    def test_failed_local_ocr_falls_back_or_says_why(self):
        from engine.sources import ocr
        with mock.patch.object(ocr, "read_images", side_effect=ocr.OcrError("boom")):
            src = core.ingest_file(self.conn, self.client, str(self._picture_pdf(1)))
            self.assertEqual(core.get_source(self.conn, src["id"])["text_engine"], "ocr-ai")
            with self.assertRaises(extract.ExtractError) as ctx:
                core.ingest_file(self.conn, None, str(self._picture_pdf(2)))
        self.assertIn("boom", str(ctx.exception))

    @unittest.skipUnless(HAS_PDF, "pypdf/pypdfium2 not installed")
    def test_reread_with_ai_replaces_the_local_reading(self):
        src = core.ingest_file(self.conn, self.client, str(self._picture_pdf(2)))
        out = core.reread_with_ai(self.conn, self.client, src["id"])
        self.assertEqual(out["text_engine"], "ocr-ai")
        text = self._chunks(src["id"])
        self.assertIn("schéma", text)
        self.assertNotIn("Guide du compost", text)  # the local reading is replaced, not doubled

    def test_text_inside_an_image_is_read_locally(self):
        src = core.ingest_file(self.conn, None, str(self.fixtures / "sample.png"))  # no key: still searchable
        note = brain.get_note(self.conn, core.get_source(self.conn, src["id"])["note_id"])
        self.assertIn("Texte dans l'image", note["body"])
        self.assertIn("compost", note["body"])

    def test_a_web_page_keeps_its_raw_copy(self):
        html = b"<html><head><title>Compost</title></head><body><p>" + ("Le compost aime l'air. " * 20).encode() + b"</p></body></html>"
        with mock.patch.object(extract, "from_url_raw", return_value=("Compost", "Le compost aime l'air. " * 20, "text/html", len(html), html)):
            src = core.ingest_url(self.conn, self.client, "https://example.org/compost")
        rel = core.get_source(self.conn, src["id"])["original"]
        self.assertTrue(rel.endswith(".html"))
        self.assertEqual((self.root / rel).read_bytes(), html)


if __name__ == "__main__":
    unittest.main()
