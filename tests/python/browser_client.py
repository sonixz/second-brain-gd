"""Plays the browser extension against a real engine (run with the engine's venv Python: needs websockets).

  browser_client.py <port> <local api token>

Pairs with a code, connects the WebSocket, then drives the assistant (fake model) through « ouvre la page »,
« injecte-la » and « ferme-la », answering the engine's commands like the extension does. Prints one JSON line.
"""
import asyncio
import json
import sys
import threading
import urllib.error
import urllib.request

import websockets

PORT, TOK = int(sys.argv[1]), sys.argv[2]
BASE = f"http://127.0.0.1:{PORT}"
PAGE = ("<html><head><title>Analyste DevSecOps — Exemple</title></head><body><nav>Menu</nav><main><h1>Analyste DevSecOps</h1>"
        + "<p>Montréal, hybride. Azure, Sentinel, Bicep, KQL. Poste permanent, équipe sécurité infonuagique.</p>" * 12
        + "</main></body></html>")


def call(path, token=None, body=None, method=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 method=method or ("POST" if body is not None else "GET"),
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


async def main():
    out = {}
    code = call("/browser/pair/start", TOK, {})[1]["code"]
    out["wrong_code"] = call("/browser/pair", body={"code": "AAAA-AAAA", "browser": "Test"})[0]
    st, paired = call("/browser/pair", body={"code": code.lower().replace("-", " "), "browser": "TestBrowser 1"})
    out["paired"] = st
    btok = paired["token"]
    out["code_reused"] = call("/browser/pair", body={"code": code, "browser": "Test"})[0]
    out["capture_without_token"] = call("/browser/capture", body={"url": "https://example.org", "html": PAGE})[0]
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/browser/ws") as ws:
        await ws.send(json.dumps({"type": "hello", "token": btok, "browser": "TestBrowser 1", "version": "1.0.0",
                                  "can_read_tabs": True}))
        out["welcome"] = json.loads(await ws.recv())["type"]
        out["status_connected"] = call("/browser/status", TOK)[1]["connected"]
        seen = []

        async def extension():
            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] != "command":
                    continue
                seen.append(msg["action"])
                if msg["action"] == "open":
                    data = {"ref": "7", "url": msg["url"]}
                elif msg["action"] == "capture":
                    data = await asyncio.to_thread(call, "/browser/capture", btok,
                                                   {"url": "https://jobs.example.org/7", "title": "Analyste DevSecOps — Exemple",
                                                    "html": PAGE, "text": "", "selection": ""})
                    data = data[1]
                else:
                    data = {"closed": 1}
                await ws.send(json.dumps({"type": "result", "id": msg["id"], "ok": True, "data": data}))

        task = asyncio.create_task(extension())
        replies = []
        for text in ["Ouvre la page https://jobs.example.org/7", "Injecte-la", "Ferme-la"]:
            st, res = await asyncio.to_thread(call, "/assistant/chat", TOK, {"text": text})
            replies.append(res.get("reply", f"HTTP {st}"))
        out["commands"] = seen
        out["replies"] = replies
        out["rev"] = call("/browser/status", TOK)[1]["rev"]
        task.cancel()
    out["unpair"] = call("/browser/pair", TOK, method="DELETE")[1]["revoked"]
    out["capture_after_unpair"] = call("/browser/capture", btok, {"url": "https://example.org", "html": PAGE})[0]
    print(json.dumps(out, ensure_ascii=False))


asyncio.run(main())
