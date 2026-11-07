"""Loop MCP-F: local MCP servers (stdio) — approval of the exact command, pinned versions, the runtime detected not
installed, a clean environment with only declared variables, restart after a crash, the log."""
import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from engine import database
from engine.brain.seed import seed_all
from engine.mcp import catalog, client as mcp, local

SERVER = textwrap.dedent('''
    import json, os, sys
    sys.stderr.write("tiny server started\\n"); sys.stderr.flush()
    for line in sys.stdin:
        msg = json.loads(line)
        if "id" not in msg:
            continue
        m = msg["method"]
        if m == "initialize":
            res = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "tiny"}}
        elif m == "tools/list":
            res = {"tools": [{"name": "env_check", "annotations": {"readOnlyHint": True}, "inputSchema": {"type": "object"}},
                             {"name": "crash", "annotations": {"readOnlyHint": True}, "inputSchema": {"type": "object"}}]}
        elif msg["params"]["name"] == "crash":
            sys.exit(3)
        else:
            res = {"content": [{"type": "text", "text": json.dumps({"declared": os.environ.get("TINY_TOKEN"),
                   "brain_secret": os.environ.get("OPENAI_API_KEY")})}]}
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": res}) + "\\n"); sys.stdout.flush()
''')


class LocalServerTests(unittest.TestCase):
    def setUp(self):
        mcp._sessions.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"SBGD_SECRETS_BACKEND": "file", "OPENAI_API_KEY": "sk-should-not-leak"})
        self.env.start()
        self.db = Path(self.tmp.name) / "data" / "second_brain.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_all(self.conn)
        self.script = Path(self.tmp.name) / "tiny_server.py"
        self.script.write_text(SERVER)

    def tearDown(self):
        mcp.close_all()
        self.conn.close()
        self.env.stop()
        self.tmp.cleanup()

    def test_nothing_runs_before_approval_then_it_works_with_a_clean_environment(self):
        s = mcp.add_local(self.conn, "Tiny", [sys.executable, str(self.script)], ["TINY_TOKEN"])
        self.assertEqual((s["status"], s["approved"]), ("approval", False))
        self.assertEqual(mcp._sessions, {}, "nothing started")
        self.assertIn("not available", mcp.run(self.conn, "mcp__tiny__env_check", {}, "archivist")["error"], "no tools before approval")
        self.assertEqual(mcp._sessions, {})
        mcp.set_env(self.conn, s["id"], "TINY_TOKEN", "t-42")
        s = mcp.approve_local(self.conn, s["id"])
        self.assertEqual(s["status"], "ready", s.get("error"))
        out = mcp.run(self.conn, "mcp__tiny__env_check", {}, "archivist")
        seen = json.loads(out["content"])
        self.assertEqual(seen["declared"], "t-42", "the declared variable, from the secret store")
        self.assertIsNone(seen["brain_secret"], "no secret of the Brain is inherited")
        self.assertIn("tiny server started", mcp.local_log(s["id"]))
        self.assertNotIn("t-42", json.dumps(mcp.servers(self.conn)))

    def test_a_changed_command_needs_a_new_approval(self):
        s = mcp.add_local(self.conn, "Tiny", [sys.executable, str(self.script)])
        mcp.approve_local(self.conn, s["id"])
        mcp._update(self.conn, s["id"], command=[sys.executable, str(self.script), "--other"])
        mcp._close(s["id"])
        out = mcp.run(self.conn, "mcp__tiny__env_check", {}, "archivist")
        self.assertIn("waits for your approval", out["error"])

    def test_a_crash_is_reported_and_the_next_call_restarts_it(self):
        s = mcp.add_local(self.conn, "Tiny", [sys.executable, str(self.script)])
        mcp.approve_local(self.conn, s["id"])
        self.assertIn("stopped", mcp.run(self.conn, "mcp__tiny__crash", {}, "archivist")["error"])
        again = mcp.run(self.conn, "mcp__tiny__env_check", {}, "archivist")
        self.assertIn("declared", again["content"], "started again on the next call")
        mcp.stop_local(self.conn, s["id"])
        self.assertNotIn(s["id"], mcp._sessions)

    def test_versions_are_pinned_and_runtimes_never_installed(self):
        with self.assertRaises(mcp.McpClientError):
            mcp.add_local(self.conn, "x", "npx -y @scope/server")
        with self.assertRaises(mcp.McpClientError):
            mcp.add_local(self.conn, "x", "uvx some-server")
        with self.assertRaises(mcp.McpClientError):
            mcp.add_local(self.conn, "x", "npx a && del *")
        self.assertEqual(local.command_for_package("npm", "@acme/srv", "1.2.3"), ["npx", "-y", "@acme/srv@1.2.3"])
        self.assertEqual(local.command_for_package("pypi", "acme-srv", "0.4"), ["uvx", "acme-srv==0.4"])
        with self.assertRaises(local.LocalError):
            local.command_for_package("npm", "@acme/srv", "latest")
        with mock.patch.object(local.shutil, "which", return_value=None):
            s = mcp.add_local(self.conn, "Needs node", "npx -y @acme/srv@1.2.3")
            self.assertEqual(s["status"], "missing")
            self.assertIn("Node.js", s["error"])
            self.assertEqual(mcp.approve_local(self.conn, s["id"])["status"], "missing", "never installed by the Brain")

    def test_registry_local_entries_carry_their_package_and_variables(self):
        e = {"server": {"name": "io.github.acme/srv", "version": "1.2.3", "packages": [{"registryType": "npm", "identifier": "@acme/srv",
             "version": "1.2.3", "environmentVariables": [{"name": "ACME_TOKEN", "isSecret": True, "isRequired": True}]}]}}
        n = catalog.normalize(e)
        self.assertEqual((n["family"], n["package_type"], n["package_id"], n["package_version"]), ("local", "npm", "@acme/srv", "1.2.3"))
        self.assertEqual(n["env"][0]["name"], "ACME_TOKEN")


if __name__ == "__main__":
    unittest.main()
