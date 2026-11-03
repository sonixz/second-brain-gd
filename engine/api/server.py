"""Process entry point for the local API: python -m engine.api.server ...

Lifecycle (see docs/architecture/process-lifecycle.md):
- started detached by the bootstrap, token passed via SBGD_API_TOKEN;
- writes runtime/server.json once listening;
- stops on POST /system/shutdown, on SIGTERM/SIGINT, or when --parent-pid exits;
- removes runtime/server.json and records 'stopped' on the way out.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

import psutil
import uvicorn

from engine import database
from engine.api.app import create_app
from engine.events import utc_now
from engine.installer.state import atomic_write_json
from engine.paths import Layout

WATCHDOG_INTERVAL_S = 1.0


def _record(layout: Layout, stage: str, event_status: str, message: str, service: dict | None = None) -> None:
    try:
        with database.session(layout.database) as conn:
            database.record_event(conn, {"timestamp": utc_now(), "run_id": None, "component": "api",
                                         "stage": stage, "status": event_status, "message": message})
            if service:
                database.upsert_service_status(conn, "api", **service)
    except Exception as exc:  # never crash the server because history failed
        print(f"[server] could not record event: {exc}", file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--instance-id", required=True)
    p.add_argument("--parent-pid", type=int, default=None)
    args = p.parse_args(argv)

    token = os.environ.pop("SBGD_API_TOKEN", "")
    if not token:
        print("[server] SBGD_API_TOKEN is missing; refusing to start without auth", file=sys.stderr)
        return 2
    layout = Layout(args.data_dir.resolve())
    server_box: dict[str, uvicorn.Server] = {}
    stop_reason = {"why": "signal"}

    def request_shutdown(why: str = "shutdown request") -> None:
        stop_reason["why"] = why
        srv = server_box.get("srv")
        if srv is not None:
            srv.should_exit = True

    def on_started() -> None:
        atomic_write_json(layout.server_file, {
            "pid": os.getpid(), "port": args.port, "instance_id": args.instance_id,
            "parent_pid": args.parent_pid, "started_at": utc_now(),
        })
        _record(layout, "start", "ok", f"API started on 127.0.0.1:{args.port} (pid {os.getpid()})",
                service={"status": "running", "pid": os.getpid(), "port": args.port, "started_at": utc_now(),
                         "message": None})

    app = create_app(layout, token, args.instance_id, args.port, request_shutdown=request_shutdown,
                     on_started=on_started)

    config = uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="info", access_log=False,
                            lifespan="on", timeout_graceful_shutdown=3)
    server = uvicorn.Server(config)
    server_box["srv"] = server

    if args.parent_pid:
        def watchdog() -> None:
            while not server.should_exit:
                if not psutil.pid_exists(args.parent_pid) or _is_zombie(args.parent_pid):
                    request_shutdown(f"parent process {args.parent_pid} exited")
                    return
                time.sleep(WATCHDOG_INTERVAL_S)

        threading.Thread(target=watchdog, name="parent-watchdog", daemon=True).start()

    try:
        server.run()
    finally:
        _record(layout, "stop", "ok", f"API stopped ({stop_reason['why']})",
                service={"status": "stopped", "last_check_at": utc_now(), "message": stop_reason["why"]})
        try:
            info = json.loads(layout.server_file.read_text(encoding="utf-8"))
            if info.get("pid") == os.getpid():
                layout.server_file.unlink()
        except (OSError, ValueError):
            pass
        try:
            if layout.token_file.read_text(encoding="utf-8").strip() == token:
                layout.token_file.unlink()  # the token dies with the server
        except OSError:
            pass
    return 0


def _is_zombie(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True
    except psutil.Error:
        return False


if __name__ == "__main__":
    sys.exit(main())
