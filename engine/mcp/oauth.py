"""Account sign-in for MCP servers (Loop MCP-E), per the MCP authorization spec: OAuth 2.1 with PKCE.

1. The server answers 401 with `WWW-Authenticate: Bearer resource_metadata="…"`.
2. Its protected-resource metadata names the authorization server; that server's metadata gives the endpoints.
3. The Brain registers itself (dynamic client registration) when it may, as a public client (no secret).
4. The user signs in in their own browser; the answer comes back to a one-time listener on 127.0.0.1.
5. The code is exchanged (with the PKCE verifier and the `resource`); tokens go to the OS credential store, are
   refreshed before they expire, and « Disconnect » revokes them.
Standard library only; nothing is sent anywhere but the server's own authorization endpoints.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets as pysecrets
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

FLOW_TIMEOUT_S = 300
_flows: dict[str, dict[str, Any]] = {}   # server id -> the sign-in under way
_lock = threading.Lock()
PAGE = ("<!doctype html><html><head><meta charset='utf-8'><title>Second Brain</title></head>"
        "<body style='font-family:Segoe UI,sans-serif;background:#14202e;color:#e6eef6;text-align:center;padding-top:15vh'>"
        "<h2>{title}</h2><p>{text}</p></body></html>")


class OAuthError(RuntimeError):
    pass


def parse_www_authenticate(value: str) -> tuple[str, str]:
    """resource_metadata and scope from a « Bearer key="value", … » challenge."""
    found: dict[str, str] = {}
    for part in value.split(","):
        k, _, v = part.strip().partition("=")
        k = k.replace("Bearer", "").strip().lower()
        found[k] = v.strip().strip('"')
    return found.get("resource_metadata", ""), found.get("scope", "")


def _get_json(url: str, timeout: float = 15.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "SecondBrain-MCP/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read(1_000_000))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise OAuthError(f"cannot read {url} ({exc.__class__.__name__})") from exc


def _post_form(url: str, data: dict[str, str], basic: tuple[str, str] | None = None, timeout: float = 20.0) -> dict[str, Any]:
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": "SecondBrain-MCP/1.0"}
    if basic:
        headers["Authorization"] = "Basic " + base64.b64encode(f"{basic[0]}:{basic[1]}".encode()).decode()
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(1_000_000)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get("error_description") or ""
        except Exception:
            detail = ""
        raise OAuthError(f"the sign-in server refused ({exc.code}{': ' + detail if detail else ''})") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise OAuthError(f"cannot reach the sign-in server ({exc.__class__.__name__})") from exc
    return json.loads(raw) if raw.strip() else {}


def discover(server_url: str, metadata_url: str = "") -> dict[str, Any]:
    """The authorization server's endpoints for an MCP server."""
    parts = urllib.parse.urlsplit(server_url)
    origin = f"{parts.scheme}://{parts.netloc}"
    candidates = [metadata_url] if metadata_url else []
    candidates += [f"{origin}/.well-known/oauth-protected-resource{parts.path.rstrip('/')}", f"{origin}/.well-known/oauth-protected-resource"]
    prm: dict[str, Any] = {}
    for c in candidates:
        try:
            prm = _get_json(c)
            break
        except OAuthError:
            continue
    issuer = (prm.get("authorization_servers") or [origin])[0].rstrip("/")
    ip = urllib.parse.urlsplit(issuer)
    base, path = f"{ip.scheme}://{ip.netloc}", ip.path.rstrip("/")
    meta: dict[str, Any] = {}
    for c in (f"{base}/.well-known/oauth-authorization-server{path}", f"{base}/.well-known/openid-configuration{path}",
              f"{issuer}/.well-known/openid-configuration"):
        try:
            meta = _get_json(c)
            if meta.get("authorization_endpoint"):
                break
        except OAuthError:
            continue
    if not meta.get("authorization_endpoint") or not meta.get("token_endpoint"):
        raise OAuthError("this server does not publish how to sign in (no authorization server metadata)")
    if "S256" not in (meta.get("code_challenge_methods_supported") or ["S256"]):
        raise OAuthError("the sign-in server does not support PKCE (S256)")
    return {"issuer": issuer, "authorization_endpoint": meta["authorization_endpoint"], "token_endpoint": meta["token_endpoint"],
            "registration_endpoint": meta.get("registration_endpoint"), "revocation_endpoint": meta.get("revocation_endpoint"),
            "scopes": prm.get("scopes_supported") or meta.get("scopes_supported") or [], "resource": prm.get("resource") or server_url}


