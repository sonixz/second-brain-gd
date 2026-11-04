"""Local OCR: the text of scanned PDFs and images, read on this machine.

Windows uses the OCR engine built into Windows 10/11 (Windows.Media.Ocr, through PowerShell: nothing to install,
nothing leaves the machine). Linux uses Tesseract when it is installed (`tesseract` on PATH, with `fra`).
SBGD_OCR=fake (tests) returns a fixed text; SBGD_OCR=off disables local OCR.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RENDER_WIDTH = 2400   # pages are enlarged before reading: small print is read far better
TIMEOUT_S = 300


class OcrError(RuntimeError):
    pass


def engine_name() -> str | None:
    """Which local OCR engine this machine has ("windows", "tesseract", "fake") or None."""
    mode = os.environ.get("SBGD_OCR", "").strip().lower()
    if mode == "off":
        return None
    if mode == "fake":
        return "fake"
    if sys.platform == "win32" and shutil.which("powershell"):
        return "windows"
    if shutil.which("tesseract"):
        return "tesseract"
    return None


def _no_window() -> dict:
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if sys.platform == "win32" else {}


def read_images(paths: list[Path], lang: str = "") -> list[str]:
    """Text of each image, in order."""
    engine = engine_name()
    if engine is None:
        raise OcrError("no local OCR on this machine")
    if engine == "fake":
        return [f"Texte lu par OCR local (image {i + 1}) : Guide du compost, alterner matières vertes et brunes."
                for i in range(len(paths))]
    if engine == "windows":
        script = Path(__file__).with_name("ocr_windows.ps1")
        with tempfile.TemporaryDirectory(prefix="sbgd-ocr-") as tmp:
            listing = Path(tmp) / "pages.txt"
            listing.write_text("\n".join(str(p) for p in paths), encoding="utf-8")
            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script),
                   "-List", str(listing)] + (["-Lang", lang] if lang else [])
            try:
                out = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT_S, **_no_window())
            except subprocess.TimeoutExpired as exc:
                raise OcrError("Windows OCR took too long") from exc
        if out.returncode != 0:
            msg = out.stderr.decode("utf-8", "replace").strip().splitlines()
            raise OcrError("Windows OCR failed: " + (msg[0][:200] if msg else f"exit {out.returncode}"))
        try:
            data = json.loads(out.stdout.decode("utf-8-sig"))
        except ValueError as exc:
            raise OcrError("Windows OCR returned no result") from exc
        pages = data.get("pages") or []
        return [pages] if isinstance(pages, str) else [str(p) for p in pages]
    langs = "fra+eng"
    try:
        have = subprocess.run(["tesseract", "--list-langs"], capture_output=True, timeout=30).stdout.decode("utf-8", "replace")
        if "fra" not in have.split():
            langs = "eng"
    except (OSError, subprocess.TimeoutExpired):
        langs = "eng"
    texts = []
    for p in paths:
        try:
            out = subprocess.run(["tesseract", str(p), "stdout", "-l", langs], capture_output=True, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired as exc:
            raise OcrError("Tesseract took too long") from exc
        if out.returncode != 0:
            raise OcrError("Tesseract failed: " + out.stderr.decode("utf-8", "replace").strip()[:200])
        texts.append(out.stdout.decode("utf-8", "replace").strip())
    return texts


def read_pdf(path: Path, pages: int, max_pages: int = 60) -> str:
    """Every page of a PDF made of images, rendered large and read locally."""
    from engine.sources import render

    with tempfile.TemporaryDirectory(prefix="sbgd-ocr-") as tmp:
        files = []
        for page in range(1, min(pages, max_pages) + 1):
            f = Path(tmp) / f"p{page}.png"
            f.write_bytes(render.render_page(path, page, RENDER_WIDTH, Path(tmp) / "cache"))
            files.append(f)
        texts = read_images(files)
    parts = [t.strip() for t in texts if t and t.strip()]
    if pages > max_pages:
        parts.append(f"[Pages {max_pages + 1} à {pages} non lues.]")
    return "\n\n".join(parts)
