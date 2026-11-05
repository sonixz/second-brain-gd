"""Pictures from web pages (Loop 25): which ones are kept, what they say, and that they go with their item."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import brain, database
from engine.assistant.llm import FakeChat
from engine.brain.seed import seed_if_empty
from engine.sources import core as sources, extract, images, originals, render

PAGE = ("<html><head><title>Heat pumps in cold climates</title>"
        "<meta property='og:image' content='/media/outdoor-unit.jpg'></head><body>"
        "<header><img src='/img/site-logo.png' alt='Site' width='600' height='200'></header>"
        "<nav><img src='/img/menu.png' width='400' height='300'></nav><main>"
        + "<p>Cold-climate heat pumps keep heating well below freezing.</p>" * 6
        + "<figure><img src='/media/cop-curve.png' alt='COP curve' width='800' height='500'>"
          "<figcaption>Chart: efficiency (COP) against outdoor temperature</figcaption></figure>"
          "<img src='/icons/share-twitter.png' width='300' height='300'>"
          "<img src='/media/tiny.png' width='40' height='40'>"
          "<img src='/media/outdoor-unit.jpg' alt='An outdoor unit in the snow' width='1200' height='800'>"
        "</main><footer><img src='/media/partner.png' width='500' height='300'></footer></body></html>")


def picture(w: int = 400, h: int = 300, shade: int = 90) -> bytes:
    return render.png(bytes([shade, 120, 200, 255]) * (w * h), w, h)


def photo(w: int = 600, h: int = 400) -> bytes:
    """A JPEG's header (what the Brain reads without decoding it): a photo, as most photos on the web are."""
    app0 = b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof = b"\xff\xc0\x00\x11\x08" + h.to_bytes(2, "big") + w.to_bytes(2, "big") + b"\x03" + b"\x01\x22\x00" * 3
    return b"\xff\xd8" + app0 + sof + b"\x00" * 64 + b"\xff\xd9"


class ChoosingTests(unittest.TestCase):
    def test_sizes_from_the_header(self):
        self.assertEqual(images.size_of(picture(400, 300)), (400, 300))
        self.assertEqual((images.sniff(photo()), images.size_of(photo(640, 480))), ("image/jpeg", (640, 480)))
        self.assertEqual(images.sniff(picture()), "image/png")
        self.assertIsNone(images.sniff(b"<svg xmlns='http://www.w3.org/2000/svg'/>"))

    def test_only_the_pictures_that_carry_something(self):
        chosen = images.pick_from_html(PAGE, "https://example.org/articles/ccashp")
        urls = [c["url"] for c in chosen]
        self.assertEqual(urls[0], "https://example.org/media/outdoor-unit.jpg")  # the page's main image first
        self.assertIn("https://example.org/media/cop-curve.png", urls)
        self.assertEqual(len(urls), 2)  # no logo, menu, share icon, tiny picture or footer partner
        fig = next(c for c in chosen if c["url"].endswith("cop-curve.png"))
        self.assertEqual(fig["caption"], "Chart: efficiency (COP) against outdoor temperature")


class LanguageTests(unittest.TestCase):
    def test_the_page_language(self):
        self.assertEqual(images.language("en-CA"), "English")
        self.assertEqual(images.language("fr"), "français")
        self.assertEqual(images.language("", "Les pompes à chaleur sont efficaces dans le froid et pour la maison"), "français")
        self.assertEqual(images.language("", "The heat pump moves heat from the outside air into the house"), "English")
        self.assertEqual(images.html_lang("<!doctype html><html class='x' lang=\"en\" dir='ltr'>"), "en")


class KeepingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        (Path(self.tmp.name) / "data").mkdir()
        self.db = Path(self.tmp.name) / "data" / "second_brain.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_if_empty(self.conn)
        self.env = mock.patch.dict(os.environ, {"SBGD_OCR": "off"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.conn.close()
        self.tmp.cleanup()

    def test_a_page_keeps_its_pictures_and_what_they_say(self):
        pics = [{"url": "https://example.org/media/cop-curve.png", "alt": "COP curve",
                 "caption": "Chart: efficiency against outdoor temperature", "data": picture(800, 500)},
                {"url": "https://example.org/media/photo.jpg", "alt": "", "caption": "", "data": photo(600, 400)},
                {"url": "https://example.org/media/icon.png", "alt": "", "caption": "", "data": picture(40, 40)},
                {"url": "https://example.org/x.svg", "alt": "", "caption": "", "data": b"<svg/>"}]
        src = sources.ingest_page(self.conn, FakeChat(), "https://example.org/articles/ccashp", "Heat pumps",
                                  PAGE, "", None, pics, "en")
        self.assertEqual(src["images"], {"kept": 2, "described": 1})  # the chart is described, the plain photo is not
        self.assertIn("en English", str(FakeChat.last_messages[0]["content"][0]["text"]))  # in the page's language
        kept = images.list_for_source(self.conn, src["id"])
        self.assertEqual([(k["idx"], k["width"]) for k in kept], [(0, 800), (1, 600)])
        self.assertIn("schéma", kept[0]["description"])
        self.assertIsNone(kept[1]["description"])
        hits = sources.search_chunks(self.conn, "efficiency outdoor temperature")
        self.assertTrue(any("[Image 1]" in h["snippet"] or h["source_id"] == src["id"] for h in hits))
        path, mime = images.path_of(self.conn, src["id"], 0)
        self.assertEqual((path.read_bytes()[:4], mime), (b"\x89PNG", "image/png"))
        # deleting the item deletes its pictures too
        brain.delete_note(self.conn, src["note_id"])
        self.assertFalse(path.exists())
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM source_images").fetchone()[0], 0)

    def test_a_picture_shared_by_two_pages_stays_while_one_still_uses_it(self):
        pic = {"url": "https://example.org/a.png", "alt": "Diagram of the cycle", "caption": "", "data": picture(500, 400)}
        a = sources.ingest_page(self.conn, None, "https://example.org/a", "A", PAGE, "", None, [pic])
        b = sources.ingest_page(self.conn, None, "https://example.org/b", "B", PAGE.replace("freezing", "zero"), "", None, [pic])
        path, _ = images.path_of(self.conn, a["id"], 0)
        brain.delete_note(self.conn, a["note_id"])
        self.assertTrue(path.exists())
        brain.delete_note(self.conn, b["note_id"])
        self.assertFalse(path.exists())

    def test_a_link_pasted_downloads_the_chosen_pictures(self):
        def fake_page(url, timeout=20.0):
            return "Heat pumps", extract.html_to_text(PAGE)[1], "text/html", len(PAGE), PAGE.encode()

        got = []

        def fake_image(url, timeout=15.0):
            got.append(url)
            if url.endswith("outdoor-unit.jpg"):
                raise OSError("404")  # one that fails is left out
            return picture(800, 500)

        with mock.patch.object(extract, "from_url_raw", fake_page), mock.patch.object(images, "download", fake_image):
            src = sources.ingest_url(self.conn, FakeChat(), "https://example.org/articles/ccashp")
        self.assertEqual(len(got), 2)
        self.assertEqual(src["images"]["kept"], 1)

    def test_a_picture_chosen_by_right_click_becomes_an_item(self):
        data = picture(640, 480)
        src = sources.ingest_image(self.conn, FakeChat(), data, "https://example.org/articles/ccashp",
                                   "Heat pumps in cold climates", "Refrigeration cycle diagram",
                                   "https://example.org/media/cycle.png")
        self.assertEqual((src["mime"], src["pages"], src["kind"]), ("image/png", 1, "url"))
        note = brain.get_note(self.conn, src["note_id"])
        self.assertEqual(note["title"], "Refrigeration cycle diagram")
        self.assertIn("https://example.org/media/cycle.png", note["body"] + " ".join(
            r[0] for r in self.conn.execute("SELECT text FROM source_chunks WHERE source_id = ?", (src["id"],))))
        again = sources.ingest_image(self.conn, FakeChat(), data, "https://example.org/other", "Other")
        self.assertTrue(again["duplicate"])
        with self.assertRaises(extract.ExtractError):
            sources.ingest_image(self.conn, None, b"<svg/>", "https://example.org/a")
        with self.assertRaises(extract.ExtractError):
            sources.ingest_image(self.conn, None, data, "file:///C:/secret")
