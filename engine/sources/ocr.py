"""Local OCR: the text of scanned PDFs and images, read on this machine.

Windows uses the OCR engine built into Windows 10/11 (Windows.Media.Ocr, through PowerShell: nothing to install,
nothing leaves the machine). Linux uses Tesseract when it is installed (`tesseract` on PATH, with `fra`).
SBGD_OCR=fake (tests) returns a fixed text; SBGD_OCR=off disables local OCR; SBGD_OCR=recorded (the How-to guides)
replays the pages a real Windows OCR read, from the JSON file SBGD_OCR_PAGES.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable

RENDER_WIDTH = 2400   # pages are enlarged before reading: small print is read far better
TIMEOUT_S = 300


class OcrError(RuntimeError):
    pass


def engine_name() -> str | None:
    """Which local OCR engine this machine has ("windows", "tesseract", "fake") or None."""
    mode = os.environ.get("SBGD_OCR", "").strip().lower()
    if mode == "off":
        return None
    if mode in ("fake", "recorded"):
        return mode
    if sys.platform == "win32" and shutil.which("powershell"):
        return "windows"
    if shutil.which("tesseract"):
        return "tesseract"
    return None


def _no_window() -> dict:
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if sys.platform == "win32" else {}


Progress = Callable[[str, int, int], None]   # (stage, done, total): "render" or "ocr", pages done so far


def read_images(paths: list[Path], lang: str = "", on_page: Progress | None = None) -> list[str]:
    """Text of each image, in order. on_page("ocr", k, n) after each one."""
    engine = engine_name()
    if engine is None:
        raise OcrError("no local OCR on this machine")
    n = len(paths)
    tick = on_page or (lambda _s, _d, _t: None)
    if engine == "fake":
        out = []
        for i in range(n):
            out.append(f"Texte lu par OCR local (image {i + 1}) : Guide du compost, alterner matières vertes et brunes.")
            tick("ocr", i + 1, n)
        return out
    if engine == "recorded":
        import time

        pages = json.loads(Path(os.environ["SBGD_OCR_PAGES"]).read_text(encoding="utf-8"))["pages"]
        out = []
        for i in range(n):
            time.sleep(0.8)  # a real page takes about a second: the progress line has time to show
            out.append(pages[i] if i < len(pages) else "")
            tick("ocr", i + 1, n)
        return out
    if engine == "windows":
        return _windows(paths, lang, tick)
    langs = "fra+eng"
    try:
        have = subprocess.run(["tesseract", "--list-langs"], capture_output=True, timeout=30).stdout.decode("utf-8", "replace")
        if "fra" not in have.split():
            langs = "eng"
    except (OSError, subprocess.TimeoutExpired):
        langs = "eng"
    texts = []
    for i, p in enumerate(paths):
        try:
            out = subprocess.run(["tesseract", str(p), "stdout", "-l", langs], capture_output=True, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired as exc:
            raise OcrError("Tesseract took too long") from exc
        if out.returncode != 0:
            raise OcrError("Tesseract failed: " + out.stderr.decode("utf-8", "replace").strip()[:200])
        texts.append(out.stdout.decode("utf-8", "replace").strip())
        tick("ocr", i + 1, n)
    return texts


def _windows(paths: list[Path], lang: str, tick: Progress) -> list[str]:
    """Windows.Media.Ocr through PowerShell; the script prints one JSON line per page as soon as it is read."""
    script = Path(__file__).with_name("ocr_windows.ps1")
    n = len(paths)
    texts: dict[int, str] = {}
    with tempfile.TemporaryDirectory(prefix="sbgd-ocr-") as tmp:
        listing = Path(tmp) / "pages.txt"
        listing.write_text("\n".join(str(p) for p in paths), encoding="utf-8")
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script),
               "-List", str(listing)] + (["-Lang", lang] if lang else [])
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_no_window())
        expired: list[bool] = []
        timer = threading.Timer(TIMEOUT_S, lambda: (expired.append(True), proc.kill()))
        timer.start()
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.decode("utf-8-sig", "replace").strip()
                if not line.startswith("{"):
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if "i" in item:
                    texts[int(item["i"])] = str(item.get("text") or "")
                    tick("ocr", len(texts), n)
            err = proc.stderr.read().decode("utf-8", "replace").strip() if proc.stderr else ""
            code = proc.wait()
        finally:
            timer.cancel()
    if expired:
        raise OcrError("Windows OCR took too long")
    if code != 0:
        raise OcrError("Windows OCR failed: " + (err.splitlines()[0][:200] if err else f"exit {code}"))
    if len(texts) < n:
        raise OcrError(f"Windows OCR read {len(texts)} of {n} pages")
    return [texts[i] for i in range(1, n + 1)]


def read_pdf(path: Path, pages: int, max_pages: int = 60, on_progress: Progress | None = None) -> str:
    """Every page of a PDF made of images, rendered large and read locally."""
    from engine.sources import render

    tick = on_progress or (lambda _s, _d, _t: None)
    n = min(pages, max_pages)
    with tempfile.TemporaryDirectory(prefix="sbgd-ocr-") as tmp:
        files = []
        for page in range(1, n + 1):
            f = Path(tmp) / f"p{page}.png"
            f.write_bytes(render.render_page(path, page, RENDER_WIDTH, Path(tmp) / "cache"))
            files.append(f)
            tick("render", page, n)
        texts = read_images(files, on_page=tick)
    parts = [t.strip() for t in texts if t and t.strip()]
    if pages > max_pages:
        parts.append(f"[Pages {max_pages + 1} à {pages} non lues.]")
    return "\n\n".join(parts)
