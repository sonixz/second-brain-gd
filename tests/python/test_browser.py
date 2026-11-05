"""Browser extension, engine side (2026-11-04): pairing, the command hub, pages sent from a tab, assistant tools."""
import asyncio
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from engine import brain, database
from engine.assistant import core
from engine.assistant.llm import FakeChat
from engine.brain.seed import seed_if_empty
from engine.browser import pairing
from engine.browser.hub import BrowserError, Hub
from engine.sources import core as sources, extract

PAGE = ("<html><head><title>Analyste DevSecOps</title></head><body><nav>Menu Accueil Connexion</nav><main>"
        + "<p>Montréal, hybride. Azure, Sentinel, Bicep, KQL.</p>" * 10 + "</main></body></html>")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        (Path(self.tmp.name) / "data").mkdir()
        self.db = Path(self.tmp.name) / "data" / "second_brain.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_if_empty(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()


class PairingTests(Base):
    def test_code_works_once_and_token_is_stored_hashed(self):
        code = pairing.start(self.conn)["code"]
        token = pairing.complete(self.conn, code.lower(), "Edge 130")  # case and dash do not matter
        self.assertIsNotNone(pairing.verify(self.conn, token))
        self.assertNotIn(token, str(database.get_setting(self.conn, "browser_tokens")))
        with self.assertRaises(pairing.PairingError):
            pairing.complete(self.conn, code, "again")
        self.assertEqual(pairing.paired(self.conn)[0]["browser"], "Edge 130")
        self.assertEqual(pairing.revoke_all(self.conn), 1)
        self.assertIsNone(pairing.verify(self.conn, token))

    def test_expired_code_and_too_many_attempts(self):
        code = pairing.start(self.conn)["code"]
        with mock.patch("engine.browser.pairing.time.time", return_value=time.time() + 601):
            with self.assertRaises(pairing.PairingError):
                pairing.complete(self.conn, code)
        code = pairing.start(self.conn)["code"]
        for _ in range(pairing.MAX_ATTEMPTS):
            with self.assertRaises(pairing.PairingError):
                pairing.complete(self.conn, "WRONGCOD")
        with self.assertRaises(pairing.PairingError):
            pairing.complete(self.conn, code)  # the code died after 5 wrong attempts


class PageTests(Base):
    def test_a_page_from_the_tab_is_kept_and_readable_without_its_menus(self):
        src = sources.ingest_page(self.conn, None, "https://jobs.example.org/7", "Analyste DevSecOps", PAGE, "Menu " + "x" * 50)
        row = sources.get_source(self.conn, src["id"])
        self.assertEqual((row["text_engine"], row["mime"]), ("browser", "text/html"))
        self.assertTrue(row["original"].endswith(".html"))
        text = " ".join(r[0] for r in self.conn.execute("SELECT text FROM source_chunks"))
        self.assertIn("Sentinel", text)
        self.assertNotIn("Connexion", text)  # page chrome dropped

    def test_an_app_page_uses_what_was_on_screen(self):
        shell = "<html><body><div id=app></div><script>render()</script></body></html>"
        src = sources.ingest_page(self.conn, None, "https://app.example.org", "App", shell, "Tableau de bord: 12 tâches ouvertes. " * 20)
        self.assertIn("Tableau de bord", " ".join(r[0] for r in self.conn.execute(
            "SELECT text FROM source_chunks WHERE source_id = ?", (src["id"],))))

    def test_a_pdf_tab_is_downloaded_instead(self):
        from engine.browser.routes import PageIn, needs_download

        viewer = '<html><body style="margin:0"><embed src="about:blank" type="application/pdf"></body></html>'
        self.assertTrue(needs_download(PageIn(url="https://example.org/report.pdf", html=viewer, text="")))
        self.assertTrue(needs_download(PageIn(url="https://example.org/report.pdf")))
        self.assertFalse(needs_download(PageIn(url="https://jobs.example.org/7", html=PAGE, text="")))
        self.assertFalse(needs_download(PageIn(url="https://app.example.org", html="<div id=app></div>", text="Tableau " * 30)))

    def test_only_web_pages(self):
        with self.assertRaises(extract.ExtractError):
            sources.ingest_page(self.conn, None, "file:///C:/secret.txt", "x", PAGE, "")


class HubTests(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.hub = Hub()
        self.sent = []

    def tearDown(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(2)

    def fake_ws(self, answer=True):
        hub, sent = self.hub, self.sent

        class WS:
            async def send_text(self, text):
                import json
                msg = json.loads(text)
                sent.append(msg)
                if answer:
                    threading.Timer(0.05, lambda: hub.resolve(msg["id"], True, {"ref": "7"})).start()
        return WS()

    def test_a_command_waits_for_the_answer(self):
        self.hub.attach(self.fake_ws(), self.loop, {"browser": "Edge"})
        self.assertEqual(self.hub.command("open", {"url": "https://x.org"}), {"ref": "7"})
        self.assertEqual(self.sent[0]["action"], "open")

    def test_no_browser_no_answer_and_disconnect(self):
        with self.assertRaises(BrowserError):
            self.hub.command("open", {})
        ws = self.fake_ws(answer=False)
        self.hub.attach(ws, self.loop, {})
        with self.assertRaises(BrowserError):
            self.hub.command("open", {}, timeout=0.3)
        threading.Timer(0.1, lambda: self.hub.detach(ws)).start()
        with self.assertRaises(BrowserError):
            self.hub.command("close", {}, timeout=5)
        self.assertFalse(self.hub.connected())


class ToolTests(Base):
    def test_without_the_extension_opening_uses_the_system_browser(self):
        core._UI["actions"] = []
        out = core.run_tool(self.conn, "open_web_page", {"url": "https://jobs.example.org/7"}, [])
        self.assertTrue(out["opened"])
        self.assertEqual(core._UI["actions"], [{"action": "open_url", "url": "https://jobs.example.org/7"}])
        out = core.run_tool(self.conn, "capture_browser_tab", {}, [])
        self.assertIn("not connected", out["error"])
        self.assertEqual(core.run_tool(self.conn, "open_web_page", {"url": "file:///etc/passwd"}, [])["error"],
                         "only http/https addresses can be opened")


if __name__ == "__main__":
    unittest.main()
