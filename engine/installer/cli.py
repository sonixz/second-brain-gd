from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from engine.events import EventWriter
from engine.installer.steps import Installer, SetupFailed, stop_server
from engine.installer.state import load_state
from engine.paths import Layout, default_data_dir


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bootstrap.py", description="Second Brain GD bootstrap")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("setup", "status", "stop"):
        s = sub.add_parser(name)
        s.add_argument("--data-dir", type=Path, default=None)
        if name == "setup":
            s.add_argument("--events", type=Path, default=None, help="JSON Lines event file for the UI")
            s.add_argument("--port", type=int, default=None)
            s.add_argument("--parent-pid", type=int, default=None,
                           help="the API stops by itself when this process exits")
            s.add_argument("--quiet", action="store_true", help="do not echo events on stdout")
            s.add_argument("--no-start", action="store_true", help="install only, do not start the API")
    return p


def run(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    layout = Layout((args.data_dir or default_data_dir()).expanduser().resolve())
    if args.command == "status":
        print(json.dumps(load_state(layout), indent=2))
        return 0
    if args.command == "stop":
        print(json.dumps(stop_server(layout)))
        return 0
    run_id = uuid.uuid4().hex[:12]
    events = EventWriter(args.events, run_id, echo=not args.quiet)
    installer = Installer(layout, events, port=args.port, parent_pid=args.parent_pid,
                          start_service=not args.no_start)
    try:
        installer.run()
        return 0
    except SetupFailed:
        return 1
    except KeyboardInterrupt:
        events.emit("bootstrap", "done", "error", "Setup interrupted.")
        return 130
    except Exception as exc:  # last resort: never die without telling the UI
        events.emit("bootstrap", "done", "error", f"Unexpected error: {exc.__class__.__name__}: {exc}")
        raise
    finally:
        events.close()
        sys.stdout.flush()
