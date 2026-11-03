"""Per-user secrets.

Order of lookup:
1. the OS credential store via `keyring` (Windows Credential Manager, macOS
   Keychain, Linux Secret Service);
2. a private file in the data folder when no credential store exists
   (e.g. WSL/headless Linux), readable by the user only;
3. the OPENAI_API_KEY environment variable (developers: `dotenvx run`).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from engine.paths import Layout

SERVICE = os.environ.get("SBGD_KEYRING_SERVICE", "SecondBrainGD")
ENV_VARS = {"openai": "OPENAI_API_KEY"}


@dataclass
class SecretInfo:
    configured: bool
    source: str          # "keyring" | "file" | "env" | "none"
    backend: str
    hint: str            # last 4 characters only, e.g. "••••a1b2"


def _keyring():
    """The usable OS credential store, or (None, "none")."""
    try:
        import keyring

        backend = keyring.get_keyring()
        # The "fail" backend (no store available) and empty chainers have priority < 1.
        if getattr(backend, "priority", 0) < 1:
            return None, "none"
        return keyring, type(backend).__module__.split(".")[-1] + "." + type(backend).__name__
    except Exception:
        return None, "none"


def _file(layout: Layout, provider: str) -> Path:
    return layout.root / "secrets" / f"{provider}.key"


def _hint(value: str) -> str:
    return "••••" + value[-4:] if len(value) >= 8 else "••••"


def get(layout: Layout, provider: str) -> tuple[str | None, str]:
    kr, _ = _keyring()
    if kr is not None:
        try:
            value = kr.get_password(SERVICE, provider)
            if value:
                return value, "keyring"
        except Exception:
            pass
    path = _file(layout, provider)
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value, "file"
    env = os.environ.get(ENV_VARS.get(provider, ""), "").strip()
    if env:
        return env, "env"
    return None, "none"


def info(layout: Layout, provider: str) -> SecretInfo:
    value, source = get(layout, provider)
    _, backend = _keyring()
    return SecretInfo(configured=value is not None, source=source,
                      backend=backend if backend != "none" else "private file",
                      hint=_hint(value) if value else "")


def store(layout: Layout, provider: str, value: str) -> str:
    """Saves the secret; returns where it went ("keyring" or "file")."""
    value = value.strip()
    if not value:
        raise ValueError("empty secret")
    kr, _ = _keyring()
    if kr is not None:
        try:
            kr.set_password(SERVICE, provider, value)
            _file(layout, provider).unlink(missing_ok=True)
            return "keyring"
        except Exception:
            pass
    path = _file(layout, provider)
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(path.parent, 0o700)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(value)
    os.replace(tmp, path)
    return "file"


def delete(layout: Layout, provider: str) -> None:
    kr, _ = _keyring()
    if kr is not None:
        try:
            kr.delete_password(SERVICE, provider)
        except Exception:
            pass
    _file(layout, provider).unlink(missing_ok=True)
