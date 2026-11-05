"""Builds the How-to sample files (tools/howto/files/), pure Python, no dependency.

- heat-pump-quote.pdf: a normal PDF with a text layer.
- insurance-renewal-scan.pdf: two pages that are only pictures (a "scan"), drawn by render_page.ps1.
Run: python3 tools/howto/make_files.py  (after render_page.ps1 made files/scan-p1.bmp and scan-p2.bmp)
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

FILES = Path(__file__).resolve().parent / "files"

QUOTE = """Northwind Climate Inc.
Quote Q-2026-311 · November 3, 2026

Cold-climate heat pump, installed
Ducted unit, 3 tons, HSPF2 9.5, works down to -30 °C
Equipment                                              $9,850
Installation and commissioning                         $3,200
Electrical: new 40 A breaker and wiring                $  690
Removal of the old oil furnace                         $  950
Total before taxes                                    $14,690

Rebates: the provincial rebate covers up to $5,000 if the old oil
heating is removed. We file the paperwork for you.
Lead time: 3 weeks. Valid until December 15, 2026.""".splitlines()


def _pdf(objects: list[bytes]) -> bytes:
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for o in offsets:
        out += f"{o:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def _stream(data: bytes, extra: str = "") -> bytes:
    return f"<< /Length {len(data)} {extra}>>\nstream\n".encode() + data + b"\nendstream"


def text_pdf(lines: list[str]) -> bytes:
    ops = ["BT", "/F2 20 Tf", "72 760 Td", f"({_esc(lines[0])}) Tj", "/F1 11 Tf", "0 -22 Td"]
    for ln in lines[1:]:
        ops += ["0 -17 Td", f"({_esc(ln)}) Tj"]
    ops.append("ET")
    content = "\n".join(ops).encode("cp1252")
    return _pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
        _stream(content),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ])


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _bmp_rgb(path: Path) -> tuple[int, int, bytes]:
    b = path.read_bytes()
    off, = struct.unpack_from("<I", b, 10)
    w, h = struct.unpack_from("<ii", b, 18)
    row = (w * 3 + 3) & ~3
    rows = []
    for y in range(abs(h)):
        src = b[off + (abs(h) - 1 - y) * row: off + (abs(h) - 1 - y) * row + w * 3] if h > 0 else b[off + y * row: off + y * row + w * 3]
        px = bytearray(src)
        px[0::3], px[2::3] = src[2::3], src[0::3]  # BGR -> RGB
        rows.append(bytes(px))
    return w, abs(h), b"".join(rows)


def image_pdf(bmps: list[Path]) -> bytes:
    n = len(bmps)
    kids = " ".join(f"{3 + i * 3} 0 R" for i in range(n))
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode()]
    for i, p in enumerate(bmps):
        w, h, rgb = _bmp_rgb(p)
        page, content, img = 3 + i * 3, 4 + i * 3, 5 + i * 3
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content} 0 R "
                    f"/Resources << /XObject << /Im{i} {img} 0 R >> >> >>".encode())
        objs.append(_stream(f"q 612 0 0 792 0 0 cm /Im{i} Do Q".encode()))
        objs.append(_stream(zlib.compress(rgb, 9), f"/Type /XObject /Subtype /Image /Width {w} /Height {h} "
                                                   "/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode "))
    return _pdf(objs)


if __name__ == "__main__":
    (FILES / "heat-pump-quote.pdf").write_bytes(text_pdf(QUOTE))
    (FILES / "insurance-renewal-scan.pdf").write_bytes(image_pdf([FILES / "scan-p1.bmp", FILES / "scan-p2.bmp"]))
    for f in sorted(FILES.glob("*.pdf")):
        print(f.name, f.stat().st_size)
