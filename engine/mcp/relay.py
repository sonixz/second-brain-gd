"""MCP stdio relay (Loop MCP-A): lets an MCP client that starts a command (Claude Code in WSL, for one) reach the
Brain's MCP endpoint on this computer. Run it with the app's own Windows Python:

    claude mcp add second-brain -- <SecondBrainGD>/.venv/Scripts/python.exe <repo>/engine/mcp/relay.py --client <id>

It reads newline-delimited JSON-RPC on stdin, posts each message to http://127.0.0.1:<port>/mcp (the port from the
running engine's runtime/server.json) with the client's token (from <SecondBrainGD>/mcp/<id>.token, written by the
app), and writes the answers on stdout. Standard library only; nothing else is started or downloaded.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def home() -> Path:
    if os.environ.get("SBGD_HOME"):
        return Path(os.environ["SBGD_HOME"])
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "SecondBrainGD"


def _err(mid, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32000, "message": message}}


def post(port: int, token: str, payload: bytes, session: str | None) -> tuple[int, bytes, str | None]:
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "Authorization": f"Bearer {token}"}
    if session:
        headers["Mcp-Session-Id"] = session
    req = urllib.request.Request(f"http://127.0.0.1:{port}/mcp", data=payload, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, resp.read(), resp.headers.get("Mcp-Session-Id")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Second Brain MCP relay (stdio ⇄ http://127.0.0.1)")
    ap.add_argument("--client", required=True, help="the client id shown by the app")
    args = ap.parse_args(argv)
    root = home()
    token_file = root / "mcp" / f"{args.client}.token"
    session: str | None = None
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            out.write(json.dumps(_err(None, "parse error")) + "\n")
            out.flush()
            continue
        mid = msg.get("id") if isinstance(msg, dict) else None
        try:
            token = token_file.read_text(encoding="utf-8").strip()
            port = int(json.loads((root / "runtime" / "server.json").read_text(encoding="utf-8"))["port"])
        except (OSError, ValueError, KeyError):
            if mid is not None:
                out.write(json.dumps(_err(mid, "Second Brain is not running, or this tool was disconnected: open the "
                                               "app (and connect the tool again if needed)")) + "\n")
                out.flush()
            continue
        try:
            status, body, sid = post(port, token, line.encode("utf-8"), session)
        except OSError:
            if mid is not None:
                out.write(json.dumps(_err(mid, "Second Brain is not answering: is the app open?")) + "\n")
                out.flush()
            continue
        session = sid or session
        if status == 202 or not body:
            continue
        if status >= 400:
            try:
                detail = json.loads(body).get("error") or json.loads(body).get("detail")
            except ValueError:
                detail = f"HTTP {status}"
            if mid is not None:
                out.write(json.dumps(_err(mid, str(detail))) + "\n")
                out.flush()
            continue
        out.write(body.decode("utf-8").strip() + "\n")
        out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
