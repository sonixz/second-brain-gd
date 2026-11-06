"""Builds the Python runtime shipped inside Second Brain GD (Loop 28), and optionally the whole app folder.

  python3 tools/package/build.py runtime --target windows|linux     dist/runtime-<target>/python
  python3 tools/package/build.py app --target windows|linux         dist/SecondBrainGD-<target>/ + .zip + SHA256SUMS

The runtime is a python-build-standalone CPython pinned in tools/package/runtime.json (file and SHA-256: the build
stops on any mismatch), with the locked dependencies installed into its own site-packages (pip --require-hashes,
wheels only, for the target platform: a Windows runtime can be built on Linux). Parts never used are removed
(tests, Tk, IDLE). A marker, python/sbgd-runtime.json, records what was built; the installer recognises it and
skips the virtual environment (engine/installer/steps.py).

Downloads happen here, at build time, from the pinned addresses: the app itself never downloads an interpreter.
Nothing is published: the output stays in dist/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINS = json.loads((Path(__file__).with_name("runtime.json")).read_text(encoding="utf-8"))
LOCK = ROOT / "engine" / "requirements.lock"
CACHE = Path(os.environ.get("SBGD_PACKAGE_CACHE", Path.home() / ".cache" / "sbgd-package"))
DIST = ROOT / "dist"
BASE_URL = "https://github.com/astral-sh/python-build-standalone/releases/download"
# Never used by the engine: removed from the runtime (about a third of its size).
DROP = ["test", "idlelib", "tkinter", "turtledemo", "turtle.py", "ensurepip", "lib2to3", "pydoc_data", "venv"]
DROP_TOP = ["tcl", "share", "include"]
# What the app folder holds besides the Godot export (the engine is plain Python source, readable by anyone).
APP_PARTS = ["engine", "browser-extension", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(target: str) -> Path:
    pin = PINS["targets"][target]
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / pin["file"]
    if not path.exists() or sha256(path) != pin["sha256"]:
        url = f"{BASE_URL}/{PINS['release']}/{pin['file'].replace('+', '%2B')}"
        print(f"downloading {url}")
        tmp = path.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=120) as resp, tmp.open("wb") as out:
            shutil.copyfileobj(resp, out)
        tmp.replace(path)
    got = sha256(path)
    if got != pin["sha256"]:
        path.unlink(missing_ok=True)
        raise SystemExit(f"checksum mismatch for {pin['file']}: {got} (expected {pin['sha256']})")
    return path


def _extract(archive: Path, dest: Path) -> None:
    """tarfile's "data" filter refuses absolute paths, ".." and links leaving the folder."""
    with tarfile.open(archive) as tar:
        tar.extractall(dest, filter="data")


def strip(py: Path, target: str) -> None:
    lib = py / "Lib" if target == "windows" else py / "lib" / f"python{PINS['python']}"
    for name in DROP:
        p = lib / name
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    for name in DROP_TOP:
        shutil.rmtree(py / name, ignore_errors=True)
    if target == "linux":
        for pattern in ("tcl*", "tk*", "itcl*", "thread*", "libtcl*", "libtk*", "pkgconfig"):
            for p in (py / "lib").glob(pattern):
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() and not p.is_symlink() else p.unlink()
        # one real interpreter and one real libpython: the other names are links, which would become copies
        keep = py / "python3.keep"
        shutil.copy2((py / "bin" / "python3").resolve(), keep)
        for p in list((py / "bin").iterdir()):
            p.unlink()
        keep.replace(py / "bin" / "python3")
        for p in (py / "lib").glob("libpython*.so*"):
            if p.is_symlink():
                p.unlink()
    else:
        for p in py.glob("tcl*"):
            shutil.rmtree(p, ignore_errors=True)
        for p in (py / "DLLs").glob("t[ck]*.dll"):
            p.unlink()
        (py / "DLLs" / "_tkinter.pyd").unlink(missing_ok=True)
    for p in py.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)


