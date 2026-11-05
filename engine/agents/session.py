"""Agent sessions: the engine drives `codex app-server` over stdio, Godot shows the result.

Protocol (Codex app-server, rust-v0.166.0): newline-delimited JSON-RPC without the
"jsonrpc" field. Handshake `initialize` + `initialized`, then `account/login/start`
with the user's OpenAI key (sent over stdin, never in argv, env or logs), then
`thread/start` in a folder the user chose. Each message becomes `turn/start`.
The server streams notifications (items, deltas, turn completion) and asks for
approvals (`item/commandExecution/requestApproval`, `item/fileChange/requestApproval`);
those wait for the user's decision in the UI.

Godot polls `/agents/sessions/{id}/events?after=N`: an append-only list of small,
already-trimmed UI events, so the app never parses the raw protocol.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from engine.events import utc_now

APPROVAL_METHODS = {"item/commandExecution/requestApproval": "command", "item/fileChange/requestApproval": "file_change"}
DECISIONS = ("accept", "acceptForSession", "decline", "cancel")
MAX_EVENTS = 2000
OUTPUT_LIMIT = 4000
DIFF_LIMIT = 8000
CLIENT_INFO = {"name": "second_brain_gd", "title": "Second Brain GD", "version": "0.6"}


class AgentError(RuntimeError):
    pass


def _no_window() -> dict[str, Any]:
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def command_for(binary: str) -> list[str]:
    # Test fixtures are Python scripts standing in for the native binary.
    return [sys.executable, binary] if binary.endswith(".py") else [binary]


def _trim_item(item: dict[str, Any]) -> dict[str, Any]:
    out = {k: item.get(k) for k in ("id", "type", "status", "text", "phase", "command", "cwd", "exitCode", "durationMs")
           if item.get(k) is not None}
    if item.get("aggregatedOutput"):
        out["output"] = str(item["aggregatedOutput"])[-OUTPUT_LIMIT:]
    if item.get("changes"):
        out["changes"] = [{"path": c.get("path"), "kind": c.get("kind"), "diff": str(c.get("diff") or "")[:DIFF_LIMIT]}
                          for c in item["changes"][:50]]
    return out


class AgentSession:
    def __init__(self, binary: str, cwd: Path, model: str, home: Path, approval_policy: str, sandbox: str):
        self.id = uuid.uuid4().hex[:12]
        self.binary = binary
        self.cwd = cwd
        self.model = model
        self.home = home
        self.approval_policy = approval_policy
        self.sandbox = sandbox
        self.created_at = utc_now()
        self.status = "starting"
        self.thread_id: str | None = None
        self.turn_id: str | None = None
        self.error: str | None = None
        self.events: list[dict[str, Any]] = []
        self.seq = 0
        self.pending: dict[int, dict[str, Any]] = {}
        self.stderr_tail: deque[str] = deque(maxlen=40)
        self._lock = threading.Lock()
        self._next_id = 0
        self._waiters: dict[int, tuple[threading.Event, dict[str, Any]]] = {}
        self._write_lock = threading.Lock()
        self.proc: subprocess.Popen[bytes] | None = None

    # ------------------------------------------------------------ plumbing
    def _event(self, event_type: str, /, **data: Any) -> None:
        with self._lock:
            self.seq += 1
            self.events.append({**data, "seq": self.seq, "type": event_type, "at": utc_now()})
            if len(self.events) > MAX_EVENTS:
                del self.events[: len(self.events) - MAX_EVENTS]

    def _write(self, obj: dict[str, Any]) -> None:
        if self.proc is None or self.proc.stdin is None or self.proc.poll() is not None:
            raise AgentError("The agent process is not running.")
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        with self._write_lock:
            self.proc.stdin.write(data)
            self.proc.stdin.flush()

    def request(self, method: str, params: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
        with self._lock:
            self._next_id += 1
            rid = self._next_id
            done, slot = threading.Event(), {}
            self._waiters[rid] = (done, slot)
        self._write({"id": rid, "method": method, "params": params})
        if not done.wait(timeout):
            self._waiters.pop(rid, None)
            raise AgentError(f"No answer to {method} after {timeout:.0f} s.")
        if "error" in slot:
            raise AgentError(f"{method}: {(slot['error'] or {}).get('message', 'error')}")
        return slot.get("result") or {}

    def _read_stdout(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        for raw in self.proc.stdout:
            try:
                msg = json.loads(raw.decode("utf-8", errors="replace"))
            except ValueError:
                continue
            try:
                self._dispatch(msg)
            except Exception as exc:  # a malformed message must not kill the reader
                self._event("log", text=f"unreadable message: {exc.__class__.__name__}")
        code = self.proc.wait()
        if self.status != "stopped":
            self.status = "error" if code else "stopped"
            if code:
                self.error = self.error or f"The agent stopped (exit code {code})."
            self._event("stopped", code=code, error=self.error)
        for done, slot in list(self._waiters.values()):
            slot["error"] = {"message": "agent process exited"}
            done.set()

    def _read_stderr(self) -> None:
        assert self.proc is not None and self.proc.stderr is not None
        for raw in self.proc.stderr:
            self.stderr_tail.append(raw.decode("utf-8", errors="replace").rstrip()[:300])

    def _dispatch(self, msg: dict[str, Any]) -> None:
        method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
        if method is None and mid is not None:  # a response to one of our requests
            waiter = self._waiters.pop(mid, None)
            if waiter is not None:
                waiter[1].update({k: msg[k] for k in ("result", "error") if k in msg})
                waiter[0].set()
            return
        if method is not None and mid is not None:  # the agent asks us something
            kind = APPROVAL_METHODS.get(method)
            if kind is None:
                # Permission escalations, user-input prompts and MCP elicitations are refused for now.
                self._write({"id": mid, "error": {"code": -32601, "message": "Not supported by Second Brain GD"}})
                self._event("log", text=f"refused request {method}")
                return
            offered = [d for d in (params.get("availableDecisions") or DECISIONS) if d in DECISIONS] or list(DECISIONS)
            if "decline" not in offered:
                # The real app-server suggests only accept/cancel for commands, but takes `decline` and the agent
                # carries on, whereas `cancel` ends the whole turn. The user must always be able to say no.
                offered.append("decline")
            approval = {"request_id": mid, "kind": kind, "item_id": params.get("itemId"),
                        "reason": params.get("reason"), "command": params.get("command"), "cwd": params.get("cwd"),
                        "grant_root": params.get("grantRoot"), "decisions": offered}
            self.pending[mid] = approval
            self.status = "waiting_approval"
            self._event("approval", **approval)
            return
        if method == "item/agentMessage/delta":
            self._event("delta", item_id=params.get("itemId"), text=str(params.get("delta") or ""))
        elif method in ("item/started", "item/completed"):
            item = params.get("item") or {}
            if item.get("type") in ("agentMessage", "commandExecution", "fileChange", "reasoning", "webSearch",
                                    "mcpToolCall", "plan"):
                self._event("item", phase=method.split("/")[1], item=_trim_item(item))
        elif method == "turn/started":
            self.turn_id = (params.get("turn") or {}).get("id")
            self.status = "working"
            self._event("turn_started", turn_id=self.turn_id)
        elif method == "turn/completed":
            turn = params.get("turn") or {}
            self.status = "idle"
            self.turn_id = None
            err = (turn.get("error") or {}).get("message")
            self._event("turn_completed", status=turn.get("status"), error=err)

    # ------------------------------------------------------------ lifecycle
    def start(self, api_key: str) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k not in ("OPENAI_API_KEY", "CODEX_API_KEY")}
        env["CODEX_HOME"] = str(self.home)  # never the user's own ~/.codex
        self.proc = subprocess.Popen(command_for(self.binary), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, cwd=str(self.cwd), env=env, **_no_window())
        threading.Thread(target=self._read_stdout, name=f"agent-{self.id}-out", daemon=True).start()
        threading.Thread(target=self._read_stderr, name=f"agent-{self.id}-err", daemon=True).start()
        try:
            self.request("initialize", {"clientInfo": CLIENT_INFO}, timeout=30)
            self._write({"method": "initialized", "params": {}})
            self.request("account/login/start", {"type": "apiKey", "apiKey": api_key}, timeout=30)
            res = self.request("thread/start", {"cwd": str(self.cwd), "model": self.model,
                                                "approvalPolicy": self.approval_policy, "sandbox": self.sandbox,
                                                "serviceName": "Second Brain GD"}, timeout=60)
        except AgentError as exc:
            self.error = str(exc).replace(api_key, "***")
            self.stop()
            self.status = "error"
            raise AgentError(self.error) from None
        self.thread_id = (res.get("thread") or {}).get("id")
        self.status = "idle"
        self._event("ready", thread_id=self.thread_id, cwd=str(self.cwd), model=self.model)

    def send(self, text: str) -> dict[str, Any]:
        if self.thread_id is None or self.status in ("stopped", "error"):
            raise AgentError("This session is not running.")
        if self.status in ("working", "waiting_approval"):
            raise AgentError("The agent is still working on the previous message.")
        self._event("user", text=text)
        self.status = "working"
        res = self.request("turn/start", {"threadId": self.thread_id, "input": [{"type": "text", "text": text}]})
        return res.get("turn") or {}

    def decide(self, request_id: int, decision: str) -> None:
        if decision not in DECISIONS:
            raise AgentError(f"Unknown decision {decision}.")
        approval = self.pending.pop(request_id, None)
        if approval is None:
            raise AgentError("No such pending approval.")
        self._write({"id": request_id, "result": {"decision": decision}})
        self._event("decision", request_id=request_id, decision=decision, kind=approval["kind"])
        if not self.pending and self.status == "waiting_approval":
            self.status = "working"

    def interrupt(self) -> None:
        if self.thread_id and self.turn_id:
            self.request("turn/interrupt", {"threadId": self.thread_id, "turnId": self.turn_id}, timeout=15)

    def stop(self) -> None:
        self.status = "stopped"
        if self.proc is not None and self.proc.poll() is None:
            try:
                if self.proc.stdin:
                    self.proc.stdin.close()
                self.proc.wait(timeout=3)
            except Exception:
                self.proc.kill()
        # With an API-key login the app-server may keep credentials in CODEX_HOME; the key lives in the
        # OS credential store already, so remove any copy when the session ends.
        for name in ("auth.json",):
            try:
                (self.home / name).unlink()
            except OSError:
                pass

    def snapshot(self, after: int = 0) -> dict[str, Any]:
        with self._lock:
            events = [e for e in self.events if e["seq"] > after]
        return {"id": self.id, "status": self.status, "cwd": str(self.cwd), "model": self.model,
                "created_at": self.created_at, "error": self.error, "seq": self.seq,
                "pending": list(self.pending.values()), "events": events}


class AgentManager:
    MAX_SESSIONS = 4

    def __init__(self, home: Path):
        self.home = home
        self.sessions: dict[str, AgentSession] = {}
        self._lock = threading.Lock()

    def create(self, binary: str, cwd: Path, model: str, api_key: str, approval_policy: str, sandbox: str) -> AgentSession:
        with self._lock:
            live = [s for s in self.sessions.values() if s.status not in ("stopped", "error")]
            if len(live) >= self.MAX_SESSIONS:
                raise AgentError(f"At most {self.MAX_SESSIONS} agents at a time; stop one first.")
            s = AgentSession(binary, cwd, model, self.home, approval_policy, sandbox)
            self.sessions[s.id] = s
        s.start(api_key)
        return s

    def get(self, sid: str) -> AgentSession:
        s = self.sessions.get(sid)
        if s is None:
            raise KeyError(sid)
        return s

    def stop_all(self) -> None:
        for s in list(self.sessions.values()):
            s.stop()

    def remove(self, sid: str) -> None:
        s = self.sessions.pop(sid, None)
        if s is not None:
            s.stop()
