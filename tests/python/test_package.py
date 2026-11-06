"""The app's own Python (Loop 28): the installer recognises it, skips the virtual environment, runs the engine
with it; the agent room is downloaded only on demand. The package build's pure parts are checked too."""
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine.installer import steps
from engine.paths import Layout

ROOT = Path(__file__).resolve().parents[2]


class _Events:
    def __init__(self):
        self.seen = []

    def add_listener(self, fn):
        pass

    def emit(self, component, stage, status, message, progress=None, **details):
        self.seen.append((component, stage, status, message))

    def close(self):
        pass


class BundledRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.layout = Layout(Path(self.tmp.name))
        self.layout.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _installer(self, marker):
        with mock.patch.object(steps, "bundled_runtime", return_value=marker):
            inst = steps.Installer(self.layout, _Events())
        inst._mark = lambda *a, **k: None
        inst.state = {}
        return inst

    def test_the_marker_is_found_next_to_the_interpreter(self):
        prefix = Path(self.tmp.name) / "python"
        prefix.mkdir()
        (prefix / "sbgd-runtime.json").write_text(json.dumps({"format": "sbgd-runtime", "lock_sha256": "x"}))
        with mock.patch.object(sys, "prefix", str(prefix)), mock.patch.object(sys, "base_prefix", str(prefix)):
            self.assertEqual(steps.bundled_runtime()["lock_sha256"], "x")
        self.assertIsNone(steps.bundled_runtime())  # the test runner's Python is not the app's

    def test_no_virtual_environment_with_the_apps_python(self):
        inst = self._installer({"format": "sbgd-runtime", "lock_sha256": steps.lock_sha256()})
        inst.step_venv()
        self.assertEqual(inst.engine_python(), Path(sys.executable))
        self.assertFalse(self.layout.venv.exists())
        self.assertEqual(inst.events.seen[-1][2], "skipped")

    def test_packages_built_from_another_lock_are_refused(self):
        inst = self._installer({"format": "sbgd-runtime", "lock_sha256": "0" * 64})
        with self.assertRaises(steps.SetupFailed):
            inst.step_dependencies()

    def test_packages_from_this_lock_are_checked_not_reinstalled(self):
        inst = self._installer({"format": "sbgd-runtime", "lock_sha256": steps.lock_sha256()})
        with mock.patch.object(inst, "_deps_importable", return_value=True), \
                mock.patch.object(steps.subprocess, "Popen", side_effect=AssertionError("pip must not run")):
            inst.step_dependencies()
        self.assertEqual(inst.events.seen[-1][2], "skipped")


class AgentRoomOnDemandTests(unittest.TestCase):
    def test_setup_does_not_download_the_agent_room_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            inst = steps.Installer(Layout(Path(tmp)), _Events())
            inst._mark = lambda *a, **k: None
            with mock.patch.dict(os.environ, {"SBGD_AGENTS": ""}), \
                    mock.patch("engine.agents.install.install", side_effect=AssertionError("no download at setup")):
                inst.step_agents()
            self.assertIn("only if you open it", inst.events.seen[-1][3])


class BuildScriptTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("build", ROOT / "tools" / "package" / "build.py")
        self.build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.build)

    def test_pins_are_complete(self):
        for target, pin in self.build.PINS["targets"].items():
            self.assertRegex(pin["sha256"], r"^[0-9a-f]{64}$", target)
            self.assertIn(self.build.PINS["release"], pin["file"], target)
            self.assertTrue(pin["file"].startswith("cpython-" + self.build.PINS["python"]), target)

    def test_a_wrong_download_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(self.build, "CACHE", Path(tmp)):
            pin = self.build.PINS["targets"]["linux"]
            (Path(tmp) / pin["file"]).write_bytes(b"not the archive")
            with mock.patch.object(self.build.urllib.request, "urlopen", return_value=io.BytesIO(b"still not it")):
                with self.assertRaises(SystemExit):
                    self.build.fetch("linux")
            self.assertFalse((Path(tmp) / pin["file"]).exists())
