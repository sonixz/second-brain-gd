"""Per-user secrets (API keys).

Order of lookup:
1. Windows: the Credential Manager, called directly (advapi32 CredReadW/CredWriteW/CredDeleteW, no package);
2. a private file in the data folder elsewhere (Linux, WSL), readable by the user only (0600 in a 0700 folder);
3. the OPENAI_API_KEY (or OPENAI_ADMIN_KEY) environment variable (developers: `dotenvx run`).

Loop 27 replaced the `keyring` package (and the nine packages it pulled, `cryptography` among them) with this file.
Credentials are written the way `keyring` wrote them on Windows (a generic credential named
"<provider>@<service>", user name <provider>, the value in UTF-16), and keyring's other naming ("<service>" with the
user name <provider>) is still read, so a key saved before Loop 27 is found as it is: nobody re-enters it.
The service name is SBGD_KEYRING_SERVICE (tests and capture tools use their own, never the user's).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from engine.paths import Layout

SERVICE = os.environ.get("SBGD_KEYRING_SERVICE", "SecondBrainGD")
ENV_VARS = {"openai": "OPENAI_API_KEY", "openai_admin": "OPENAI_ADMIN_KEY"}


@dataclass
class SecretInfo:
    configured: bool
    source: str          # "keyring" (the OS store) | "file" | "env" | "none"
    backend: str
    hint: str            # last 4 characters only, e.g. "••••a1b2"


# ---------------------------------------------------------------- Windows Credential Manager
class _WinCred:
    """The few calls of advapi32 we need. Values are stored as UTF-16, like `keyring` did."""
    name = "Windows Credential Manager"
    GENERIC = 1
    # keyring's choice too: with another persistence Windows keeps a second credential under the same name, and
    # deleting one brings the other back (measured on Windows 11, 2026-11-05)
    PERSIST_ENTERPRISE = 3
    NOT_FOUND = 1168

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                        ("Comment", wintypes.LPWSTR), ("LastWritten", FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
                        ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                        ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]

        self.ct, self.CREDENTIAL = ctypes, CREDENTIAL
        api = ctypes.WinDLL("advapi32", use_last_error=True)
        self.read_fn = api.CredReadW
        self.read_fn.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
        self.read_fn.restype = wintypes.BOOL
        self.write_fn = api.CredWriteW
        self.write_fn.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
        self.write_fn.restype = wintypes.BOOL
        self.delete_fn = api.CredDeleteW
        self.delete_fn.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self.delete_fn.restype = wintypes.BOOL
        self.free = api.CredFree
        self.free.argtypes = [ctypes.c_void_p]

    def _read(self, target: str) -> tuple[str, str] | None:
        """(user name, value) of a generic credential, None when there is none."""
        ct = self.ct
        p = ct.POINTER(self.CREDENTIAL)()
        if not self.read_fn(target, self.GENERIC, 0, ct.byref(p)):
            if ct.get_last_error() == self.NOT_FOUND:
                return None
            raise OSError(ct.get_last_error(), "CredReadW failed")
        try:
            c = p.contents
            blob = ct.string_at(c.CredentialBlob, c.CredentialBlobSize)
            return (c.UserName or ""), blob.decode("utf-16-le")
        finally:
            self.free(p)

    def get(self, service: str, user: str) -> str | None:
        found = self._read(f"{user}@{service}")
        if found is None:  # keyring's first naming: the service alone, when it held a single user
            plain = self._read(service)
            found = plain if plain is not None and plain[0] == user else None
        return found[1] if found else None

    def set(self, service: str, user: str, value: str) -> None:
        ct = self.ct
        blob = value.encode("utf-16-le")
        buf = (ct.c_ubyte * len(blob)).from_buffer_copy(blob)
        cred = self.CREDENTIAL()
        cred.Type, cred.Persist = self.GENERIC, self.PERSIST_ENTERPRISE
        cred.TargetName, cred.UserName = f"{user}@{service}", user
        cred.Comment = "Second Brain GD"
        cred.CredentialBlobSize, cred.CredentialBlob = len(blob), ct.cast(buf, ct.POINTER(ct.c_ubyte))
        if not self.write_fn(ct.byref(cred), 0):
            raise OSError(ct.get_last_error(), "CredWriteW failed")

    def delete(self, service: str, user: str) -> None:
        for _ in range(3):  # until nothing is left under that name (an older copy can sit behind)
            if self._read(f"{user}@{service}") is None:
                break
            self.delete_fn(f"{user}@{service}", self.GENERIC, 0)
        for _ in range(3):
            plain = self._read(service)
            if plain is None or plain[0] != user:
                break
            self.delete_fn(service, self.GENERIC, 0)


def _store():
    """The OS credential store (Windows), or None: the private file is used instead."""
    if sys.platform != "win32" or os.environ.get("SBGD_SECRETS_BACKEND") == "file":
        return None
    try:
        return _WinCred()
    except (OSError, AttributeError):
        return None


# ---------------------------------------------------------------- private file and environment
def _file(layout: Layout, provider: str) -> Path:
    return layout.root / "secrets" / f"{provider}.key"


def _hint(value: str) -> str:
    return "••••" + value[-4:] if len(value) >= 8 else "••••"


def get(layout: Layout, provider: str) -> tuple[str | None, str]:
    store_ = _store()
    if store_ is not None:
        try:
            value = store_.get(SERVICE, provider)
            if value:
                return value, "keyring"
        except OSError:
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
    store_ = _store()
    return SecretInfo(configured=value is not None, source=source,
                      backend=store_.name if store_ is not None else "private file",
                      hint=_hint(value) if value else "")


def store(layout: Layout, provider: str, value: str) -> str:
    """Saves the secret; returns where it went ("keyring" for the OS store, or "file")."""
    value = value.strip()
    if not value:
        raise ValueError("empty secret")
    store_ = _store()
    if store_ is not None:
        try:
            store_.set(SERVICE, provider, value)
            _file(layout, provider).unlink(missing_ok=True)
            return "keyring"
        except OSError:
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
    store_ = _store()
    if store_ is not None:
        try:
            store_.delete(SERVICE, provider)
        except OSError:
            pass
    _file(layout, provider).unlink(missing_ok=True)
