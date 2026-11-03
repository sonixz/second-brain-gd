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
                         {"python", "directories", "venv", "dependencies", "database", "service", "health"})
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
        self.assertTrue(any(n["type"] == "note" for n in g["nodes"]), "first start seeds a welcome graph")
        code, note = get(base + "/notes", tok, "POST", {"title": "API idea", "body": "links [[Engine room]] #api"})
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
