"""Local MCP servers (Loop MCP-F): programs the Brain starts on this computer and talks to over stdio.

Nothing runs without the owner's approval of the exact command; a package's version is pinned (never « latest »);
the runtime it needs (Node's npx, uv's uvx, Docker, Python) is detected, never installed: the window says what is
missing and where to get it. The process gets a clean environment (no secret of the Brain is inherited; only the
variables the server declares, filled from the OS credential store), runs without a window, stops with the app,
and its error output is kept as a short log. Same permissions, guard, budget and lights as remote servers.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from typing import Any

RUNTIMES = {
    "npx": "Node.js (nodejs.org) — it brings npx",
    "uvx": "uv (docs.astral.sh/uv) — it brings uvx",
    "docker": "Docker Desktop (docker.com)",
    "python": "Python (python.org)",
    "python3": "Python (python.org)",
    "node": "Node.js (nodejs.org)",
}
# What a local server keeps from the Brain's environment: just enough to run (paths, temp, the user's folders).
KEEP_ENV = ("PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "HOME", "USERPROFILE",
            "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "LANG", "LC_ALL", "TZ")


class LocalError(RuntimeError):
    pass


def command_for_package(registry_type: str, identifier: str, version: str) -> list[str]:
    """The pinned command for a registry package (npm → npx, pypi → uvx, oci → docker)."""
    if not version or version.lower() in ("latest", "*"):
        raise LocalError("a local server needs a pinned version (not « latest »)")
    if not re.fullmatch(r"[@\w./:-]{1,200}", identifier) or not re.fullmatch(r"[\w.+-]{1,60}", version):
        raise LocalError("this package name or version looks wrong")
    if registry_type == "npm":
        return ["npx", "-y", f"{identifier}@{version}"]
    if registry_type == "pypi":
        return ["uvx", f"{identifier}=={version}"]
    if registry_type == "oci":
        return ["docker", "run", "-i", "--rm", f"{identifier}:{version}"]
    raise LocalError(f"packages of type « {registry_type} » are not supported")


def parse_command(command: str | list[str]) -> list[str]:
    argv = list(command) if isinstance(command, list) else shlex.split(command, posix=os.name != "nt")
    argv = [str(a) for a in argv if str(a).strip()]
    if not argv:
        raise LocalError("the command is empty")
    if any(ch in " ".join(argv) for ch in ("|", "&&", ";", "`", "$(")):
        raise LocalError("one program with its arguments only (no pipes or chained commands)")
    tool = os.path.basename(argv[0]).lower().removesuffix(".exe").removesuffix(".cmd")
    joined = " ".join(argv[1:])
    package = next((a for a in argv[1:] if not a.startswith("-")), "")
    if tool == "npx" and not re.search(r".@\d", package):
        raise LocalError("pin the package version (e.g. npx -y @scope/server@1.2.3), never latest")
    if tool == "uvx" and "==" not in joined:
        raise LocalError("pin the package version (e.g. uvx package==1.2.3)")
    if tool == "docker" and not re.search(r":[\w.+-]+(\s|$)", joined + " "):
        raise LocalError("pin the image version (e.g. image:1.2.3)")
    return argv


def command_hash(argv: list[str]) -> str:
    return hashlib.sha256(json.dumps(argv).encode()).hexdigest()[:20]


def missing_runtime(argv: list[str]) -> str:
    """'' when the program is found; else what to install (the user installs it, the Brain never does)."""
    if shutil.which(argv[0]) or os.path.isfile(argv[0]):
        return ""
    tool = os.path.basename(argv[0]).lower().removesuffix(".exe").removesuffix(".cmd")
    return RUNTIMES.get(tool, argv[0])


def clean_env(extra: dict[str, str]) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k.upper() in KEEP_ENV}
    env.update(extra)
    return env


class StdioSession:
    """One running local server: newline-delimited JSON-RPC on stdin / stdout, stderr kept as a short log."""

    def __init__(self, argv: list[str], env: dict[str, str], on_request: Any = None):
        self.on_request = on_request
        self.replies: dict[Any, dict[str, Any]] = {}
        self.cv = threading.Condition()
        self.log: deque[str] = deque(maxlen=200)
        self.closed = False
        exe = shutil.which(argv[0]) or argv[0]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.proc = subprocess.Popen([exe, *argv[1:]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         env=env, creationflags=flags, bufsize=0)
        except OSError as exc:
            raise LocalError(f"the program could not start ({exc.__class__.__name__})") from exc
        threading.Thread(target=self._read_out, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()

    def _read_out(self) -> None:
        for raw in iter(self.proc.stdout.readline, b""):
            try:
                m = json.loads(raw.decode("utf-8", errors="replace"))
            except ValueError:
                self.log.append("(stdout) " + raw.decode("utf-8", errors="replace").rstrip()[:300])
                continue
            for one in (m if isinstance(m, list) else [m]):
                if not isinstance(one, dict):
                    continue
                if one.get("method") and "id" in one:  # the server asks something back
                    from engine.mcp.client import _answer_server
                    threading.Thread(target=lambda r=one: self.write(_answer_server(r, self.on_request, "")), daemon=True).start()
                elif "id" in one:
                    with self.cv:
                        self.replies[one["id"]] = one
                        self.cv.notify_all()
        with self.cv:
            self.closed = True
            self.cv.notify_all()

    def _read_err(self) -> None:
        for raw in iter(self.proc.stderr.readline, b""):
            self.log.append(raw.decode("utf-8", errors="replace").rstrip()[:300])

    def write(self, msg: dict[str, Any]) -> None:
        try:
            self.proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
            self.proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise LocalError("the local server stopped") from exc

    def send(self, msg: dict[str, Any], timeout: float = 60.0, cancelled: Any = None) -> dict[str, Any] | None:
        self.write(msg)
        if "id" not in msg:
            return None
        end = time.time() + timeout
        with self.cv:
            while msg["id"] not in self.replies:
                if self.closed:
                    raise LocalError("the local server stopped: " + (self.log[-1] if self.log else "no message"))
                if cancelled and cancelled():
                    raise LocalError("stopped by the user")
                left = end - time.time()
                if left <= 0:
                    raise LocalError("the local server did not answer in time")
                self.cv.wait(min(left, 0.25))
            return self.replies.pop(msg["id"])

    def alive(self) -> bool:
        return self.proc.poll() is None and not self.closed

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.terminate()
            self.proc.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            try:
                self.proc.kill()
                self.proc.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                pass
        for pipe in (self.proc.stdout, self.proc.stderr):
            try:
                if pipe:
                    pipe.close()
            except OSError:
                pass
