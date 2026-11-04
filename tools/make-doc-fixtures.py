"""Writes tests/fixtures/docs/sample.pdf (2 pages of real text) and sample.png (a small image), deterministically."""
import struct
import sys
import zlib
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "docs"
D.mkdir(parents=True, exist_ok=True)

pages = [
    ["Guide du compost", "Le compost transforme les restes de cuisine en terreau.", "Il faut alterner matieres vertes et brunes."],
    ["Page deux", "Retourner le tas toutes les deux semaines.", "Le compost est pret en trois a six mois."],
]
objs = []
def add(b: bytes) -> int:
    objs.append(b)
    return len(objs)
font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
page_ids = []
pages_id = len(objs) + 1 + 2 * len(pages)  # reserved below
for lines in pages:
    text = "BT /F1 18 Tf 72 760 Td " + " ".join(f"({l}) Tj 0 -28 Td" for l in lines) + " ET"
    content = add(b"<< /Length %d >>\nstream\n" % len(text) + text.encode("latin-1") + b"\nendstream")
    page_ids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                        % (pages_id, font, content)))
assert pages_id == len(objs) + 1
add(b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % i for i in page_ids) + b"] /Count %d >>" % len(page_ids))
catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
out = bytearray(b"%PDF-1.4\n")
offsets = []
for i, body in enumerate(objs, 1):
    offsets.append(len(out))
    out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
xref = len(out)
out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
for off in offsets:
    out += b"%010d 00000 n \n" % off
out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, catalog, xref)
(D / "sample.pdf").write_bytes(bytes(out))

w, h = 64, 48
raw = b"".join(b"\x00" + b"".join(bytes((x * 4 % 256, y * 5 % 256, 160, 255)) for x in range(w)) for y in range(h))
def chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
(D / "sample.png").write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                               + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
print("ok", len(out))
