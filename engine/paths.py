"""Data directory layout. Stdlib only.

User data never lives inside the repository. The default location follows the
operating system convention and can be overridden with ``SBGD_HOME`` or the
``--data-dir`` flag. Godot computes the same default in
``scripts/core/paths.gd`` and always passes ``--data-dir`` explicitly.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_DIR_WINDOWS_MAC = "SecondBrainGD"
APP_DIR_LINUX = "second-brain-gd"

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = REPO_ROOT / "engine"
LOCK_FILE = ENGINE_DIR / "requirements.lock"
MIGRATIONS_DIR = ENGINE_DIR / "database" / "migrations"


def default_data_dir() -> Path:
    override = os.environ.get("SBGD_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_DIR_WINDOWS_MAC
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_WINDOWS_MAC
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_DIR_LINUX


@dataclass(frozen=True)
class Layout:
    root: Path

    @property
    def venv(self) -> Path:
        return self.root / ".venv"

    @property
    def venv_python(self) -> Path:
        if sys.platform == "win32":
            return self.venv / "Scripts" / "python.exe"
        return self.venv / "bin" / "python"

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def database(self) -> Path:
        return self.data / "second_brain.sqlite3"

    @property
    def notes(self) -> Path:
        # Reserved for Loop 1+ (knowledge items). Created empty now.
        return self.data / "notes"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def runtime(self) -> Path:
        """Short-lived files: events stream, API token, server pid. Private."""
        return self.root / "runtime"

    @property
    def config_file(self) -> Path:
        return self.root / "config.json"

    @property
    def state_file(self) -> Path:
        return self.root / "install_state.json"

    @property
    def server_file(self) -> Path:
        return self.runtime / "server.json"

    @property
    def token_file(self) -> Path:
        return self.runtime / "api_token"

    @property
    def lock_file(self) -> Path:
        return self.runtime / "bootstrap.lock"

    def directories(self) -> list[Path]:
        return [self.root, self.data, self.notes, self.logs, self.runtime]
