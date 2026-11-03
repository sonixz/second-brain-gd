"""A tiny stand-in for `codex app-server` (tests only).

Speaks the same newline-delimited JSON-RPC over stdio as the real app-server
(rust-v0.166.0, documented at learn.chatgpt.com/docs/app-server): initialize,
account/login/start (apiKey), thread/start, turn/start, turn/interrupt, and
server-to-client approval requests for file changes and commands.
A turn whose text contains "write" asks to create notes.md; "run" asks to run
a command. The file is really written in the thread's cwd when approved.
"""
import json
import os
import sys

state = {"cwd": os.getcwd(), "turn": 0, "req": 100, "logged_in": False, "init": False}


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def notify(method, params):
    send({"method": method, "params": params})


def ask(method, params):
    state["req"] += 1
    rid = state["req"]
    send({"id": rid, "method": method, "params": params})
    for line in sys.stdin:  # wait for the client's answer to this request
        msg = json.loads(line)
        if msg.get("id") == rid and "method" not in msg:
            return (msg.get("result") or {}).get("decision")
    sys.exit(0)


def run_turn(thread_id, text):
    state["turn"] += 1
    tid = f"turn_{state['turn']}"
    notify("turn/started", {"threadId": thread_id, "turn": {"id": tid, "status": "inProgress"}})
    notify("item/started", {"threadId": thread_id, "turnId": tid, "item": {"id": "msg_a", "type": "agentMessage", "text": ""}})
    notify("item/agentMessage/delta", {"threadId": thread_id, "turnId": tid, "itemId": "msg_a", "delta": "Je regarde "})
    notify("item/agentMessage/delta", {"threadId": thread_id, "turnId": tid, "itemId": "msg_a", "delta": "le dossier."})
    notify("item/completed", {"threadId": thread_id, "turnId": tid,
                              "item": {"id": "msg_a", "type": "agentMessage", "text": "Je regarde le dossier.", "phase": "commentary"}})
    if "write" in text:
        change = {"id": "fc_1", "type": "fileChange", "status": "inProgress",
                  "changes": [{"path": "notes.md", "kind": "add", "diff": "+# Notes\n+hello"}]}
        notify("item/started", {"threadId": thread_id, "turnId": tid, "item": change})
        decision = ask("item/fileChange/requestApproval", {"itemId": "fc_1", "threadId": thread_id, "turnId": tid,
                                                          "reason": "Create notes.md"})
        ok = decision in ("accept", "acceptForSession")
        if ok:
            with open(os.path.join(state["cwd"], "notes.md"), "w", encoding="utf-8") as fh:
                fh.write("# Notes\nhello\n")
        notify("item/completed", {"threadId": thread_id, "turnId": tid,
                                  "item": {**change, "status": "completed" if ok else "declined"}})
    if "run" in text:
        cmd = {"id": "cmd_1", "type": "commandExecution", "command": "echo hi", "cwd": state["cwd"], "status": "inProgress",
               "commandActions": []}
        notify("item/started", {"threadId": thread_id, "turnId": tid, "item": cmd})
        decision = ask("item/commandExecution/requestApproval", {"itemId": "cmd_1", "threadId": thread_id, "turnId": tid,
                                                                "command": "echo hi", "cwd": state["cwd"],
                                                                "reason": "Say hi"})
        ok = decision in ("accept", "acceptForSession")
        notify("item/completed", {"threadId": thread_id, "turnId": tid, "item": {
            **cmd, "status": "completed" if ok else "declined", "aggregatedOutput": "hi\n" if ok else None,
            "exitCode": 0 if ok else None}})
    notify("item/completed", {"threadId": thread_id, "turnId": tid,
                              "item": {"id": "msg_b", "type": "agentMessage", "text": "Fait.", "phase": "final_answer"}})
    notify("turn/completed", {"threadId": thread_id, "turn": {"id": tid, "status": "completed"}})


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if method == "initialize":
        state["init"] = True
        send({"id": mid, "result": {"userAgent": "fake-codex/0.0"}})
    elif method == "initialized":
        pass
    elif not state["init"]:
        send({"id": mid, "error": {"code": -32002, "message": "Not initialized"}})
    elif method == "account/login/start":
        ok = params.get("type") == "apiKey" and str(params.get("apiKey", "")).startswith("sk-")
        if not ok:
            send({"id": mid, "error": {"code": -32600, "message": "invalid api key"}})
            continue
        state["logged_in"] = True
        send({"id": mid, "result": {"type": "apiKey"}})
        notify("account/login/completed", {"loginId": None, "success": True})
    elif method == "thread/start":
        if not state["logged_in"]:
            send({"id": mid, "error": {"code": -32600, "message": "not logged in"}})
            continue
        state["cwd"] = params.get("cwd") or state["cwd"]
        send({"id": mid, "result": {"thread": {"id": "thr_1"}}})
        notify("thread/started", {"thread": {"id": "thr_1"}})
    elif method == "turn/start":
        text = " ".join(i.get("text", "") for i in params.get("input", []) if i.get("type") == "text")
        send({"id": mid, "result": {"turn": {"id": f"turn_{state['turn'] + 1}", "status": "inProgress"}}})
        run_turn(params.get("threadId"), text)
    elif method == "turn/interrupt":
        send({"id": mid, "result": {}})
    elif mid is not None:
        send({"id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}})
