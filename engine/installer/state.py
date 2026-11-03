"""install_state.json: what the bootstrap verified, and when."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from engine.events import utc_now
from engine.paths import Layout

STATE_SCHEMA = 1


def load_state(layout: Layout) -> dict[str, Any]:
    try:
        data = json.loads(layout.state_file.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("schema") == STATE_SCHEMA:
            return data
    except (OSError, ValueError):
        pass
    return {"schema": STATE_SCHEMA, "installed": False, "steps": {}}


def save_state(layout: Layout, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    atomic_write_json(layout.state_file, state)


def atomic_write_json(path: Path, data: Any, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    if private and os.name == "posix":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def load_config(layout: Layout) -> dict[str, Any]:
    defaults = {"port": 8765}
    try:
        data = json.loads(layout.config_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            defaults.update(data)
    except (OSError, ValueError):
        pass
    return defaults
