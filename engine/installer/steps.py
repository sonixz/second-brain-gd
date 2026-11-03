"""The setup procedure. Each step checks the real state first, so a rerun
skips what is already done and resumes after the step that failed."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

from engine import VERSION, database
from engine.events import EventWriter, utc_now
from engine.installer.state import atomic_write_json, load_config, load_state, save_state
from engine.paths import LOCK_FILE, REPO_ROOT, Layout
from engine.procutil import pid_alive, terminate

PYTHON_DOWNLOAD = "https://www.python.org/downloads/"
PORT_SCAN = 20
HEALTH_TIMEOUT_S = 25.0
# Anything that can go wrong while talking to a local port that is not ready yet
# (refused, reset, timeout, garbage such as a TCP self-connect echo on Windows).
NET_ERRORS = (OSError, ValueError, http.client.HTTPException)


class SetupFailed(Exception):
    pass


# Weight of each step in the overall progress bar (sums to 1.0).
STEPS: list[tuple[str, float, str]] = [
    ("python", 0.04, "Python interpreter"),
    ("directories", 0.04, "Data directories"),
    ("venv", 0.14, "Virtual environment"),
    ("dependencies", 0.46, "Locked dependencies"),
    ("database", 0.08, "SQLite database"),
    ("service", 0.16, "Local API service"),
    ("health", 0.08, "Health verification"),
]


def is_store_python() -> bool:
    markers = ("WindowsApps", "PythonSoftwareFoundation.Python")
    return sys.platform == "win32" and any(m in sys.base_prefix or m in sys.executable for m in markers)


def lock_sha256() -> str:
    return hashlib.sha256(LOCK_FILE.read_bytes()).hexdigest()


def _no_window() -> dict[str, Any]:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def http_json(url: str, token: str | None = None, method: str = "GET", timeout: float = 3.0) -> dict[str, Any]:
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if os.name == "posix":
            # uvicorn binds with SO_REUSEADDR: a port in TIME_WAIT after our own
            # restart is usable. (On Windows that flag means "steal"; not used.)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def read_server_file(layout: Layout) -> dict[str, Any] | None:
    try:
        return json.loads(layout.server_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def running_server(layout: Layout) -> dict[str, Any] | None:
    """The API we started earlier, if it is alive and answers as itself."""
    info = read_server_file(layout)
    if not info or not pid_alive(int(info.get("pid", 0))):
        return None
    try:
        health = http_json(f"http://127.0.0.1:{info['port']}/health", timeout=2.0)
    except NET_ERRORS + (KeyError,):
        return None
    if health.get("instance_id") != info.get("instance_id"):
        return None
    return info


def stop_server(layout: Layout, timeout: float = 5.0) -> dict[str, Any]:
    info = read_server_file(layout)
    if not info:
        return {"stopped": False, "reason": "no server file"}
    pid = int(info.get("pid", 0))
    if not pid_alive(pid):
        layout.server_file.unlink(missing_ok=True)
        return {"stopped": False, "reason": "not running"}
    try:
        token = layout.token_file.read_text(encoding="utf-8").strip()
        http_json(f"http://127.0.0.1:{info['port']}/system/shutdown", token=token, method="POST")
    except NET_ERRORS:
        pass
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and pid_alive(pid):
        time.sleep(0.1)
    graceful = not pid_alive(pid)
    if not graceful:
        terminate(pid)
    layout.server_file.unlink(missing_ok=True)
    return {"stopped": True, "graceful": graceful, "pid": pid}


class Installer:
    def __init__(self, layout: Layout, events: EventWriter, port: int | None = None,
                 parent_pid: int | None = None, start_service: bool = True) -> None:
        self.layout = layout
        self.events = events
        self.port_override = port
        self.parent_pid = parent_pid
        self.start_service = start_service
        self.state: dict[str, Any] = {}
        self._done_weight = 0.0
        self._db_ready = False
        self._pending_db_events: list[dict[str, Any]] = []
        self._log_fh = None
        self.events.add_listener(self._persist_event)

    # ---------------------------------------------------------------- events
    def _persist_event(self, event: dict[str, Any]) -> None:
        if self._log_fh is not None:
            self._log_fh.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._log_fh.flush()
        if event["status"] == "log":
            return  # raw tool output stays in the log file, not in the database
        if not self._db_ready:
            self._pending_db_events.append(event)
            return
        try:
            with database.session(self.layout.database) as conn:
                database.record_event(conn, event)
        except Exception:  # the stream must never break because of history
            pass

    def _flush_pending(self) -> None:
        with database.session(self.layout.database) as conn:
            for ev in self._pending_db_events:
                database.record_event(conn, ev)
        self._pending_db_events.clear()

    def emit(self, component: str, stage: str, status: str, message: str,
             step_fraction: float | None = None, **details: Any) -> None:
        weight = dict((n, w) for n, w, _ in STEPS).get(component, 0.0)
        progress = None
        if step_fraction is not None:
            progress = self._done_weight + weight * step_fraction
        self.events.emit(component, stage, status, message, progress, **details)

    def fail(self, component: str, message: str, hint: str | None = None, **details: Any) -> None:
        if hint:
            details["hint"] = hint
        self.emit(component, "failed", "error", message, **details)
        self._mark(component, "error", message=message)
        self.events.emit("bootstrap", "done", "error", f"Setup stopped at step '{component}'. You can retry.",
                         round(self._done_weight, 4), failed_step=component)
        raise SetupFailed(component)

    def _mark(self, step: str, status: str, **extra: Any) -> None:
        self.state.setdefault("steps", {})[step] = {"status": status, "at": utc_now(), **extra}
        try:
            save_state(self.layout, self.state)
        except OSError:
            pass

    # ------------------------------------------------------------------ run
    def run(self) -> None:
        started = time.monotonic()
        self.events.emit("bootstrap", "begin", "started", f"Second Brain GD bootstrap {VERSION}", 0.0,
                         data_dir=str(self.layout.root))
        steps: dict[str, Callable[[], None]] = {
            "python": self.step_python,
            "directories": self.step_directories,
            "venv": self.step_venv,
            "dependencies": self.step_dependencies,
            "database": self.step_database,
            "service": self.step_service,
            "health": self.step_health,
        }
        try:
            for name, weight, label in STEPS:
                if name in ("service", "health") and not self.start_service:
                    self.emit(name, "skip", "skipped", f"{label}: not requested (--no-start)", 1.0)
                else:
                    self.emit(name, "begin", "started", f"{label}…", 0.0)
                    steps[name]()
                self._done_weight += weight
            self.state["installed"] = True
            self.state["last_success_at"] = utc_now()
            save_state(self.layout, self.state)
            elapsed = round(time.monotonic() - started, 1)
            self.events.emit("bootstrap", "done", "ok", f"System ready in {elapsed} s.", 1.0,
                             elapsed_s=elapsed, port=self.state.get("service", {}).get("port"))
        finally:
            self._release_lock()
            if self._log_fh is not None:
                self._log_fh.close()

    # ---------------------------------------------------------------- steps
    def step_python(self) -> None:
        info = {
            "executable": sys.executable,
            "version": "%d.%d.%d" % sys.version_info[:3],
            "implementation": sys.implementation.name,
            "store_python": is_store_python(),
        }
        try:
            import ensurepip  # noqa: F401
            import venv  # noqa: F401
        except ImportError:
            self.fail("python", "This Python has no 'venv'/'ensurepip' module.",
                      hint="On Debian/Ubuntu: sudo apt install python3-venv. "
                           f"Or install Python from {PYTHON_DOWNLOAD}", **info)
        self.state = load_state(self.layout)
        self.state["python"] = info
        self.emit("python", "check", "ok", f"Python {info['version']} at {info['executable']}", 1.0, **info)

    def step_directories(self) -> None:
        root_existed = self.layout.root.exists()
        if is_store_python() and not root_existed:
            # Microsoft Store Python silently redirects new folders under AppData
            # to a private location that Godot cannot see. A folder created by
            # another process beforehand is written in place.
            self.fail("directories", f"The data folder {self.layout.root} must exist before setup "
                      "when using the Microsoft Store Python.",
                      hint="Launch setup from Godot (it creates the folder), or create the folder manually.")
        created = []
        for d in self.layout.directories():
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
                created.append(d.name)
        if os.name == "posix":
            os.chmod(self.layout.runtime, 0o700)
        self._take_lock()
        # Keep the last few UI event streams for troubleshooting, drop older ones.
        streams = sorted(self.layout.runtime.glob("events-*.jsonl"), key=lambda f: f.stat().st_mtime)
        for old_stream in streams[:-10]:
            old_stream.unlink(missing_ok=True)
        self._log_fh = open(self.layout.logs / "bootstrap.log", "a", encoding="utf-8")
        if not self.layout.config_file.exists():
            atomic_write_json(self.layout.config_file, load_config(self.layout))
        # Write the in-memory state now that the folder exists.
        self._mark("python", "ok", version=self.state["python"]["version"])
        if created:
            self.emit("directories", "create", "ok", f"Created {', '.join(created)} in {self.layout.root}", 1.0)
        else:
            self.emit("directories", "check", "skipped", f"Data folders already present in {self.layout.root}", 1.0)
        self._mark("directories", "ok")

    def _take_lock(self) -> None:
        lock = self.layout.lock_file
        if lock.exists():
            try:
                other = int(lock.read_text().strip() or 0)
            except (OSError, ValueError):
                other = 0
            if other and other != os.getpid() and pid_alive(other):
                self.fail("directories", f"Another setup is already running (pid {other}).",
                          hint="Wait for it to finish, then retry.")
        lock.write_text(str(os.getpid()))

    def _release_lock(self) -> None:
        try:
            if self.layout.lock_file.read_text().strip() == str(os.getpid()):
                self.layout.lock_file.unlink()
        except OSError:
            pass

    def _venv_version(self) -> str | None:
        py = self.layout.venv_python
        if not py.exists():
            return None
        try:
            out = subprocess.run([str(py), "-c", "import sys;print('%d.%d.%d' % sys.version_info[:3])"],
                                 capture_output=True, text=True, timeout=30, **_no_window())
        except (OSError, subprocess.TimeoutExpired):
            return None
        return out.stdout.strip() if out.returncode == 0 else None

    def step_venv(self) -> None:
        current = "%d.%d" % sys.version_info[:2]
        existing = self._venv_version()
        if existing and existing.rsplit(".", 1)[0] == current:
            self.emit("venv", "check", "skipped", f"Virtual environment OK (Python {existing})", 1.0,
                      path=str(self.layout.venv))
            self._mark("venv", "ok", python=existing)
            self.state["venv_python"] = str(self.layout.venv_python)
            return
        if self.layout.venv.exists():
            reason = f"built for Python {existing}" if existing else "broken"
            self.emit("venv", "recreate", "warning", f"Existing virtual environment is {reason}; recreating it.")
            shutil.rmtree(self.layout.venv)
        self.emit("venv", "create", "progress", f"Creating {self.layout.venv} (with pip)…", 0.2)
        import venv as venv_mod

        try:
            venv_mod.EnvBuilder(with_pip=True, clear=False, symlinks=(os.name != "nt")).create(str(self.layout.venv))
        except Exception as exc:  # venv raises a mix of OSError/CalledProcessError
            self.fail("venv", f"Could not create the virtual environment: {exc}",
                      hint="Check free disk space and antivirus quarantine, then retry.")
        version = self._venv_version()
        if not version:
            self.fail("venv", "The virtual environment was created but its Python does not run.")
        self.state["venv_python"] = str(self.layout.venv_python)
        self.emit("venv", "create", "ok", f"Virtual environment ready (Python {version})", 1.0)
        self._mark("venv", "ok", python=version)

    def _deps_importable(self) -> bool:
        try:
            out = subprocess.run([str(self.layout.venv_python), "-c", "import fastapi, uvicorn, psutil, websockets, keyring, pypdf"],
                                 capture_output=True, timeout=60, **_no_window())
        except (OSError, subprocess.TimeoutExpired):
            return False
        return out.returncode == 0

    def step_dependencies(self) -> None:
        digest = lock_sha256()
        previous = self.state.get("steps", {}).get("dependencies", {})
        if previous.get("status") == "ok" and previous.get("lock_sha256") == digest and self._deps_importable():
            self.emit("dependencies", "check", "skipped", "Locked dependencies already installed", 1.0,
                      lock_sha256=digest[:12])
            return
        packages = [ln.split("==")[0].strip() for ln in LOCK_FILE.read_text().splitlines()
                    if "==" in ln and not ln.startswith((" ", "#"))]
        total = max(1, len(packages))
        cmd = [str(self.layout.venv_python), "-m", "pip", "install", "--require-hashes", "--only-binary=:all:",
               "--no-input", "--disable-pip-version-check", "--progress-bar", "off", "-r", str(LOCK_FILE)]
        self.emit("dependencies", "install", "progress",
                  f"Installing {total} pinned packages (hash-verified wheels from PyPI)…", 0.02)
        env = dict(os.environ, PYTHONUNBUFFERED="1", PIP_NO_COLOR="1")
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                    encoding="utf-8", errors="replace", env=env, **_no_window())
        except OSError as exc:
            self.fail("dependencies", f"Could not run pip: {exc}")
        seen: set[str] = set()
        tail: list[str] = []
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip()
            if not line:
                continue
            tail = (tail + [line])[-15:]
            self.emit("dependencies", "pip", "log", line)
            low = line.lower()
            for verb in ("collecting ", "downloading ", "using cached "):
                if low.startswith(verb):
                    target = low[len(verb):].split(" ")[0]
                    # "pkg==1.0" when collecting, "pkg_name-1.0-py3-none-any.whl" when downloading
                    name = target.split("==")[0] if "==" in target else target.split("-")[0]
                    name = name.replace("_", "-")
                    if name in packages and name not in seen:
                        seen.add(name)
                        frac = min(0.85, 0.05 + 0.8 * len(seen) / total)
                        self.emit("dependencies", "download", "progress",
                                  f"Fetched {len(seen)}/{total}: {name}", frac)
            if low.startswith("installing collected packages"):
                self.emit("dependencies", "install", "progress", "Installing packages into the environment…", 0.9)
        code = proc.wait()
        if code != 0:
            self.fail("dependencies", f"pip exited with code {code}.",
                      hint="Check the internet connection (PyPI) and the log below, then retry.",
                      tail="\n".join(tail))
        if not self._deps_importable():
            self.fail("dependencies", "Packages installed but cannot be imported.")
        self.emit("dependencies", "verify", "ok", f"{total} packages installed and importable", 1.0)
        self._mark("dependencies", "ok", lock_sha256=digest)

    def step_database(self) -> None:
        db = self.layout.database
        existed = db.exists()
        try:
            result = database.migrate(db)
        except database.MigrationError as exc:
            self.fail("database", str(exc), hint="Your data was not modified by the failed migration.")
        except Exception as exc:
            self.fail("database", f"Cannot open {db}: {exc}")
        self._db_ready = True
        self._flush_pending()
        with database.session(db) as conn:
            if database.get_setting(conn, "installed_at") is None:
                database.set_setting(conn, "installed_at", utc_now())
            database.set_setting(conn, "app_version", VERSION)
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        msg = (f"Applied {', '.join(result['applied'])}" if result["applied"]
               else f"Schema up to date (version {result['schema_version']})")
        status = "ok" if result["applied"] or not existed else "skipped"
        self.emit("database", "migrate", status, msg, 1.0, path=str(db), schema_version=result["schema_version"],
                  tables=sorted(tables))
        self.state["database"] = {"path": str(db), "schema_version": result["schema_version"]}
        self._mark("database", "ok", schema_version=result["schema_version"])

    def _choose_port(self) -> int:
        configured = int(self.port_override or os.environ.get("SBGD_PORT") or load_config(self.layout)["port"])
        for port in range(configured, configured + PORT_SCAN):
            if port_free(port):
                if port != configured:
                    self.emit("service", "port", "warning",
                              f"Port {configured} is busy; using {port} instead.", 0.2)
                return port
        self.fail("service", f"No free port between {configured} and {configured + PORT_SCAN - 1}.",
                  hint=f"Set another 'port' in {self.layout.config_file}.")
        raise AssertionError  # unreachable

    def step_service(self) -> None:
        current = running_server(self.layout)
        orphaned = current and current.get("parent_pid") and not pid_alive(int(current["parent_pid"]))
        if orphaned:
            # Its watchdog is about to stop it: do not reuse a server that is going away.
            self.emit("service", "replace", "progress",
                      f"The running API (pid {current['pid']}) belongs to a closed app; replacing it…", 0.2)
            stop_server(self.layout)
            current = None
        if current and self.parent_pid and current.get("parent_pid") != self.parent_pid:
            # The watchdog must follow the app that asked for the engine now.
            self.emit("service", "reattach", "progress",
                      f"Restarting the running API (pid {current['pid']}) to attach it to this app…", 0.2)
            stop_server(self.layout)
            current = None
        if current:
            self._server = current
            self.emit("service", "check", "skipped",
                      f"API already running (pid {current['pid']}, port {current['port']})", 1.0)
            self.state["service"] = {"port": current["port"]}
            self._mark("service", "ok", port=current["port"])
            return
        stale = read_server_file(self.layout)
        if stale:
            terminate(int(stale.get("pid", 0)))  # only ever a process this app started
            self.layout.server_file.unlink(missing_ok=True)
        port = self._choose_port()
        token = secrets.token_urlsafe(32)
        atomic_write_json_text(self.layout.token_file, token)
        instance_id = uuid.uuid4().hex
        cmd = [str(self.layout.venv_python), "-m", "engine.api.server", "--data-dir", str(self.layout.root),
               "--port", str(port), "--instance-id", instance_id]
        if self.parent_pid:
            cmd += ["--parent-pid", str(self.parent_pid)]
        env = dict(os.environ, SBGD_API_TOKEN=token, PYTHONUNBUFFERED="1")
        log = open(self.layout.logs / "server.log", "a", encoding="utf-8")
        kwargs: dict[str, Any] = {"cwd": str(REPO_ROOT), "env": env, "stdout": log, "stderr": subprocess.STDOUT,
                                  "stdin": subprocess.DEVNULL}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True  # survives the bootstrap, not tied to its terminal
        self.emit("service", "spawn", "progress", f"Starting API on 127.0.0.1:{port}…", 0.4)
        try:
            proc = subprocess.Popen(cmd, **kwargs)
        except OSError as exc:
            self.fail("service", f"Could not start the API: {exc}")
        finally:
            log.close()
        self._server = {"pid": proc.pid, "port": port, "instance_id": instance_id, "proc": proc}
        self.emit("service", "spawn", "ok", f"API process started (pid {proc.pid})", 1.0, pid=proc.pid, port=port)
        self.state["service"] = {"port": port}
        self._mark("service", "ok", port=port)

    def step_health(self) -> None:
        srv = self._server
        base = f"http://127.0.0.1:{srv['port']}"
        deadline = time.monotonic() + HEALTH_TIMEOUT_S
        attempt = 0
        health: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            attempt += 1
            proc = srv.get("proc")
            if proc is not None and proc.poll() is not None:
                self.fail("health", f"The API exited during startup (code {proc.returncode}).",
                          hint=f"See {self.layout.logs / 'server.log'}.", tail=self._server_log_tail())
            try:
                health = http_json(f"{base}/health", timeout=1.5)
                break
            except NET_ERRORS:
                frac = min(0.8, (time.monotonic() - (deadline - HEALTH_TIMEOUT_S)) / HEALTH_TIMEOUT_S)
                if attempt % 4 == 1:
                    self.emit("health", "wait", "progress", f"Waiting for {base}/health (attempt {attempt})…", frac)
                time.sleep(0.25)
        if health is None:
            self.fail("health", f"No answer from {base}/health after {HEALTH_TIMEOUT_S:.0f} s.",
                      tail=self._server_log_tail())
        if health.get("status") != "ok" or health.get("instance_id") != srv["instance_id"]:
            self.fail("health", "Something else answered on the API port.", details=health)
        token = self.layout.token_file.read_text(encoding="utf-8").strip()
        try:
            status = http_json(f"{base}/system/status", token=token)
        except NET_ERRORS as exc:
            self.fail("health", f"Authenticated call failed: {exc}")
        try:
            http_json(f"{base}/system/status")
            self.fail("health", "The API accepted a request without a token.")
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                self.fail("health", f"Unexpected status {exc.code} for an unauthenticated call.")
        self.emit("health", "verify", "ok",
                  f"/health OK, database {health.get('database')}, auth enforced, pid {status['process']['pid']}",
                  1.0, port=srv["port"], pid=status["process"]["pid"])
        self._mark("health", "ok", port=srv["port"])

    def _server_log_tail(self, n: int = 20) -> str:
        try:
            lines = (self.layout.logs / "server.log").read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return ""
        return "\n".join(lines[-n:])


def atomic_write_json_text(path: Path, text: str) -> None:
    """Write a secret file readable only by the current user."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(tmp, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)
