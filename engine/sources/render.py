"""Document pages as images (Loop 12). PDF pages are rendered with PDFium (pypdfium2) at a
width chosen by the viewer, encoded as PNG with the stdlib, and cached on disk."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

WIDTHS = (320, 640, 1024, 1600, 2400)
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
               ".gif": "image/gif"}


class RenderError(RuntimeError):
    pass


def bucket(width: int) -> int:
    """The smallest cached width that is at least the asked one (so zooming in gets sharper pages)."""
    for w in WIDTHS:
        if width <= w:
            return w
    return WIDTHS[-1]


def png(rgba: bytes, width: int, height: int) -> bytes:
    stride = width * 4
    raw = b"".join(b"\x00" + rgba[y * stride:(y + 1) * stride] for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def page_count(path: Path) -> int:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RenderError("PDF rendering is not installed (pypdfium2)") from exc
    try:
        doc = pdfium.PdfDocument(str(path))
        try:
            return len(doc)
        finally:
            doc.close()
    except Exception as exc:
        raise RenderError(f"cannot open this PDF: {exc.__class__.__name__}") from exc


def render_page(path: Path, page: int, width: int, cache: Path) -> bytes:
    """PNG of one page (1-based) at about `width` pixels wide, from the cache when possible."""
    w = bucket(width)
    target = cache / f"{path.stem}-p{page}-w{w}.png"
    if target.exists():
        return target.read_bytes()
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RenderError("PDF rendering is not installed (pypdfium2)") from exc
    doc = pdfium.PdfDocument(str(path))
    try:
        if not 1 <= page <= len(doc):
            raise RenderError(f"page {page} does not exist (1-{len(doc)})")
        pg = doc[page - 1]
        scale = w / max(1.0, pg.get_width())
        bitmap = pg.render(scale=scale, rev_byteorder=True, prefer_bgrx=False, may_draw_forms=True)
        bw, bh, stride, n = bitmap.width, bitmap.height, bitmap.stride, bitmap.n_channels
        buf = bytes(bitmap.buffer)
        rows = []
        for y in range(bh):
            row = buf[y * stride:y * stride + bw * n]
            if n == 3:  # RGB -> RGBA
                row = b"".join(row[i:i + 3] + b"\xff" for i in range(0, len(row), 3))
            rows.append(row)
        data = png(b"".join(rows), bw, bh)
    finally:
        doc.close()
    cache.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(target)
    return data
