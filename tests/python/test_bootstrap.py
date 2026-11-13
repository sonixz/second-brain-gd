"""Integration tests: real venv, real pip install, real API process.

They need network access to PyPI the first time (pip cache afterwards).
One data folder is installed once per class and reused by the tests.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "engine" / "bootstrap.py"
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def free_port() -> int:
    """A free port below the ephemeral range (49152+ on Windows, 32768+ on
    Linux): connecting to an unused ephemeral port can self-connect."""
    import random

    for _ in range(200):
        port = random.randint(20000, 30000)
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("no free port")


def run_setup(home: Path, *extra: str, timeout: int = 600) -> tuple[int, list[dict]]:
    events = home.parent / f"events-{time.time_ns()}.jsonl"
    cmd = [sys.executable, str(BOOTSTRAP), "setup", "--quiet", "--data-dir", str(home), "--events", str(events),
           *extra]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **NO_WINDOW)
    lines = [json.loads(ln) for ln in events.read_text(encoding="utf-8").splitlines()] if events.exists() else []
    if proc.returncode not in (0, 1):
        raise AssertionError(f"bootstrap crashed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
    return proc.returncode, lines


def get(url: str, token: str | None = None, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return e.code, {}


def stop(home: Path) -> dict:
    out = subprocess.run([sys.executable, str(BOOTSTRAP), "stop", "--data-dir", str(home)], capture_output=True,
                         text=True, timeout=30, **NO_WINDOW)
    return json.loads(out.stdout or "{}")


def by_component(events: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for e in events:
        out.setdefault(e["component"], []).append(e)
    return out


class BootstrapIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="sbgd-test-")
        cls.home = Path(cls.tmp.name) / "home"
        cls.home.mkdir()  # as Godot does (required for Microsoft Store Python)
        cls.port = free_port()
        cls.code, cls.events = run_setup(cls.home, "--port", str(cls.port))

    @classmethod
    def tearDownClass(cls):
        stop(cls.home)
        cls.tmp.cleanup()

    def setUp(self):
        if self.code != 0:
            tail = [e["message"] for e in self.events if e["status"] != "log"][-5:]
            self.fail(f"initial setup failed: {tail}")

    def server(self) -> dict:
        return json.loads((self.home / "runtime" / "server.json").read_text())

    def token(self) -> str:
        return (self.home / "runtime" / "api_token").read_text().strip()

    def test_01_events_follow_protocol(self):
        for e in self.events:
            for key in ("timestamp", "component", "stage", "status", "message"):
                self.assertIn(key, e)
        progress = [e["progress"] for e in self.events if "progress" in e]
        self.assertEqual(progress, sorted(progress), "overall progress must never go backwards")
        final = self.events[-1]
        self.assertEqual((final["component"], final["stage"], final["status"]), ("bootstrap", "done", "ok"))
        # success is announced only after the health step verified the API
        comps = by_component(self.events)
        health_ok = [i for i, e in enumerate(self.events) if e["component"] == "health" and e["status"] == "ok"]
        self.assertTrue(health_ok)
        self.assertLess(health_ok[0], len(self.events) - 1)
        self.assertIn("dependencies", comps)
        self.assertTrue(any(e["status"] == "log" for e in comps["dependencies"]), "pip output is streamed")

    def test_02_files_and_database(self):
        self.assertTrue((self.home / ".venv").is_dir())
        self.assertTrue((self.home / "data" / "second_brain.sqlite3").is_file())
        state = json.loads((self.home / "install_state.json").read_text())
        self.assertTrue(state["installed"])
        self.assertEqual({k for k, v in state["steps"].items() if v["status"] == "ok"},
                         {"python", "directories", "venv", "dependencies", "database", "agents", "service", "health"})
        agents = json.loads((self.home / "agents" / "installed.json").read_text())
        self.assertEqual(agents["version"], "test-1")  # the fixture manifest, never the 160 MB download
        self.assertNotIn(self.token(), (self.home / "logs" / "bootstrap.log").read_text())
        self.assertNotIn(self.token(), (self.home / "logs" / "server.log").read_text())

    def test_03_api_endpoints(self):
        base = f"http://127.0.0.1:{self.server()['port']}"
        code, health = get(base + "/health")
        self.assertEqual(code, 200)
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["database"], "ok")
        for path in ("/system/status", "/system/storage", "/system/events"):
            self.assertEqual(get(base + path)[0], 401, path)
            self.assertEqual(get(base + path, "wrong-token-wrong-token")[0], 401, path)
        code, status = get(base + "/system/status", self.token())
        self.assertEqual(code, 200)
        self.assertTrue(status["python"]["in_venv"])
        self.assertGreaterEqual(status["database"]["schema_version"], 2)
        self.assertGreater(status["process"]["rss_bytes"], 0)
        self.assertEqual(status["process"]["pid"], self.server()["pid"])
        code, storage = get(base + "/system/storage", self.token())
        self.assertEqual(code, 200)
        self.assertGreater(storage["entries"]["venv"]["bytes"], 1_000_000)
        self.assertIsNotNone(storage["disk"]["free_bytes"])
        code, events = get(base + "/system/events?limit=500", self.token())
        self.assertEqual(code, 200)
        components = {e["component"] for e in events["events"]}
        self.assertTrue({"bootstrap", "venv", "database", "api"} <= components)
        self.assertFalse(any(e["status"] == "log" for e in events["events"]))

    def test_04_only_loopback(self):
        port = self.server()["port"]
        with socket.socket() as s:
            s.settimeout(1)
            # the API is bound to 127.0.0.1 only: another local address must not answer
            try:
                hostname_ip = socket.gethostbyname(socket.gethostname())
            except OSError:
                self.skipTest("no non-loopback address")
            if hostname_ip.startswith("127."):
                self.skipTest("hostname resolves to loopback")
            self.assertNotEqual(s.connect_ex((hostname_ip, port)), 0)

    def test_05_rerun_is_idempotent_and_keeps_data(self):
        base = f"http://127.0.0.1:{self.server()['port']}"
        _, before = get(base + "/system/status", self.token())
        pid_before = self.server()["pid"]
        code, events = run_setup(self.home, "--port", str(self.port))
        self.assertEqual(code, 0)
        statuses = {e["component"]: e["status"] for e in events if e["stage"] not in ("begin",)}
        for comp in ("venv", "dependencies", "database", "service"):
            self.assertEqual(statuses[comp], "skipped", comp)
        self.assertEqual(self.server()["pid"], pid_before, "running API is reused")
        _, after = get(base + "/system/status", self.token())
        self.assertEqual(after["database"]["installed_at"], before["database"]["installed_at"])

    def test_06_restart_after_stop_and_resume_after_failure(self):
        res = stop(self.home)
        self.assertTrue(res["stopped"])
        self.assertTrue(res["graceful"])
        self.assertFalse((self.home / "runtime" / "server.json").exists())
        # simulate a dependency step that failed last time: it runs again, the rest is skipped
        state_file = self.home / "install_state.json"
        state = json.loads(state_file.read_text())
        state["steps"]["dependencies"] = {"status": "error", "at": "x"}
        state_file.write_text(json.dumps(state))
        code, events = run_setup(self.home, "--port", str(self.port))
        self.assertEqual(code, 0)
        last = {e["component"]: e["status"] for e in events}
        self.assertEqual(last["venv"], "skipped")
        self.assertEqual(last["dependencies"], "ok")
        self.assertEqual(last["service"], "ok")
        _, ev = get(f"http://127.0.0.1:{self.server()['port']}/system/events?limit=200", self.token())
        self.assertTrue(any(e["component"] == "api" and e["stage"] == "stop" for e in ev["events"]))

    def test_07_busy_port_falls_back(self):
        stop(self.home)
        with socket.socket() as blocker:
            busy = free_port()
            blocker.bind(("127.0.0.1", busy))
            blocker.listen(1)
            code, events = run_setup(self.home, "--port", str(busy))
        self.assertEqual(code, 0)
        self.assertTrue(any(e["component"] == "service" and e["status"] == "warning" for e in events))
        self.assertNotEqual(self.server()["port"], busy)

    def test_08_parent_watchdog_stops_api(self):
        stop(self.home)
        parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], **NO_WINDOW)
        try:
            code, _ = run_setup(self.home, "--port", str(self.port), "--parent-pid", str(parent.pid))
            self.assertEqual(code, 0)
            port = self.server()["port"]
            self.assertEqual(get(f"http://127.0.0.1:{port}/health")[0], 200)
        finally:
            parent.kill()
            parent.wait()
        deadline = time.time() + 10
        alive = True
        while time.time() < deadline:
            try:
                get(f"http://127.0.0.1:{port}/health")
            except OSError:
                alive = False
                break
            time.sleep(0.2)
        self.assertFalse(alive, "API must exit when its parent process exits")
        time.sleep(0.5)
        self.assertFalse((self.home / "runtime" / "server.json").exists())

    def test_99_offline_agent_room_does_not_block_setup(self):
        manifest = json.loads((ROOT / "tests" / "fixtures" / "agents" / "manifest.json").read_text())
        manifest["version"] = "unreachable-1"
        for spec in manifest["platforms"].values():
            spec["url"] = "http://127.0.0.1:9/nothing.tar.gz"
        path = self.home.parent / "offline-manifest.json"
        path.write_text(json.dumps(manifest))
        old = os.environ.get("SBGD_AGENTS_MANIFEST")
        os.environ["SBGD_AGENTS_MANIFEST"] = str(path)
        try:
            code, events = run_setup(self.home, "--no-start")
        finally:
            os.environ["SBGD_AGENTS_MANIFEST"] = old or ""
        self.assertEqual(code, 0, "setup succeeds without the agent room: %s" % [e["message"] for e in events if e["status"] in ("error", "unavailable")])
        agent_events = [e for e in events if e["component"] == "agents"]
        self.assertEqual(agent_events[-1]["status"], "unavailable")
        self.assertIn("retry", agent_events[-1]["message"])
        self.assertEqual(events[-1]["status"], "ok")

    def test_09_concurrent_setup_is_refused(self):
        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], **NO_WINDOW)
        try:
            (self.home / "runtime" / "bootstrap.lock").write_text(str(sleeper.pid))
            code, events = run_setup(self.home, "--no-start")
            self.assertEqual(code, 1)
            self.assertIn("Another setup", " ".join(e["message"] for e in events))
        finally:
            sleeper.kill()
            sleeper.wait()
        code, _ = run_setup(self.home, "--no-start")
        self.assertEqual(code, 0, "a stale lock from a dead process is ignored")

    def test_10_running_api_is_reattached_to_a_new_parent(self):
        code, _ = run_setup(self.home, "--port", str(self.port))
        self.assertEqual(code, 0)
        first = self.server()
        parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], **NO_WINDOW)
        try:
            code, events = run_setup(self.home, "--port", str(self.port), "--parent-pid", str(parent.pid))
            self.assertEqual(code, 0)
            second = self.server()
            self.assertNotEqual(first["pid"], second["pid"])
            self.assertEqual(second["parent_pid"], parent.pid)
            self.assertTrue(any(e["stage"] == "reattach" for e in events))
        finally:
            parent.kill()
            parent.wait()

    def test_11_brain_api(self):
        code, _ = run_setup(self.home, "--port", str(self.port))
        self.assertEqual(code, 0)
        base = f"http://127.0.0.1:{self.server()['port']}/brain"
        tok = self.token()
        self.assertEqual(get(base + "/graph")[0], 401)
        code, g = get(base + "/graph", tok)
        self.assertEqual(code, 200)
        self.assertTrue(any(n["type"] == "note" for n in g["nodes"]), "first start seeds the Getting started guide")
        self.assertFalse(any(n["type"] == "space" and n.get("kind") == "area" for n in g["nodes"]), "no preset areas")
        code, note = get(base + "/notes", tok, "POST", {"title": "API idea", "body": "links [[Capturer n'importe quoi]] #api"})
        self.assertEqual(code, 201)
        self.assertEqual(note["space_id"], "inbox")
        self.assertEqual(len(note["links_out"]), 1)
        code, found = get(base + "/search?q=api", tok)
        self.assertIn(note["id"], [r["id"] for r in found["results"]])
        code, patched = get(base + f"/notes/{note['id']}", tok, "PATCH", {"title": "API idea 2"})
        self.assertEqual((code, patched["title"]), (200, "API idea 2"))
        self.assertEqual(get(base + "/notes", tok, "POST", {"title": ""})[0], 422)
        self.assertEqual(get(base + "/notes/nope", tok)[0], 404)
        code, sp = get(base + "/spaces", tok, "POST", {"name": "Client X"})
        self.assertEqual(code, 201)
        code, brief = get(base + "/briefing", tok)
        self.assertEqual(code, 200)
        self.assertGreaterEqual(brief["totals"]["notes"], 5)
        self.assertEqual(get(base + f"/notes/{note['id']}", tok, "DELETE")[0], 204)

    def test_12_voice_api_and_stream(self):
        stop(self.home)
        os.environ["SBGD_VOICE_PROVIDER"] = "fake"   # the server inherits it: no OpenAI call, no cost
        os.environ["SBGD_ASSISTANT_PROVIDER"] = "fake"
        os.environ["SBGD_BILLING_PROVIDER"] = "fake"
        try:
            code, _ = run_setup(self.home, "--port", str(self.port))
        finally:
            os.environ.pop("SBGD_VOICE_PROVIDER", None)
            os.environ.pop("SBGD_ASSISTANT_PROVIDER", None)
            os.environ.pop("SBGD_BILLING_PROVIDER", None)
        self.assertEqual(code, 0)
        port, tok = self.server()["port"], self.token()
        base = f"http://127.0.0.1:{port}/voice"
        self.assertEqual(get(base + "/status")[0], 401)
        code, st = get(base + "/status", tok)
        self.assertEqual(code, 200)
        self.assertEqual(st["model"], "gpt-realtime-whisper")
        self.assertNotIn("api_key", json.dumps(st))
        # A made-up key is checked against OpenAI and refused (or saved with a warning when offline).
        code, res = get(base + "/key", tok, "PUT", {"api_key": "sk-proj-not-a-real-key-000000000000"})
        self.assertIn(code, (422, 200))
        if code == 200:
            self.assertFalse(res["check"]["ok"])
            get(base + "/key", tok, "DELETE")
        # The WebSocket refuses a wrong token, then streams with the right one.
        venv_py = str(self.home / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python"))
        client = str(ROOT / "tests" / "python" / "voice_client.py")
        pcm = self.home / "tone.pcm"
        pcm.write_bytes(b"\x10\x00" * 24000 * 2)  # 2 s of audio
        bad = subprocess.run([venv_py, client, "stream", str(port), "wrong-token", str(pcm)], capture_output=True,
                             text=True, timeout=60, **NO_WINDOW)
        self.assertNotEqual(bad.returncode, 0, "a wrong token must not open a voice session")
        ok = subprocess.run([venv_py, client, "stream", str(port), tok, str(pcm)], capture_output=True, text=True,
                            timeout=60, **NO_WINDOW)
        self.assertEqual(ok.returncode, 0, ok.stderr[-800:])
        out = json.loads(ok.stdout.strip().splitlines()[-1])
        self.assertEqual(out["messages"][0]["type"], "ready")
        self.assertEqual(out["finals"], ["[fake transcript of 2.0 s of audio]"])
        self.assertTrue(out["deltas"])
        found = False
        for _ in range(30):  # the session-closed event is written right after the socket closes
            _, ev = get(f"http://127.0.0.1:{port}/system/events?limit=50", tok)
            found = any(e["component"] == "voice" and "2.0 s of audio" in e["message"] for e in ev["events"])
            if found:
                break
            time.sleep(0.1)
        self.assertTrue(found, "the voice session is recorded with its duration and estimated cost")
        # Assistant routes (fake provider, still running in this server)
        a = f"http://127.0.0.1:{port}/assistant"
        self.assertEqual(get(a + "/status")[0], 401)
        code, st = get(a + "/status", tok)
        self.assertEqual((code, st["configured"], st["assistant_voice"]), (200, True, "marin"))
        code, out = get(a + "/chat", tok, "POST", {"text": "cherche capturer"})
        self.assertEqual(code, 200)
        self.assertTrue(out["cited"])
        code, b = get(a + "/briefing", tok, "POST")
        self.assertEqual(code, 200)
        self.assertTrue(b["text"])
        code, h = get(a + "/history", tok)
        self.assertEqual([m["role"] for m in h["messages"]], ["user", "assistant", "briefing"])
        req = urllib.request.Request(a + "/speak", data=json.dumps({"text": "Bonjour"}).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            self.assertEqual(r.headers["Content-Type"], "audio/mpeg")
            self.assertGreater(len(r.read()), 1000)
        # Live conversation (Loop 7b) through the real route, fake Realtime upstream: 3 spoken turns.
        lv = subprocess.run([venv_py, client, "live", str(port), tok, "3"], capture_output=True, text=True,
                            timeout=90, **NO_WINDOW)
        self.assertEqual(lv.returncode, 0, lv.stderr[-800:])
        res = json.loads(lv.stdout.strip().splitlines()[-1])
        self.assertEqual(res["types"][0], "ready")
        self.assertIn({"action": "open_view", "view": "projects"}, res["ui_actions"])
        self.assertEqual(res["user_text"][0], "Montre-moi mes projets.")
        self.assertGreater(res["audio_bytes"], 10000)
        self.assertEqual(res["ended"], "goodbye")
        # the engine does not close on the heels of « ended »: Godot reads why, then closes its side
        self.assertTrue(res["open_after_ended"], "the socket closed right behind « ended »")
        self.assertGreater(res["cost"], 0)
        bad = subprocess.run([venv_py, client, "live", str(port), "wrong-token", "1"], capture_output=True, text=True,
                             timeout=60, **NO_WINDOW)
        self.assertNotEqual(bad.returncode, 0, "a wrong token must not open a live conversation")
        code, st = get(base + "/status", tok)
        self.assertEqual(st["live"]["model"], "gpt-realtime-2.1-mini")
        # « Envoyer au Brain » from a browser (Loop 9): a bookmarklet opens /capture with a capture key.
        code, link = get(f"http://127.0.0.1:{port}/brain/capture-link", tok)
        self.assertEqual(code, 200)
        self.assertTrue(link["bookmarklet"].startswith("javascript:"))
        ckey = link["bookmarklet"].split("key=", 1)[1].split("&", 1)[0]
        def page(q):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/capture?" + urllib.parse.urlencode(q), timeout=30) as r:
                    return r.status, r.read().decode("utf-8")
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8")
        code, body = page({"key": "wrong", "url": "https://example.org/a"})
        self.assertEqual(code, 400)
        self.assertIn("Invalid capture link", body)  # English, the app's default language
        code, st = get(f"http://127.0.0.1:{port}/assistant/settings", tok, "PATCH", {"language": "fr"})
        self.assertEqual((code, st["ui_language"]), (200, "fr"))
        code, body = page({"key": "wrong", "url": "https://example.org/a"})
        self.assertIn("Lien de capture invalide", body)  # the FR / EN switch reaches the engine's own words
        get(f"http://127.0.0.1:{port}/assistant/settings", tok, "PATCH", {"language": "en"})
        code, body = page({"key": ckey, "url": "https://example.org/sommeil", "title": "Dormir mieux",
                           "text": "Une routine du soir régulière améliore le sommeil."})
        self.assertEqual(code, 200, body[-400:])
        self.assertIn("Added to your Brain", body)
        code, feed = get(f"http://127.0.0.1:{port}/brain/feed?limit=5", tok)
        top = feed["items"][0]
        self.assertEqual((top["title"], top["origin"], top["origin_uri"]), ("Dormir mieux", "url", "https://example.org/sommeil"))
        self.assertTrue(top["filed"])
        # Originals and the document viewer (Loop 12): the PDF is kept, its pages come back as images.
        fx = ROOT / "tests" / "fixtures" / "docs"
        code, src = get(f"http://127.0.0.1:{port}/sources/file", tok, "POST", {"path": str(fx / "sample.pdf")})
        self.assertEqual(code, 201, src)
        code, doc = get(f"http://127.0.0.1:{port}/sources/{src['id']}/document", tok)
        self.assertEqual((doc["kind"], doc["pages"], doc["viewable"]), ("pdf", 2, True))
        self.assertTrue(Path(doc["original_path"]).is_file())
        self.assertIn("originals", doc["original_path"])
        req = urllib.request.Request(f"http://127.0.0.1:{port}/sources/{src['id']}/page/2?width=700",
                                     headers={"Authorization": f"Bearer {tok}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            self.assertEqual(r.headers["Content-Type"], "image/png")
            self.assertEqual(r.read()[:8], b"\x89PNG\r\n\x1a\n")
        code, _ = get(f"http://127.0.0.1:{port}/sources/{src['id']}/page/9", tok)
        self.assertEqual(code, 422)
        code, img = get(f"http://127.0.0.1:{port}/sources/file", tok, "POST", {"path": str(fx / "sample.png")})
        self.assertEqual(code, 201, img)
        req = urllib.request.Request(f"http://127.0.0.1:{port}/sources/{img['id']}/page/1",
                                     headers={"Authorization": f"Bearer {tok}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            self.assertEqual(r.headers["Content-Type"], "image/png")
        code, item = get(f"http://127.0.0.1:{port}/brain/items/{img['note_id']}", tok)
        self.assertEqual(item["source"]["pages"], 1)
        code, storage = get(f"http://127.0.0.1:{port}/system/storage", tok)
        self.assertGreater(storage["entries"]["originals"]["files"], 1)
        # Browser extension (2026-11-04): pairing, live commands from the assistant, a page sent from the tab.
        bc = subprocess.run([venv_py, str(ROOT / "tests" / "python" / "browser_client.py"), str(port), tok],
                            capture_output=True, text=True, timeout=120, **NO_WINDOW)
        self.assertEqual(bc.returncode, 0, bc.stderr[-1200:])
        b = json.loads(bc.stdout.strip().splitlines()[-1])
        self.assertEqual((b["wrong_code"], b["paired"], b["code_reused"], b["capture_without_token"]), (403, 200, 403, 401))
        self.assertEqual((b["welcome"], b["status_connected"]), ("welcome", True))
        self.assertEqual(b["commands"], ["open", "capture", "close"])
        self.assertEqual(b["replies"][0], "Ouvert.")
        self.assertIn("Analyste DevSecOps", b["replies"][1])
        self.assertEqual(b["replies"][2], "Fermé.")
        self.assertGreaterEqual(b["rev"], 1)
        self.assertEqual((b["unpair"], b["capture_after_unpair"]), (1, 401))
        # Real costs: read live from OpenAI's shapes (fake pages here), never stored.
        bl = f"http://127.0.0.1:{port}/billing"
        self.assertEqual(get(bl)[0], 401)
        code, st = get(bl + "/status", tok)
        self.assertEqual((code, st["configured"]), (200, True))
        code, data = get(bl + "?days=30", tok)
        self.assertEqual(code, 200)
        self.assertEqual(len(data["days"]), 30)
        self.assertGreater(data["month"], 0)
        self.assertTrue(data["models"])
        code, again = get(bl + "?days=30", tok)
        self.assertTrue(again["cached"])
        code, res = get(bl + "/key", tok, "PUT", {"api_key": "sk-admin-not-a-real-key-0000000000"})
        self.assertIn(code, (422, 200))  # refused by OpenAI (401), or saved when offline
        if code == 200:
            get(bl + "/key", tok, "DELETE")

    def test_13_os_credential_store_roundtrip(self):
        venv_py = str(self.home / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python"))
        out = subprocess.run([venv_py, str(ROOT / "tests" / "python" / "voice_client.py"), "keyring-roundtrip"],
                             capture_output=True, text=True, timeout=60, cwd=str(ROOT), **NO_WINDOW)
        self.assertEqual(out.returncode, 0, out.stderr[-800:])
        res = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertTrue(res["match"])
        self.assertTrue(res["deleted"])
        self.assertEqual(res["hint"], "••••cdef")
        if sys.platform == "win32":
            self.assertEqual(res["where"], "keyring", "Windows must use the Credential Manager")


class DetectCommand(unittest.TestCase):
    def test_detect_reports_json(self):
        out = subprocess.run([sys.executable, str(BOOTSTRAP), "detect"], capture_output=True, text=True,
                             timeout=60, **NO_WINDOW)
        info = json.loads(out.stdout)
        self.assertTrue(info["compatible"])
        self.assertTrue(info["venv_available"])
        self.assertEqual(out.returncode, 0)


if __name__ == "__main__":
    unittest.main()
