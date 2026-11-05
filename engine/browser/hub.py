"""The live link with the extension: commands go out (open, capture, close) and answers come back.

The extension keeps one WebSocket open to the engine. The assistant's tools run in worker threads: they send a
command into the event loop and wait (with a timeout) for the extension's answer.
"""
from __future__ import annotations

import asyncio
import itertools
import json
import threading
import time
from typing import Any


class BrowserError(RuntimeError):
    pass


class Hub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ws: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending: dict[str, dict[str, Any]] = {}
        self._ids = itertools.count(1)
        self.info: dict[str, Any] = {}
        self.rev = 0                      # pages added from the browser: the app refreshes when it changes
        self.last_added: dict[str, Any] = {}
        self.opened: dict[str, dict[str, Any]] = {}  # tabs the Brain opened: ref -> {url, title}

    # --- connection (event loop side)
    def attach(self, ws: Any, loop: asyncio.AbstractEventLoop, info: dict[str, Any]) -> None:
        with self._lock:
            self._ws, self._loop = ws, loop
            self.info = {**info, "connected_at": time.time()}

    def detach(self, ws: Any) -> None:
        with self._lock:
            if self._ws is ws:
                self._ws, self._loop = None, None
                for p in self._pending.values():  # nobody will answer them now
                    p["result"] = {"ok": False, "error": "the browser disconnected"}
                    p["event"].set()

    def connected(self) -> bool:
        return self._ws is not None

    def resolve(self, cmd_id: str, ok: bool, data: Any) -> None:
        with self._lock:
            p = self._pending.get(str(cmd_id))
        if p is not None:
            p["result"] = {"ok": bool(ok), **({"data": data} if ok else {"error": str(data)[:300]})}
            p["event"].set()

    def note_added(self, item: dict[str, Any]) -> None:
        with self._lock:
            self.rev += 1
            self.last_added = item

    # --- commands (worker thread side)
    def command(self, action: str, args: dict[str, Any] | None = None, timeout: float = 20.0) -> Any:
        with self._lock:
            ws, loop = self._ws, self._loop
            if ws is None or loop is None:
                raise BrowserError("the browser extension is not connected")
            cmd_id = str(next(self._ids))
            waiter = {"event": threading.Event(), "result": None}
            self._pending[cmd_id] = waiter
        msg = json.dumps({"type": "command", "id": cmd_id, "action": action, **(args or {})}, ensure_ascii=False)
        try:
            asyncio.run_coroutine_threadsafe(ws.send_text(msg), loop).result(timeout=5)
            if not waiter["event"].wait(timeout):
                raise BrowserError(f"the browser did not answer « {action} » in {int(timeout)} s")
        except BrowserError:
            raise
        except Exception as exc:
            raise BrowserError(f"could not reach the browser: {exc.__class__.__name__}") from exc
        finally:
            with self._lock:
                self._pending.pop(cmd_id, None)
        res = waiter["result"] or {"ok": False, "error": "no answer"}
        if not res["ok"]:
            raise BrowserError(res.get("error") or "the browser refused")
        return res.get("data")


HUB = Hub()  # one per engine process