def install_dependencies(py: Path, target: str) -> None:
    pin = PINS["targets"][target]
    site = py / pin["site_packages"]
    cmd = [sys.executable, "-m", "pip", "install", "--no-input", "--disable-pip-version-check", "--no-compile",
           "--require-hashes", "--only-binary=:all:", "--target", str(site), "--python-version", PINS["python"],
           "--implementation", "cp", "--abi", "cp" + PINS["python"].replace(".", ""), "--abi", "abi3", "--abi", "none"]
    for plat in pin["pip_platforms"]:
        cmd += ["--platform", plat]
    cmd += ["-r", str(LOCK)]
    subprocess.run(cmd, check=True)
    for p in site.glob("*.dist-info"):  # keep the licences, drop pip's install records
        (p / "RECORD").unlink(missing_ok=True)


def runtime(target: str, out: Path | None = None) -> Path:
    out = out or DIST / f"runtime-{target}"
    work = CACHE / f"work-{target}"  # a Linux folder: the archive's symbolic links extract cleanly there
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    _extract(fetch(target), work)
    strip(work / "python", target)
    for p in (work / "python" / PINS["targets"][target]["site_packages"]).glob("pip*"):  # not needed at run time
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    install_dependencies(work / "python", target)
    out.mkdir(parents=True, exist_ok=True)
    py = out / "python"
    if py.exists():
        shutil.rmtree(py)
    shutil.copytree(work / "python", py, symlinks=False)  # links resolved: the folder works on any disk
    shutil.rmtree(work, ignore_errors=True)
    marker = {"format": "sbgd-runtime", "version": 1, "target": target, "python": PINS["python"],
              "release": PINS["release"], "file": PINS["targets"][target]["file"],
              "lock_sha256": sha256(LOCK), "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    (py / "sbgd-runtime.json").write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    size = sum(f.stat().st_size for f in py.rglob("*") if f.is_file())
    print(f"runtime {target}: {py} ({size / 1e6:.1f} MB)")
    return py


def godot_export(target: str, dest: Path) -> None:
    godot = os.environ.get("GODOT", "godot")
    preset = {"windows": "Windows Desktop", "linux": "Linux"}[target]
    exe = dest / ("SecondBrainGD.exe" if target == "windows" else "SecondBrainGD.x86_64")
    subprocess.run([godot, "--headless", "--path", str(ROOT), "--import"], capture_output=True)
    res = subprocess.run([godot, "--headless", "--path", str(ROOT), "--export-release", preset, str(exe)],
                         capture_output=True, text=True)
    if res.returncode != 0 or not exe.exists():
        raise SystemExit(f"Godot export failed ({preset}):\n{res.stdout[-2000:]}\n{res.stderr[-2000:]}")


def app(target: str) -> Path:
    dest = DIST / f"SecondBrainGD-{target}"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    godot_export(target, dest)
    licenses = dest / "LICENSES"  # Godot's licence and its components must travel with the exported app
    licenses.mkdir()
    subprocess.run([os.environ.get("GODOT", "godot"), "--headless", "--path", str(ROOT), "--script",
                    "res://tools/package/licenses.gd", "--", str(licenses / "godot.txt")], check=True, capture_output=True)
    if not (licenses / "godot.txt").is_file() or (licenses / "godot.txt").stat().st_size < 1000:
        raise SystemExit("Godot's licence notices could not be written")
    for part in APP_PARTS:
        src = ROOT / part
        if src.is_dir():
            shutil.copytree(src, dest / part, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif src.exists():
            shutil.copy2(src, dest / part)
    runtime(target, out=dest)
    archive = DIST / f"SecondBrainGD-{target}.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(dest.rglob("*")):
            if f.is_file():
                info = zipfile.ZipInfo.from_file(f, f.relative_to(DIST).as_posix())
                if os.access(f, os.X_OK) and target == "linux":
                    info.external_attr = 0o755 << 16
                with f.open("rb") as fh:
                    z.writestr(info, fh.read(), zipfile.ZIP_DEFLATED)
    sums = DIST / "SHA256SUMS"
    lines = [l for l in (sums.read_text().splitlines() if sums.exists() else []) if not l.endswith(archive.name)]
    lines.append(f"{sha256(archive)}  {archive.name}")
    sums.write_text("\n".join(sorted(lines)) + "\n")
    print(f"app {target}: {archive} ({archive.stat().st_size / 1e6:.1f} MB)")
    return dest


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["runtime", "app"])
    ap.add_argument("--target", choices=sorted(PINS["targets"]), required=True)
    a = ap.parse_args()
    runtime(a.target) if a.what == "runtime" else app(a.target)
