"""Loop MCP-E: account sign-in (OAuth 2.1 + PKCE per the MCP spec), server questions (elicitation), sampling refused
unless allowed. A fake MCP server that is also its own authorization server."""
import base64
import hashlib
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from engine import database
from engine.brain.seed import seed_all
from engine.mcp import client as mcp, oauth


class FakeAuthServer:
    def __init__(self):
        self.codes, self.revoked, self.registered = {}, [], []
        self.valid = {"tok-1"}
        self.answer = threading.Event()
        self.answered = {}
        outer = self

        class H(BaseHTTPRequestHandler):
            def _json(self, code, body, headers=None):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                base = outer.base
                if self.path.startswith("/.well-known/oauth-protected-resource"):
                    return self._json(200, {"resource": base + "/mcp", "authorization_servers": [base], "scopes_supported": ["read"]})
                if self.path.startswith("/.well-known/oauth-authorization-server"):
                    return self._json(200, {"issuer": base, "authorization_endpoint": base + "/authorize", "token_endpoint": base + "/token",
                                            "registration_endpoint": base + "/register", "revocation_endpoint": base + "/revoke",
                                            "code_challenge_methods_supported": ["S256"]})
                if self.path.startswith("/authorize"):  # the user signs in: back to the redirect with a code
                    q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                    code = "c-" + q["state"][0][:6]
                    outer.codes[code] = (q["code_challenge"][0], q["redirect_uri"][0], q["resource"][0])
                    self.send_response(302)
                    self.send_header("Location", q["redirect_uri"][0] + "?" + urllib.parse.urlencode({"code": code, "state": q["state"][0]}))
                    self.end_headers()
                    return
                self.send_response(404)
                self.end_headers()

            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                if self.path == "/register":
                    outer.registered.append(json.loads(raw))
                    return self._json(201, {"client_id": "cli-1"})
                if self.path in ("/token", "/revoke"):
                    f = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode()).items()}
                    if self.path == "/revoke":
                        outer.revoked.append(f["token"])
                        return self._json(200, {})
                    if f["grant_type"] == "authorization_code":
                        challenge, redirect, resource = outer.codes.pop(f["code"])
                        calc = base64.urlsafe_b64encode(hashlib.sha256(f["code_verifier"].encode()).digest()).rstrip(b"=").decode()
                        if calc != challenge or redirect != f["redirect_uri"] or resource != f["resource"]:
                            return self._json(400, {"error": "invalid_grant"})
                        return self._json(200, {"access_token": "tok-1", "refresh_token": "r-1", "expires_in": 1})
                    if f["grant_type"] == "refresh_token" and f["refresh_token"] == "r-1":
                        outer.valid.add("tok-2")
                        return self._json(200, {"access_token": "tok-2", "expires_in": 3600})
                    return self._json(400, {"error": "invalid_grant"})
                msg = json.loads(raw)
                if "id" in msg and "method" not in msg:  # the client's answer to our question
                    outer.answered = msg
                    outer.answer.set()
                    self.send_response(202)
                    self.end_headers()
                    return
                if self.headers.get("Authorization", "").replace("Bearer ", "") not in outer.valid:
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", f'Bearer resource_metadata="{outer.base}/.well-known/oauth-protected-resource/mcp", scope="read"')
                    self.end_headers()
                    return
                if "id" not in msg:
                    self.send_response(202)
                    self.end_headers()
                    return
                m = msg["method"]
                if m == "initialize":
                    outer.client_caps = msg["params"]["capabilities"]
                    return self._json(200, {"jsonrpc": "2.0", "id": msg["id"], "result": {"protocolVersion": "2025-06-18", "capabilities": {}}},
                                      {"Mcp-Session-Id": "s1"})
                if m == "tools/list":
                    return self._json(200, {"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": [
                        {"name": "whoami", "annotations": {"readOnlyHint": True}, "inputSchema": {"type": "object"}},
                        {"name": "pick_project", "annotations": {"readOnlyHint": True}, "inputSchema": {"type": "object"}},
                        {"name": "summarise", "annotations": {"readOnlyHint": True}, "inputSchema": {"type": "object"}}]}})
                name = msg["params"]["name"]
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                if name == "whoami":
                    text = "you are signed in"
                else:
                    outer.answer.clear()
                    ask = ({"jsonrpc": "2.0", "id": "e1", "method": "elicitation/create", "params": {"message": "Which project?",
                            "requestedSchema": {"type": "object", "properties": {"project": {"type": "string", "enum": ["Brain", "Site"]}}}}}
                           if name == "pick_project" else
                           {"jsonrpc": "2.0", "id": "e1", "method": "sampling/createMessage", "params": {"messages": [
                               {"role": "user", "content": {"type": "text", "text": "Say hi"}}], "maxTokens": 50}})
                    self.wfile.write(("data: " + json.dumps(ask) + "\n\n").encode())
                    self.wfile.flush()
                    outer.answer.wait(20)
                    text = json.dumps(outer.answered.get("result") or outer.answered.get("error"))
                body = {"jsonrpc": "2.0", "id": msg["id"], "result": {"content": [{"type": "text", "text": text}]}}
                self.wfile.write(("data: " + json.dumps(body) + "\n\n").encode())

            def log_message(self, *a):
                pass
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class OAuthTests(unittest.TestCase):
    def setUp(self):
        mcp._sessions.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"SBGD_SECRETS_BACKEND": "file", "SBGD_ASSISTANT_PROVIDER": "fake"})
        self.env.start()
        self.db = Path(self.tmp.name) / "data" / "second_brain.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_all(self.conn)
        self.conn.commit()
        self.fake = FakeAuthServer()

    def tearDown(self):
        self.fake.close()
        self.conn.close()
        self.env.stop()
        self.tmp.cleanup()

    def signed_in_server(self):
        s = mcp.add_server(self.conn, "Fake Account", self.fake.base + "/mcp")
        self.assertEqual(s["status"], "signin", s.get("error"))
        self.assertTrue(s["auth_meta"].endswith("/.well-known/oauth-protected-resource/mcp"))
        self.conn.commit()
        start = mcp.sign_in(self.conn, s["id"])
        self.conn.commit()
        self.assertIn("code_challenge_method=S256", start["url"])
        self.assertIn("resource=", start["url"])
        urllib.request.urlopen(start["url"], timeout=10).read()  # the browser: sign-in, then back to 127.0.0.1
        for _ in range(40):
            if oauth.flow_status(s["id"])["status"] != "waiting":
                break
            time.sleep(0.1)
        self.assertEqual(oauth.flow_status(s["id"])["status"], "done", oauth.flow_status(s["id"])["error"])
        self.assertEqual(self.fake.registered[0]["token_endpoint_auth_method"], "none", "a public client, no secret")
        return mcp.get_server(self.conn, s["id"])

    def test_sign_in_use_refresh_and_disconnect(self):
        s = self.signed_in_server()
        self.assertTrue(s["oauth"])
        self.assertEqual(s["status"], "ready")
        self.assertNotIn("tok-", json.dumps(mcp.servers(self.conn)), "tokens are never in the settings")
        out = mcp.run(self.conn, "mcp__fakeaccount__whoami", {}, "archivist")
        self.assertEqual(out["content"], "you are signed in", "the 1-second token was refreshed")
        self.assertIn("tok-2", self.fake.valid)
        mcp.sign_out(self.conn, s["id"])
        self.assertIn("r-1", self.fake.revoked, "Disconnect revokes at the server")
        self.assertFalse(oauth.signed_in(mcp._layout(self.conn), s["id"]))
        self.assertEqual(mcp.get_server(self.conn, s["id"])["status"], "signin")

    def test_a_server_question_waits_for_the_user(self):
        s = self.signed_in_server()
        self.assertIn("elicitation", self.fake.client_caps)

        def user():
            for _ in range(80):
                with database.session(self.db) as c2:
                    q = mcp.questions(c2)
                    if q:
                        self.assertEqual(q[0]["message"], "Which project?")
                        mcp.answer_question(c2, q[0]["id"], "accept", {"project": "Brain"})
                        return
                time.sleep(0.1)
        threading.Thread(target=user, daemon=True).start()
        out = mcp.run(self.conn, "mcp__fakeaccount__pick_project", {}, "archivist")
        self.assertEqual(json.loads(out["content"]), {"action": "accept", "content": {"project": "Brain"}})

    def test_sampling_is_refused_unless_allowed(self):
        s = self.signed_in_server()
        self.assertNotIn("sampling", self.fake.client_caps, "not even offered by default")
        out = mcp.run(self.conn, "mcp__fakeaccount__summarise", {}, "archivist")
        self.assertIn("does not let this server use their AI model", out["content"])
        mcp.set_sampling(self.conn, s["id"], True, 2)
        out = mcp.run(self.conn, "mcp__fakeaccount__summarise", {}, "archivist")
        self.assertEqual(json.loads(out["content"])["role"], "assistant")
        self.assertIn("sampling", self.fake.client_caps)

    def test_challenge_parsing(self):
        self.assertEqual(oauth.parse_www_authenticate('Bearer realm="OAuth", resource_metadata="https://x/.well-known/p", scope="default"'),
                         ("https://x/.well-known/p", "default"))


if __name__ == "__main__":
    unittest.main()
