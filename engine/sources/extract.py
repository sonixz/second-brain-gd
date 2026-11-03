"""Text extraction. Stdlib for HTML, DOCX, text; pypdf for PDF (imported lazily)."""
from __future__ import annotations

import html
import ipaddress
import re
import socket
import urllib.parse
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path

MAX_BYTES = 15 * 1024 * 1024
TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".json", ".log", ".rst", ".org"}
SUPPORTED = TEXT_SUFFIXES | {".pdf", ".docx", ".html", ".htm"}
UA = "SecondBrainGD/0.1 (+local knowledge app)"


class ExtractError(ValueError):
    pass


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "aside"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "pre", "blockquote"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag in self.SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def html_to_text(raw: str) -> tuple[str, str]:
    p = _Text()
    p.feed(raw)
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.parts))
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return html.unescape(p.title.strip()), text


def docx_to_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ExtractError("not a valid .docx file") from exc
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml)).strip()


def pdf_to_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ExtractError("PDF support is not installed (pypdf)") from exc
    try:
        reader = PdfReader(str(path))
        pages = [(page.extract_text() or "") for page in reader.pages[:300]]
    except Exception as exc:
        raise ExtractError(f"cannot read this PDF: {exc.__class__.__name__}") from exc
    return "\n\n".join(pages).strip()


def from_file(path: Path) -> tuple[str, str, str]:
    """Returns (title, text, mime)."""
    if not path.is_file():
        raise ExtractError(f"file not found: {path}")
    if path.stat().st_size > MAX_BYTES:
        raise ExtractError("file is larger than 15 MB")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ExtractError(f"unsupported file type {suffix or '(none)'}; supported: " + ", ".join(sorted(SUPPORTED)))
    if suffix == ".pdf":
        return path.stem, pdf_to_text(path), "application/pdf"
    if suffix == ".docx":
        return path.stem, docx_to_text(path), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    raw = path.read_bytes().decode("utf-8", errors="replace")
    if suffix in (".html", ".htm"):
        title, text = html_to_text(raw)
        return title or path.stem, text, "text/html"
    return path.stem, raw.strip(), "text/plain"


def _public_host(host: str) -> bool:
    """Refuses local/private addresses: the engine must not be used to reach the LAN."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def from_url(url: str, timeout: float = 20.0) -> tuple[str, str, str, int]:
    """Returns (title, text, mime, bytes)."""
    parts = urllib.parse.urlparse(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ExtractError("only http(s) links are supported")
    if not _public_host(parts.hostname):
        raise ExtractError("this address points to a local or private network")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,text/plain,application/pdf"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            mime = (resp.headers.get_content_type() or "").lower()
            data = resp.read(MAX_BYTES + 1)
            charset = resp.headers.get_content_charset() or "utf-8"
    except OSError as exc:
        raise ExtractError(f"cannot download the page: {exc}") from exc
    if len(data) > MAX_BYTES:
        raise ExtractError("page is larger than 15 MB")
    if mime == "application/pdf":
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
            fh.write(data)
        try:
            return Path(parts.path).stem or parts.hostname, pdf_to_text(Path(fh.name)), mime, len(data)
        finally:
            Path(fh.name).unlink(missing_ok=True)
    raw = data.decode(charset, errors="replace")
    if "html" in mime or raw.lstrip().lower().startswith(("<!doctype", "<html")):
        title, text = html_to_text(raw)
        return title or parts.hostname, text, mime or "text/html", len(data)
    return parts.hostname, raw.strip(), mime or "text/plain", len(data)


def chunk(text: str, size: int = 1200, overlap: int = 150) -> list[str]:
    """Paragraph-aware chunks of about `size` characters with a small overlap."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        while len(p) > size:  # very long paragraph: hard split
            head, p = p[:size], p[size - overlap:]
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(head)
        if len(cur) + len(p) + 2 > size and cur:
            chunks.append(cur)
            cur = cur[-overlap:] + "\n\n" + p if overlap else p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        chunks.append(cur)
    return chunks