def register(meta: dict[str, Any], redirect_uri: str) -> dict[str, str]:
    if not meta.get("registration_endpoint"):
        raise OAuthError("this server needs a client registered by hand (no dynamic registration): not supported yet")
    body = json.dumps({"client_name": "Second Brain", "redirect_uris": [redirect_uri], "grant_types": ["authorization_code", "refresh_token"],
                       "response_types": ["code"], "token_endpoint_auth_method": "none"}).encode()
    req = urllib.request.Request(meta["registration_endpoint"], data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "SecondBrain-MCP/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            out = json.loads(resp.read(1_000_000))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise OAuthError(f"the sign-in server refused to register the Brain ({exc.__class__.__name__})") from exc
    if not out.get("client_id"):
        raise OAuthError("the sign-in server gave no client id")
    return {"client_id": out["client_id"], "client_secret": out.get("client_secret", "")}


def _pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(pysecrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _secret_name(sid: str) -> str:
    return f"mcp-{sid}-oauth"


def _db_path(conn: sqlite3.Connection) -> Path:
    return Path(conn.execute("PRAGMA database_list").fetchone()[2])


def start(conn: sqlite3.Connection, s: dict[str, Any], metadata_url: str = "", scope: str = "",
          on_done: Any = None) -> dict[str, Any]:
    """Prepares the sign-in: a one-time listener on 127.0.0.1, the URL to open in the user's browser."""
    from engine.mcp import client as mcp
    meta = discover(s["url"], metadata_url)
    db = _db_path(conn)
    layout = mcp._layout(conn)
    state = pysecrets.token_urlsafe(24)
    verifier, challenge = _pkce()
    flow: dict[str, Any] = {"state": state, "status": "waiting", "error": "", "started": time.time()}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if not self.path.startswith("/callback"):
                self.send_response(404)
                self.end_headers()
                return
            ok, text = _finish(q)
            page = PAGE.format(title="✓ Second Brain" if ok else "Second Brain",
                               text=("Connecté. Tu peux fermer cet onglet. · Connected. You can close this tab." if ok else text))
            data = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            threading.Thread(target=httpd.shutdown, daemon=True).start()

        def log_message(self, *a):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), H)
    redirect = f"http://127.0.0.1:{httpd.server_address[1]}/callback"
    client_info = register(meta, redirect)

    def _finish(q: dict[str, list[str]]) -> tuple[bool, str]:
        if q.get("state", [""])[0] != state:
            flow.update(status="failed", error="the answer did not match this sign-in (state)")
            return False, flow["error"]
        if q.get("error"):
            flow.update(status="failed", error=f"sign-in refused: {q['error'][0]}")
            return False, flow["error"]
        code = q.get("code", [""])[0]
        try:
            data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect, "client_id": client_info["client_id"],
                    "code_verifier": verifier, "resource": meta["resource"]}
            basic = (client_info["client_id"], client_info["client_secret"]) if client_info.get("client_secret") else None
            tok = _post_form(meta["token_endpoint"], data, basic)
            if not tok.get("access_token"):
                raise OAuthError("no access token in the answer")
            save_tokens(layout, s["id"], tok, meta, client_info)
            flow.update(status="done")
            if on_done:
                try:
                    on_done(db)
                except Exception:
                    pass
            return True, ""
        except OAuthError as exc:
            flow.update(status="failed", error=str(exc))
            return False, str(exc)

    def serve() -> None:
        httpd.timeout = 1
        deadline = time.time() + FLOW_TIMEOUT_S
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        while time.time() < deadline and flow["status"] == "waiting":
            time.sleep(0.5)
        if flow["status"] == "waiting":
            flow.update(status="failed", error="the sign-in was not finished in time")
            httpd.shutdown()
        httpd.server_close()

    threading.Thread(target=serve, daemon=True).start()
    params = {"response_type": "code", "client_id": client_info["client_id"], "redirect_uri": redirect, "state": state,
              "code_challenge": challenge, "code_challenge_method": "S256", "resource": meta["resource"]}
    scope = scope or " ".join(meta.get("scopes") or [])
    if scope:
        params["scope"] = scope
    url = meta["authorization_endpoint"] + ("&" if "?" in meta["authorization_endpoint"] else "?") + urllib.parse.urlencode(params)
    with _lock:
        _flows[s["id"]] = flow
    return {"url": url, "redirect": redirect}


