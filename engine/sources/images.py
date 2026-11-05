"""Images from web pages (Loop 25): which ones are worth keeping, and what they say.

A page has dozens of pictures; only a few carry information: its main image and its figures (a diagram, a chart,
a table published as a picture, a product photo with a caption). Those are kept as originals, at most MAX_PER_PAGE.
Logos, icons, avatars, ads and tiny pictures never are. The text read in an image on this computer (local OCR)
decides whether the vision model is asked to describe it: a picture with words or numbers in it is worth the call,
a decorative photo is kept with its caption only.
"""
from __future__ import annotations

import os
import re
import struct
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

MAX_PER_PAGE = 5
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MIN_SIDE = 160           # smaller than this: an icon or a thumbnail
MIN_AREA = 200 * 150
KEEP_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}
NOISE = re.compile(r"logo|icon|sprite|avatar|badge|emoji|spinner|loader|pixel|tracking|beacon|/ads?/|advert|banner|"
                   r"gravatar|placeholder|blank\.|spacer|share|social|button|arrow|1x1", re.I)
INFORMATIVE = re.compile(r"diagram|chart|graph|figure|fig\.|table|map|plan|schema|infographic|comparison|curve|"
                         r"schéma|graphique|tableau|carte|courbe|comparatif|données|data", re.I)


