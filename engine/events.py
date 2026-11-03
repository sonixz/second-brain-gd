"""Structured event stream between the Python engine and Godot. Stdlib only.

One JSON object per line (JSON Lines), appended and flushed immediately.
Godot tails the file while the bootstrap runs. See
docs/architecture/events-protocol.md for the full contract.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PROTOCOL_VERSION = 1
STATUSES = ("started", "progress", "log", "ok", "skipped", "warning", "error")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class EventWriter:
    def __init__(self, path: Path | None, run_id: str, echo: bool = True) -> None:
        self.path = path
        self.run_id = run_id
        self.echo = echo
        self._fh = None
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(path, "a", encoding="utf-8", newline="\n")

    def add_listener(self, fn: Callable[[dict[str, Any]], None]) -> None:
        self._listeners.append(fn)

    def emit(
        self,
        component: str,
        stage: str,
        status: str,
        message: str,
        progress: float | None = None,
        **details: Any,
    ) -> dict[str, Any]:
        if status not in STATUSES:
            raise ValueError(f"unknown status {status!r}")
        event: dict[str, Any] = {
            "v": PROTOCOL_VERSION,
            "timestamp": utc_now(),
            "run_id": self.run_id,
            "component": component,
            "stage": stage,
            "status": status,
            "message": message,
        }
        if progress is not None:
            event["progress"] = round(max(0.0, min(1.0, progress)), 4)
        if details:
            event["details"] = details
        line = json.dumps(event, ensure_ascii=False)
        if self._fh is not None:
            self._fh.write(line + "\n")
            self._fh.flush()
        if self.echo:
            print(line, file=sys.stdout, flush=True)
        for fn in self._listeners:
            fn(event)
        return event

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