def flow_status(sid: str) -> dict[str, Any]:
    with _lock:
        f = dict(_flows.get(sid) or {})
    return {"status": f.get("status", "none"), "error": f.get("error", "")}


def save_tokens(layout, sid: str, tok: dict[str, Any], meta: dict[str, Any], client_info: dict[str, str]) -> None:
    from engine.voice import secrets
    record = {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token", ""),
              "expires_at": time.time() + float(tok.get("expires_in") or 3600), "token_endpoint": meta["token_endpoint"],
              "revocation_endpoint": meta.get("revocation_endpoint") or "", "resource": meta["resource"],
              "client_id": client_info["client_id"], "client_secret": client_info.get("client_secret", "")}
    secrets.store(layout, _secret_name(sid), json.dumps(record))


def _load(layout, sid: str) -> dict[str, Any] | None:
    from engine.voice import secrets
    raw, _ = secrets.get(layout, _secret_name(sid))
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def access_token(layout, sid: str, force_refresh: bool = False) -> str | None:
    """A valid access token, refreshed when it is about to expire (or was refused)."""
    rec = _load(layout, sid)
    if not rec:
        return None
    if not force_refresh and rec.get("expires_at", 0) - time.time() > 60:
        return rec["access_token"]
    if not rec.get("refresh_token"):
        return None if force_refresh else rec["access_token"]
    data = {"grant_type": "refresh_token", "refresh_token": rec["refresh_token"], "client_id": rec["client_id"], "resource": rec["resource"]}
    basic = (rec["client_id"], rec["client_secret"]) if rec.get("client_secret") else None
    try:
        tok = _post_form(rec["token_endpoint"], data, basic)
    except OAuthError:
        return None
    rec.update(access_token=tok.get("access_token", rec["access_token"]), expires_at=time.time() + float(tok.get("expires_in") or 3600))
    if tok.get("refresh_token"):
        rec["refresh_token"] = tok["refresh_token"]
    from engine.voice import secrets
    secrets.store(layout, _secret_name(sid), json.dumps(rec))
    return rec["access_token"]


def signed_in(layout, sid: str) -> bool:
    return _load(layout, sid) is not None


def disconnect(layout, sid: str) -> None:
    """Revokes the tokens at the server when it offers it (best effort), then forgets them."""
    from engine.voice import secrets
    rec = _load(layout, sid)
    if rec and rec.get("revocation_endpoint"):
        for kind in ("refresh_token", "access_token"):
            if rec.get(kind):
                try:
                    _post_form(rec["revocation_endpoint"], {"token": rec[kind], "token_type_hint": kind, "client_id": rec["client_id"]}, None, 10.0)
                except OAuthError:
                    pass
    secrets.delete(layout, _secret_name(sid))