# ---------------------------------------------------------------- what a picture is
def sniff(data: bytes) -> str | None:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def size_of(data: bytes) -> tuple[int, int] | None:
    """Width and height from the file's header (PNG, JPEG, GIF, WebP), without decoding it."""
    try:
        kind = sniff(data)
        if kind == "image/png":
            return struct.unpack(">II", data[16:24])
        if kind == "image/gif":
            return struct.unpack("<HH", data[6:10])
        if kind == "image/webp":
            chunk = data[12:16]
            if chunk == b"VP8X":
                return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
            if chunk == b"VP8 ":
                w, h = struct.unpack("<HH", data[26:30])
                return w & 0x3FFF, h & 0x3FFF
            if chunk == b"VP8L":
                b = int.from_bytes(data[21:25], "little")
                return (b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1
            return None
        if kind == "image/jpeg":
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return w, h
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    i += 2
                    continue
                i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    except (struct.error, IndexError):
        return None
    return None


def big_enough(w: int, h: int) -> bool:
    return min(w, h) >= MIN_SIDE and w * h >= MIN_AREA


# ---------------------------------------------------------------- the page's language (descriptions are written in it)
LANG_NAMES = {"en": "English", "fr": "français", "es": "español", "de": "Deutsch", "it": "italiano", "pt": "português"}
_FR = set("le la les des une est et pour dans que qui sur avec pas du au aux ce cette sont".split())
_EN = set("the and for with that this are from was which have has not its into their".split())


def language(lang_attr: str = "", sample: str = "") -> str:
    """The page's language, by name: its <html lang>, else a guess from its words; descriptions are written in it."""
    code = (lang_attr or "").strip().lower()[:2]
    if code in LANG_NAMES:
        return LANG_NAMES[code]
    words = re.findall(r"[a-zà-ÿ']+", (sample or "").lower())[:600]
    fr, en = sum(w in _FR for w in words), sum(w in _EN for w in words)
    return "français" if fr > en else ("English" if en > fr else "la langue de la page")


def html_lang(raw: str) -> str:
    m = re.search(r"<html[^>]*\blang=[\"']?([A-Za-z-]+)", raw[:5000], re.I)
    return m.group(1) if m else ""


# ---------------------------------------------------------------- which pictures of a page
class _Pick(HTMLParser):
    """Collects the page's candidate pictures with what surrounds them (figure, caption, article, menus)."""
    SKIP = {"header", "nav", "footer", "aside", "form"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[dict[str, Any]] = []
        self.hero = ""
        self.depth = {"skip": 0, "main": 0, "figure": 0}
        self.figure: list[dict[str, Any]] = []   # the pictures of the open <figure>, waiting for its caption
        self.caption: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        a = {k: (v or "") for k, v in attrs}
        if tag == "meta" and a.get("property", a.get("name", "")).lower() in ("og:image", "twitter:image") and not self.hero:
            self.hero = a.get("content", "")
        if tag in self.SKIP:
            self.depth["skip"] += 1
        if tag in ("article", "main"):
            self.depth["main"] += 1
        if tag == "figure":
            self.depth["figure"] += 1
            self.figure = []
        if tag == "figcaption":
            self.caption = []
        if tag == "img":
            src = a.get("src", "")
            if not src or src.startswith("data:"):
                src = a.get("data-src", "") or a.get("data-original", "") or (a.get("srcset", "").split(",")[-1].strip().split(" ")[0])
            if not src or src.startswith("data:"):
                return
            def num(v: str) -> int:
                m = re.match(r"\d+", v or "")
                return int(m.group()) if m else 0
            item = {"url": src, "alt": a.get("alt", "").strip()[:300], "caption": "", "width": num(a.get("width", "")),
                    "height": num(a.get("height", "")), "in_menu": self.depth["skip"] > 0,
                    "in_main": self.depth["main"] > 0, "in_figure": self.depth["figure"] > 0, "order": len(self.found)}
            self.found.append(item)
            if item["in_figure"]:
                self.figure.append(item)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self.depth["skip"]:
            self.depth["skip"] -= 1
        if tag in ("article", "main") and self.depth["main"]:
            self.depth["main"] -= 1
        if tag == "figcaption" and self.caption is not None:
            text = " ".join("".join(self.caption).split())[:400]
            for it in self.figure:
                it["caption"] = it["caption"] or text
            self.caption = None
        if tag == "figure" and self.depth["figure"]:
            self.depth["figure"] -= 1
            self.figure = []

    def handle_data(self, data: str) -> None:
        if self.caption is not None:
            self.caption.append(data)


def score(c: dict[str, Any]) -> float:
    """How likely a picture carries information. Below zero: never kept."""
    url, alt, caption = str(c.get("url", "")), str(c.get("alt", "")), str(c.get("caption", ""))
    if NOISE.search(url.split("?")[0]) or url.lower().split("?")[0].endswith((".svg", ".ico")) or c.get("in_menu"):
        return -1.0
    w, h = int(c.get("width") or 0), int(c.get("height") or 0)
    if w and h and not big_enough(w, h):
        return -1.0
    s = 0.0
    s += 3.0 if c.get("hero") else 0.0
    s += 3.0 if caption else (1.0 if c.get("in_figure") else 0.0)
    s += 2.0 if c.get("in_main") else 0.0
    s += 2.0 if INFORMATIVE.search(alt + " " + caption) else 0.0
    s += 1.0 if len(alt) > 12 else 0.0
    s += 1.0 if w * h >= 400 * 300 else 0.0
    return s


def choose(candidates: list[dict[str, Any]], limit: int = MAX_PER_PAGE) -> list[dict[str, Any]]:
    """The best few, best first (the first one is the page's main image), each picture once."""
    seen: set[str] = set()
    ranked = []
    for c in candidates:
        key = str(c.get("url", "")).split("?")[0]
        if not key or key in seen:
            continue
        s = score(c)
        if s < 1.0:  # needs at least something: a caption, a place in the article, a real size
            continue
        seen.add(key)
        ranked.append((bool(c.get("hero")), s, -int(c.get("order", 0)), c))
    ranked.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)  # the page's own main image first: it is its card
    return [c for *_, c in ranked[:limit]]


def pick_from_html(raw: str, base_url: str, limit: int = MAX_PER_PAGE) -> list[dict[str, Any]]:
    p = _Pick()
    try:
        p.feed(raw)
    except Exception:  # a broken page: whatever was read so far
        pass
    out = []
    hero = urllib.parse.urljoin(base_url, p.hero) if p.hero else ""
    for c in p.found:
        c["url"] = urllib.parse.urljoin(base_url, c["url"])
        c["hero"] = bool(hero) and c["url"].split("?")[0] == hero.split("?")[0]
        out.append(c)
    if hero and not any(c["hero"] for c in out):
        out.append({"url": hero, "alt": "", "caption": "", "hero": True, "in_main": True, "order": -1})
    return [c for c in choose(out, limit) if c["url"].startswith(("http://", "https://"))]


# ---------------------------------------------------------------- downloading (a link pasted, no browser)
def download(url: str, timeout: float = 15.0) -> bytes:
    from engine.sources import extract

    parts = urllib.parse.urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise OSError("not a web address")

    def get() -> tuple[str, bytes, str]:
        if not extract._public_host(parts.hostname or ""):
            raise OSError("local or private address")
        req = urllib.request.Request(url, headers={"User-Agent": extract.UA, "Accept": "image/png,image/jpeg,image/webp,image/gif"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return (resp.headers.get_content_type() or "").lower(), resp.read(MAX_IMAGE_BYTES + 1), ""

    if os.environ.get("SBGD_ASSISTANT_PROVIDER") in ("record", "replay"):  # the How-to guides keep what they download
        from engine.assistant import recording

        _mime, data, _ = recording.fetch(url, get)
    else:
        _mime, data, _ = get()
    if len(data) > MAX_IMAGE_BYTES:
        raise OSError("image larger than 8 MB")
    return data


def fetch_all(chosen: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Downloads the chosen pictures; one that fails is simply left out."""
    out = []
    for c in chosen:
        try:
            out.append({**c, "data": download(str(c["url"]))})
        except Exception:
            continue
    return out


# ---------------------------------------------------------------- keeping them
VISION_PAGE_PROMPT = ("Cette image vient d'une page web{about}. Décris de façon factuelle ce qu'elle montre et ce "
                      "qu'elle apprend (schéma, graphique, tableau: les données et les valeurs importantes), et "
                      "transcris le texte visible. 2 à 6 phrases. N'invente rien. Écris toute la description en "
                      "{language}, la langue de la page.")


def keep_for_source(conn, client: Any | None, source_id: str, pictures: list[dict[str, Any]], page_title: str = "",
                    page_text: str = "", lang: str = "") -> dict[str, int]:
    """Keeps a page's chosen pictures (bytes in `data`), reads them, and indexes what they say with the page."""
    from engine.events import utc_now
    from engine.sources import extract, originals
    from engine.sources import core as sources

    root = originals.data_root(conn)
    kept = described = 0
    next_chunk = int(conn.execute("SELECT COALESCE(MAX(idx), -1) + 1 FROM source_chunks WHERE source_id = ?",
                                  (source_id,)).fetchone()[0])
    for pic in pictures:
        if kept >= MAX_PER_PAGE:
            break
        data: bytes = pic.get("data") or b""
        mime = sniff(data)
        if mime is None or len(data) > MAX_IMAGE_BYTES:
            continue
        dims = size_of(data)
        if dims is None or not big_enough(*dims):
            continue
        rel, nbytes = originals.keep_bytes(root, data, KEEP_TYPES[mime])
        if conn.execute("SELECT 1 FROM source_images WHERE source_id = ? AND original = ?", (source_id, rel)).fetchone():
            continue
        alt, caption = str(pic.get("alt") or "")[:300], str(pic.get("caption") or "")[:400]
        path = originals.resolve(root, rel)
        seen = sources._local_ocr_image(path) if path is not None and mime != "image/gif" else ""
        description = ""
        # worth a description: words or numbers in it, a caption that says diagram or chart, or a PNG (on the web,
        # diagrams, charts and screenshots are PNG; photos are JPEG)
        if client is not None and (len(seen) >= 20 or INFORMATIVE.search(alt + " " + caption) or mime == "image/png"):
            about = f" intitulée « {page_title[:120]} »" if page_title else ""
            if caption or alt:
                about += f", légende: « {(caption or alt)[:200]} »"
            prompt = VISION_PAGE_PROMPT.format(about=about, language=language(lang, page_text or page_title))
            try:
                description = sources.describe_image(conn, client, data, mime, prompt)
                described += 1
            except Exception:
                description = ""
        conn.execute("INSERT INTO source_images (source_id, idx, original, mime, bytes, width, height, url, alt, caption,"
                     " description, seen_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (source_id, kept, rel, mime, nbytes, dims[0], dims[1], str(pic.get("url") or "")[:2000], alt, caption,
                      description or None, seen or None, utc_now()))
        said = " ".join(x for x in (caption or alt, description, seen) if x).strip()
        if said:
            for piece in extract.chunk(f"[Image {kept + 1}] {said}"):
                conn.execute("INSERT INTO source_chunks (source_id, idx, text) VALUES (?, ?, ?)", (source_id, next_chunk, piece))
                next_chunk += 1
        kept += 1
    if kept:
        conn.execute("UPDATE sources SET chunks = (SELECT COUNT(*) FROM source_chunks WHERE source_id = ?) WHERE id = ?",
                     (source_id, source_id))
    return {"kept": kept, "described": described}


def list_for_source(conn, source_id: str) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT idx, mime, bytes, width, height, url, alt, caption, description FROM source_images WHERE source_id = ?"
        " ORDER BY idx", (source_id,))]


def path_of(conn, source_id: str, idx: int) -> tuple[Path, str] | None:
    from engine.sources import originals

    row = conn.execute("SELECT original, mime FROM source_images WHERE source_id = ? AND idx = ?", (source_id, idx)).fetchone()
    if row is None:
        return None
    p = originals.resolve(originals.data_root(conn), row["original"])
    return (p, row["mime"]) if p is not None else None
