"""Agent room: verified install from the pinned manifest, and a full session against a fake app-server."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from engine.agents import install
from engine.agents.session import AgentError, AgentManager
from engine.paths import Layout

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "agents"


def wait(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.layout = Layout(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_real_manifest_is_pinned_to_official_release(self):
        with mock.patch.dict(os.environ, {"SBGD_AGENTS_MANIFEST": ""}):
            m, _ = install.load_manifest()
        for key in ("windows-x86_64", "linux-x86_64"):
            spec = m["platforms"][key]
            self.assertTrue(spec["url"].startswith("https://github.com/openai/codex/releases/download/" + m["version"] + "/"))
            self.assertRegex(spec["sha256"], r"^[0-9a-f]{64}$")

    def test_install_verifies_and_is_idempotent(self):
        steps = []
        info = install.install(self.layout, lambda st, fr, msg: steps.append(st))
        self.assertFalse(info["already"])
        self.assertTrue(Path(info["binary"]).is_file())
        self.assertIn("verify", steps)
        self.assertFalse(list((self.layout.root / "agents" / "downloads").glob("*")))  # archive cleaned up
        again = install.install(self.layout)
        self.assertTrue(again["already"])
        self.assertIsNotNone(install.installed_info(self.layout))

    def test_wrong_fingerprint_is_refused_and_deleted(self):
        bad = json.loads((FIXTURES / "manifest.json").read_text())
        for spec in bad["platforms"].values():
            spec["sha256"] = "0" * 64
            spec["url"] = str((FIXTURES / "fake-codex.tar.gz").resolve().as_uri())
        path = Path(self.tmp.name) / "bad.json"
        path.write_text(json.dumps(bad))
        with mock.patch.dict(os.environ, {"SBGD_AGENTS_MANIFEST": str(path)}):
            with self.assertRaises(install.InstallError):
                install.install(self.layout)
            self.assertIsNone(install.installed_info(self.layout))
        self.assertFalse(list((self.layout.root / "agents" / "downloads").glob("*.tar.gz")))


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.layout = Layout(root / "data")
        self.binary = install.install(self.layout)["binary"]
        self.work = root / "project"
        self.work.mkdir()
        self.manager = AgentManager(root / "data" / "agents" / "home")

    def tearDown(self):
        self.manager.stop_all()
        self.tmp.cleanup()

    def start(self):
        return self.manager.create(self.binary, self.work, "gpt-6-sol", "sk-test-0000", "untrusted", "read-only")

    def test_file_change_waits_for_approval_then_applies(self):
        s = self.start()
        self.assertEqual(s.status, "idle")
        s.send("please write a notes file")
        self.assertTrue(wait(lambda: s.pending), "an approval request arrives")
        req = next(iter(s.pending.values()))
        self.assertEqual(req["kind"], "file_change")
        self.assertIn("accept", req["decisions"])
        self.assertFalse((self.work / "notes.md").exists())  # nothing happens before the user decides
        snap = s.snapshot()
        self.assertEqual(snap["status"], "waiting_approval")
        self.assertTrue(any(e["type"] == "item" and e["item"].get("type") == "fileChange" for e in snap["events"]))
        s.decide(req["request_id"], "accept")
        self.assertTrue(wait(lambda: s.status == "idle"))
        self.assertTrue((self.work / "notes.md").exists())
        types = [e["type"] for e in s.snapshot()["events"]]
        for t in ("ready", "user", "turn_started", "delta", "approval", "decision", "turn_completed"):
            self.assertIn(t, types)
        later = s.snapshot(after=s.seq)
        self.assertEqual(later["events"], [])  # polling with ?after returns only new events

    def test_declined_command_does_not_run(self):
        s = self.start()
        s.send("run something")
        self.assertTrue(wait(lambda: s.pending))
        req = next(iter(s.pending.values()))
        self.assertEqual(req["kind"], "command")
        self.assertEqual(req["command"], "echo hi")
        s.decide(req["request_id"], "decline")
        self.assertTrue(wait(lambda: s.status == "idle"))
        done = [e["item"] for e in s.snapshot()["events"] if e["type"] == "item" and e["phase"] == "completed"
                and e["item"].get("type") == "commandExecution"]
        self.assertEqual(done[0]["status"], "declined")

    def test_busy_and_bad_decisions_are_refused(self):
        s = self.start()
        s.send("write")
        self.assertTrue(wait(lambda: s.pending))
        with self.assertRaises(AgentError):
            s.send("another")
        with self.assertRaises(AgentError):
            s.decide(999, "accept")
        with self.assertRaises(AgentError):
            s.decide(next(iter(s.pending)), "yolo")

    def test_bad_key_fails_without_leaking_it(self):
        with self.assertRaises(AgentError) as ctx:
            self.manager.create(self.binary, self.work, "m", "not-a-key-SECRET", "untrusted", "read-only")
        self.assertNotIn("SECRET", str(ctx.exception))

    def test_stop_ends_process_and_removes_credentials(self):
        s = self.start()
        (s.home / "auth.json").write_text("{}")
        s.stop()
        self.assertTrue(wait(lambda: s.proc.poll() is not None))
        self.assertFalse((s.home / "auth.json").exists())
        with self.assertRaises(AgentError):
            s.send("hello")

    def test_session_limit(self):
        for _ in range(AgentManager.MAX_SESSIONS):
            self.start()
        with self.assertRaises(AgentError):
            self.start()


if __name__ == "__main__":
    unittest.main()
