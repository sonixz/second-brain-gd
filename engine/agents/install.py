"""Downloads the pinned Codex app-server (stdlib only, used by the bootstrap).

Visible, verified and resumable: the file is fetched from the official release
URL in manifest.json into `<data>/agents/downloads/*.part` (HTTP Range resumes an
interrupted download), its SHA-256 must match the pinned digest, then the whole
package (app-server plus its companions: code-mode host, exec server, ripgrep,
sandbox helpers) is extracted to `<data>/agents/codex/<version>/`. The app-server
finds those companions next to itself; without them every tool call fails.
Only plain files and folders with relative paths are extracted. No admin rights,
nothing outside the user data folder, nothing run during install.

Test hook: SBGD_AGENTS_MANIFEST points to another manifest (a local fixture).
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Any, Callable

from engine.paths import Layout

MANIFEST = Path(__file__).with_name("manifest.json")
CHUNK = 1 << 20


class InstallError(RuntimeError):
    pass


def platform_key() -> str:
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64"}.get(machine, machine)
    osname = "windows" if sys.platform == "win32" else ("macos" if sys.platform == "darwin" else "linux")
    return f"{osname}-{arch}"


def load_manifest() -> tuple[dict[str, Any], Path]:
    path = Path(os.environ.get("SBGD_AGENTS_MANIFEST") or MANIFEST)
    return json.loads(path.read_text(encoding="utf-8")), path


def agents_dir(layout: Layout) -> Path:
    return layout.root / "agents"


def installed_info(layout: Layout) -> dict[str, Any] | None:
    """The installed binary when it matches the pinned version and still exists, else None."""
    try:
        info = json.loads((agents_dir(layout) / "installed.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    manifest, _ = load_manifest()
    if info.get("version") != manifest.get("version") or not Path(info.get("binary", "")).is_file():
        return None
    return info


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _resolve_url(url: str, manifest_path: Path) -> str:
    if "://" in url:
        return url
    return (manifest_path.parent / url).resolve().as_uri()  # fixture manifests use relative paths


def download(url: str, dest: Path, expected_size: int | None,
             progress: Callable[[int, int | None], None] | None = None, timeout: float = 60.0) -> None:
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={"User-Agent": "SecondBrainGD-setup"})
    if have and url.startswith("http"):
        req.add_header("Range", f"bytes={have}-")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resumed = getattr(resp, "status", 200) == 206
        mode = "ab" if resumed else "wb"
        done = have if resumed else 0
        total = expected_size
        with part.open(mode) as fh:
            while True:
                block = resp.read(CHUNK)
                if not block:
                    break
                fh.write(block)
                done += len(block)
                if progress is not None:
                    progress(done, total)
    part.replace(dest)


def _safe_name(name: str) -> str | None:
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or ".." in parts or ":" in parts[0] or name.startswith(("/", "\\")):
        return None
    return "/".join(parts)


def _extract_package(archive: Path, target: Path) -> None:
    """Extracts into a fresh folder next to target, then swaps it in, so a half-unpacked package never counts."""
    staging = target.with_name(target.name + ".unpacking")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar:
                name = _safe_name(member.name)
                if name is None or not (member.isfile() or member.isdir()):
                    raise InstallError(f"Unexpected archive content: {member.name!r}.")
                dest = staging / name
                if member.isdir():
                    dest.mkdir(parents=True, exist_ok=True)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                src = tar.extractfile(member)
                assert src is not None
                with dest.open("wb") as out:
                    for block in iter(lambda: src.read(CHUNK), b""):
                        out.write(block)
                if sys.platform != "win32" and member.mode & 0o111:
                    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        shutil.rmtree(target, ignore_errors=True)
        staging.replace(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def install(layout: Layout, progress: Callable[[str, float, str], None] | None = None) -> dict[str, Any]:
    """Idempotent. progress(stage, fraction, message) is called along the way."""
    say = progress or (lambda *_: None)
    manifest, manifest_path = load_manifest()
    key = platform_key()
    spec = (manifest.get("platforms") or {}).get(key)
    if spec is None:
        raise InstallError(f"No agent build for this platform ({key}).")
    current = installed_info(layout)
    if current is not None:
        say("verify", 1.0, f"Agents ready ({manifest['version']}).")
        return {**current, "already": True}
    root = agents_dir(layout)
    downloads = root / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / Path(spec["url"]).name
    if archive.exists() and _sha256(archive) != spec["sha256"]:
        archive.unlink()  # a corrupted or foreign file: start over
    if not archive.exists():
        size = spec.get("size")
        mb = f"{size / 1e6:.0f} MB" if size else "unknown size"
        say("download", 0.0, f"Downloading {manifest['name']} {manifest['version']} ({mb})…")
        last = [-1]

        def tick(done: int, total: int | None) -> None:
            if total:
                pct = int(done * 100 / total)
                if pct != last[0] and pct % 2 == 0:
                    last[0] = pct
                    say("download", min(0.9, 0.9 * done / total), f"Downloading agents… {done / 1e6:.0f} / {total / 1e6:.0f} MB")

        download(_resolve_url(spec["url"], manifest_path), archive, size, tick)
    say("verify", 0.92, "Checking the SHA-256 fingerprint…")
    digest = _sha256(archive)
    if digest != spec["sha256"]:
        archive.unlink(missing_ok=True)
        raise InstallError("The downloaded file does not match the pinned fingerprint; it was deleted.")
    say("verify", 0.95, "Unpacking the agent package…")
    target = root / "codex" / manifest["version"]
    _extract_package(archive, target)
    binary = target / spec["binary"]
    if not binary.is_file():
        shutil.rmtree(target, ignore_errors=True)
        raise InstallError("The agent package does not contain its app-server.")
    info = {"name": manifest["name"], "version": manifest["version"], "platform": key, "binary": str(binary),
            "sha256": digest}
    (root / "installed.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    archive.unlink(missing_ok=True)  # the unpacked package is what we keep
    for old in (root / "codex").iterdir():  # earlier pinned versions are dead weight (about 0.5 GB each)
        if old.is_dir() and old.name != manifest["version"]:
            shutil.rmtree(old, ignore_errors=True)
    say("verify", 1.0, f"Agents ready ({manifest['version']}).")
    return {**info, "already": False}
