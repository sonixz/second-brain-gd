"""Ingestion pipeline: extract -> dedupe -> chunk -> index -> summarise -> note -> file -> embed."""
from __future__ import annotations

import array
import hashlib
import json
import math
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from engine import brain, database
from engine.events import utc_now
from engine.sources import extract, ocr, progress

EMBED_MODEL_DEFAULT = "text-embedding-3-small"
# Cosine floor for text-embedding-3-small: relevant FR->EN hits scored 0.41-0.47,
# unrelated ones at most 0.16 (measured 2026-11-03).
MIN_MEANING_SCORE = 0.25


def _record(conn: sqlite3.Connection, status: str, message: str, **details: Any) -> None:
    database.record_event(conn, {"timestamp": utc_now(), "component": "sources", "stage": "ingest", "status": status,
                                 "message": message, "details": details or None})


def list_sources(conn: sqlite3.Connection, limit: int = 100) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM sources ORDER BY created_at DESC LIMIT ?", (limit,))]


def get_source(conn: sqlite3.Connection, source_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    if row is None:
        raise brain.NotFound(f"source {source_id}")
    return dict(row)


def delete_source(conn: sqlite3.Connection, source_id: str, with_note: bool = True) -> None:
    src = get_source(conn, source_id)
    conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    if with_note and src.get("note_id"):
        try:
            brain.delete_note(conn, src["note_id"])
        except brain.NotFound:
            pass


def _summarise(client: Any, model: str, title: str, text: str) -> dict[str, Any]:
    system = ("Tu prépares une fiche de référence pour un second cerveau. Réponds en JSON avec: title (titre clair et court, "
              "sans mention de langue ni de format), summary (3 à 5 phrases dans la langue du document), key_points (3 à 6 points courts "
              "dans la langue du document), "
              "tags (0 à 3 mots-clés en minuscules, tirets entre les mots). N'invente rien. Langue: écris title, summary et "
              "key_points dans la MÊME langue que le texte du document (document en anglais: tout en anglais; en "
              "français: tout en français), même si ces consignes sont en français.")
    excerpt = text[:12000]
    res = client.complete(model, [{"role": "system", "content": system},
                                  {"role": "user", "content": json.dumps({"title": title, "text": excerpt}, ensure_ascii=False)}],
                          json_mode=True, temperature=0.2)
    try:
        out = json.loads(res["message"]["content"] or "{}")
    except ValueError:
        out = {}
    return {"out": out, "usage": res.get("usage", {}), "model": res.get("model", model)}


def ingest(conn: sqlite3.Connection, client: Any | None, kind: str, uri: str, title: str, text: str, mime: str,
           size: int | None, space_id: str | None = None, summary_model: str = "gpt-4o",
           original: tuple[str, int] | None = None, pages: int | None = None,
           text_engine: str | None = None) -> dict[str, Any]:
    text = (text or "").strip()
    if len(text) < 20:
        raise extract.ExtractError("no readable text found (scanned PDF or empty page?)")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    dup = conn.execute("SELECT id FROM sources WHERE content_hash = ? AND status = 'ready'", (digest,)).fetchone()
    if dup:
        return {**get_source(conn, dup["id"]), "duplicate": True}
    sid = uuid.uuid4().hex[:16]
    now = utc_now()
    conn.execute("INSERT INTO sources (id, kind, uri, title, mime, bytes, content_hash, status, created_at, updated_at)"
                 " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)", (sid, kind, uri, title[:300] or uri, mime, size, digest, now, now))
    pieces = extract.chunk(text)
    for i, piece in enumerate(pieces):
        conn.execute("INSERT INTO source_chunks (source_id, idx, text) VALUES (?, ?, ?)", (sid, i, piece))
    summary: dict[str, Any] = {}
    cost_note = ""
    if client is not None and not mime.startswith("image/"):  # an image's description is already its summary
        try:
            progress.report("summary")
            s = _summarise(client, summary_model, title, text)
            summary = s["out"]
            from engine.assistant.core import _usage_event  # late import: assistant depends on brain only

            _usage_event(conn, "summarise_source", s["model"], s["usage"], client.provider)
        except Exception as exc:  # the source stays usable without a summary
            cost_note = f" (summary failed: {exc})"
    note_title = str(summary.get("title") or title or uri)[:200]
    lines = []
    if summary.get("summary"):
        lines.append(str(summary["summary"]))
    if summary.get("key_points"):
        lines.append("\n".join(f"- {p}" for p in summary["key_points"][:6]))
    if not lines:
        limit = 2000 if mime.startswith("image/") else 600
        lines.append(text[:limit] + ("…" if len(text) > limit else ""))
    lines.append(f"Source: {uri}")
    tags = [str(t).strip().lower().replace(" ", "-") for t in (summary.get("tags") or [])][:3]
    if tags:
        lines.append(" ".join("#" + t for t in tags if t))
    note = brain.create_note(conn, note_title, "\n\n".join(lines), space_id, kind="reference", source="import")
    conn.execute("UPDATE sources SET status = 'ready', note_id = ?, chunks = ?, title = ?, updated_at = ?,"
                 " original = ?, original_bytes = ?, pages = ?, text_engine = ? WHERE id = ?",
                 (note["id"], len(pieces), note_title, utc_now(), original[0] if original else None,
                  original[1] if original else None, pages, text_engine, sid))
    _record(conn, "ok", f"Source added: {note_title} ({len(pieces)} chunks){cost_note}", source_id=sid, kind=kind)
    return {**get_source(conn, sid), "duplicate": False, "summary": summary}


# ---------------------------------------------------------------- search
def search_chunks(conn: sqlite3.Connection, query: str, limit: int = 8) -> list[dict[str, Any]]:
    import re

    from engine.brain.meaning import keywords

    words = keywords(query)
    if not words:
        return []
    q = " OR ".join(f'"{w}"*' for w in words)
    rows = conn.execute(
        "SELECT c.id, c.source_id, c.idx, s.title, s.uri, s.note_id, snippet(chunks_fts, 0, '[', ']', '…', 24) AS snippet,"
        " bm25(chunks_fts) AS score FROM chunks_fts JOIN source_chunks c ON c.id = chunks_fts.rowid"
        " JOIN sources s ON s.id = c.source_id JOIN notes n ON n.id = s.note_id AND n.status != 'archived'"  # trashed items stay out
        " WHERE chunks_fts MATCH ? ORDER BY score LIMIT ?", (q, limit)).fetchall()
    return [dict(r) for r in rows]


def _pack(vec: list[float]) -> bytes:
    return array.array("f", vec).tobytes()


def _unpack(blob: bytes) -> list[float]:
    a = array.array("f")
    a.frombytes(blob)
    return a.tolist()


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def embed_pending(conn: sqlite3.Connection, client: Any, model: str, batch: int = 64) -> dict[str, Any]:
    """Embeds chunks that have none yet. Records 'unavailable' when the account lacks the model."""
    rows = conn.execute("SELECT id, text FROM source_chunks WHERE embedding IS NULL LIMIT ?", (batch,)).fetchall()
    if not rows:
        return {"embedded": 0}
    try:
        vectors = client.embed(model, [r["text"] for r in rows])
    except Exception as exc:
        database.set_setting(conn, "embeddings_status", {"available": False, "model": model, "error": str(exc)[:300],
                                                         "checked_at": utc_now()})
        return {"embedded": 0, "error": str(exc)}
    for r, v in zip(rows, vectors):
        conn.execute("UPDATE source_chunks SET embedding = ?, model = ? WHERE id = ?", (_pack(v), model, r["id"]))
    database.set_setting(conn, "embeddings_status", {"available": True, "model": model, "checked_at": utc_now()})
    return {"embedded": len(rows)}


def semantic_search(conn: sqlite3.Connection, client: Any, model: str, query: str, limit: int = 8,
                    min_score: float = MIN_MEANING_SCORE) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT c.id, c.source_id, c.text, c.embedding, s.title, s.uri, s.note_id FROM source_chunks c"
                        " JOIN sources s ON s.id = c.source_id WHERE c.embedding IS NOT NULL AND c.model = ?", (model,)).fetchall()
    if not rows:
        return []
    q = client.embed(model, [query])[0]
    scored = sorted(((_cos(q, _unpack(r["embedding"])), r) for r in rows), key=lambda x: x[0], reverse=True)
    scored = [(s, r) for s, r in scored if s >= min_score][:limit]
    return [{"id": r["id"], "source_id": r["source_id"], "title": r["title"], "uri": r["uri"], "note_id": r["note_id"],
             "snippet": r["text"][:300], "score": round(s, 4)} for s, r in scored]


VISION_PROMPT = ("Décris cette image pour un second cerveau, en français et de façon factuelle: ce qu'elle montre, "
                 "le texte visible (transcris-le fidèlement), les éléments importants (schéma, graphique, personnes, lieux). "
                 "3 à 8 phrases. N'invente rien.")


def describe_image(conn: sqlite3.Connection, client: Any, data: bytes, mime: str, prompt: str = VISION_PROMPT) -> str:
    """A vision model turns an image into searchable text (no key: a placeholder the user can edit)."""
    import base64

    model = database.get_setting(conn, "assistant_vision_model", "gpt-4o-mini")
    res = client.complete(model, [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64," + base64.b64encode(data).decode("ascii")}}]}],
        temperature=0.2)
    from engine.assistant.core import _usage_event

    _usage_event(conn, "describe_image", res["model"], res["usage"], client.provider)
    return (res["message"].get("content") or "").strip()


OCR_PROMPT = ("Cette image est une page d'un document PDF numérisé. Transcris fidèlement tout le texte visible, "
              "dans sa langue d'origine, en gardant l'ordre de lecture, les titres et les listes. N'ajoute aucun "
              "commentaire. Si la page ne contient pas de texte, décris-la en une phrase entre crochets.")
OCR_MAX_PAGES = 15


def read_scanned_pdf(conn: sqlite3.Connection, client: Any, path: Path, pages: int) -> str:
    """A PDF made of page images (scanned, or exported as pictures): the vision model reads each page."""
    import base64
    import tempfile

    from engine.assistant.core import _usage_event
    from engine.sources import render

    model = database.get_setting(conn, "assistant_vision_model", "gpt-4o-mini")
    out = []
    with tempfile.TemporaryDirectory(prefix="sbgd-ocr-") as tmp:
        n = min(pages, OCR_MAX_PAGES)
        for page in range(1, n + 1):
            progress.report("ai", page - 1, n)
            data = render.render_page(path, page, 1400, Path(tmp))
            res = client.complete(model, [{"role": "user", "content": [
                {"type": "text", "text": OCR_PROMPT},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(data).decode("ascii")}}]}],
                temperature=0.0)
            _usage_event(conn, "read_scanned_page", res["model"], res["usage"], client.provider)
            out.append((res["message"].get("content") or "").strip())
    if pages > OCR_MAX_PAGES:
        out.append(f"[Pages {OCR_MAX_PAGES + 1} à {pages} non lues: document trop long pour la lecture d'images.]")
    return "\n\n".join(t for t in out if t)


def ingest_file(conn: sqlite3.Connection, client: Any | None, path: str, space_id: str | None = None) -> dict[str, Any]:
    from engine.sources import originals, render

    p = Path(path).expanduser()
    title, text, mime = extract.from_file(p)
    text_engine = None
    root = originals.data_root(conn)
    kept = originals.keep_file(root, p)
    pages = None
    if mime == "application/pdf":
        try:
            pages = render.page_count(p)
        except render.RenderError:
            pages = None
        if len(text.strip()) < 20 and pages:  # no text layer: every page is a picture
            text, text_engine = read_pdf_images(conn, client, p, pages)
    elif mime.startswith("image/"):
        pages = 1
        data = p.read_bytes()
        desc = ""
        if client is not None:
            try:
                desc = describe_image(conn, client, data, mime)
            except Exception as exc:  # the image is still kept and shown
                desc = f"(description indisponible: {exc.__class__.__name__})"
        seen = _local_ocr_image(p)  # the text inside the image, read on this machine (no key needed)
        text = f"Image: {p.name}\n\n{desc or 'Pas encore de description (ajoute ta clé OpenAI).'}"
        if seen:
            text += "\n\nTexte dans l'image :\n" + seen
            text_engine = "ocr-" + ("windows" if ocr.engine_name() == "recorded" else str(ocr.engine_name()))  # recorded = a Windows OCR reading
    return ingest(conn, client, "file", str(p), title, text, mime, p.stat().st_size, space_id, original=kept, pages=pages,
                  text_engine=text_engine)


def _local_ocr_image(p: Path) -> str:
    from engine.sources import ocr

    if ocr.engine_name() is None:
        return ""
    try:
        return "\n".join(ocr.read_images([p])).strip()
    except ocr.OcrError:
        return ""


def ocr_mode(conn: sqlite3.Connection) -> str:
    """'local' (default: scanned pages are read on this machine) or 'ai' (always the vision model)."""
    return "ai" if database.get_setting(conn, "ocr_mode", "local") == "ai" else "local"


def read_pdf_images(conn: sqlite3.Connection, client: Any | None, path: Path, pages: int) -> tuple[str, str]:
    """A PDF with no text layer: local OCR first, the vision model only when asked or when nothing local works.
    Returns (text, engine)."""
    from engine.sources import ocr

    local = ocr.engine_name()
    problem = ""
    if local and ocr_mode(conn) == "local":
        try:
            text = ocr.read_pdf(path, pages, on_progress=progress.report)
            _record(conn, "ok", f"Read {pages} scanned page(s) locally ({local} OCR)", engine=local, pages=pages)
            if len(text.strip()) >= 20:
                return text, "ocr-" + ("windows" if local == "recorded" else local)  # recorded = a Windows OCR reading
            problem = "local OCR found no text"
        except (ocr.OcrError, OSError) as exc:
            problem = str(exc)
            _record(conn, "error", f"Local OCR failed: {exc}", engine=local)
    if client is not None:
        return read_scanned_pdf(conn, client, path, pages), "ocr-ai"
    if local is None:
        raise extract.ExtractError("this PDF has no text, only page images; no local OCR here "
                                   "(Windows has one built in; on Linux install tesseract-ocr and tesseract-ocr-fra) "
                                   "and no OpenAI key to read it")
    raise extract.ExtractError(f"this PDF has no text, only page images, and they could not be read ({problem})")


def reread_with_ai(conn: sqlite3.Connection, client: Any, source_id: str) -> dict[str, Any]:
    """« Relire avec l'IA »: a scanned PDF's pages are read again by the vision model; passages and summary follow."""
    from engine.sources import originals

    src = get_source(conn, source_id)
    path = originals.resolve(originals.data_root(conn), src.get("original"))
    if path is None or src.get("mime") != "application/pdf" or not src.get("pages"):
        raise extract.ExtractError("only a kept PDF can be re-read")
    text = read_scanned_pdf(conn, client, path, int(src["pages"]))
    if len(text.strip()) < 20:
        raise extract.ExtractError("the vision model found no text")
    conn.execute("DELETE FROM source_chunks WHERE source_id = ?", (source_id,))
    pieces = extract.chunk(text)
    for i, piece in enumerate(pieces):
        conn.execute("INSERT INTO source_chunks (source_id, idx, text) VALUES (?, ?, ?)", (source_id, i, piece))
    conn.execute("UPDATE sources SET chunks = ?, text_engine = 'ocr-ai', content_hash = ?, updated_at = ? WHERE id = ?",
                 (len(pieces), hashlib.sha256(text.encode("utf-8")).hexdigest(), utc_now(), source_id))
    if src.get("note_id"):
        try:
            s = _summarise(client, database.get_setting(conn, "assistant_chat_model", "gpt-4o"), str(src["title"]), text)
            out = s["out"]
            lines = [str(out["summary"])] if out.get("summary") else []
            if out.get("key_points"):
                lines.append("\n".join(f"- {k}" for k in out["key_points"][:6]))
            if lines:
                lines.append(f"Source: {src['uri']}")
                brain.update_note(conn, src["note_id"], body="\n\n".join(lines))
        except Exception:  # the new passages are what matters; the old summary stays
            pass
    _record(conn, "ok", f"Re-read with AI: {src['title']} ({len(pieces)} chunks)", source_id=source_id)
    return {**get_source(conn, source_id), "duplicate": False}


MAX_PAGE_HTML = 3_000_000
MAX_PAGE_TEXT = 1_000_000


def ingest_page(conn: sqlite3.Connection, client: Any | None, url: str, title: str, html: str, text: str,
                space_id: str | None = None, pictures: list[dict[str, Any]] | None = None, lang: str = "") -> dict[str, Any]:
    """A page as the user's browser shows it (the extension): after their login, scripts and checks. Nothing is
    downloaded again. The page's HTML is kept as its original; its readable text is indexed. `pictures`: the few
    images the extension chose on the page, with their bytes (engine/sources/images.py keeps and reads them)."""
    from engine.sources import originals

    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise extract.ExtractError("only web pages (http/https) can be sent from the browser")
    html = (html or "")[:MAX_PAGE_HTML]
    page_title, readable = extract.html_to_text(html) if html else ("", "")
    rendered = (text or "")[:MAX_PAGE_TEXT].strip()
    if len(readable) < 200 and len(rendered) > len(readable):  # an app-like page: what was on screen reads better
        readable = rendered
    kept = originals.keep_bytes(originals.data_root(conn), html.encode("utf-8"), "html") if html else None
    out = ingest(conn, client, "url", url, (title or page_title or url)[:300], readable, "text/html",
                 len(html.encode("utf-8")) if html else len(readable), space_id, original=kept, text_engine="browser")
    if pictures and not out.get("duplicate"):  # the few pictures worth keeping, as the browser showed them
        from engine.sources import images

        out["images"] = images.keep_for_source(conn, client, out["id"], pictures, title or page_title, readable,
                                               lang or images.html_lang(html))
    return out


def ingest_url(conn: sqlite3.Connection, client: Any | None, url: str, space_id: str | None = None) -> dict[str, Any]:
    from engine.sources import originals, render

    title, text, mime, size, data = extract.from_url_raw(url)
    ext = "pdf" if mime == "application/pdf" else ("html" if "html" in mime else "txt")
    kept = originals.keep_bytes(originals.data_root(conn), data, ext)
    pages = None
    if ext == "pdf":
        try:
            pages = render.page_count(originals.data_root(conn) / kept[0])
        except render.RenderError:
            pages = None
    out = ingest(conn, client, "url", url.strip(), title, text, mime, size, space_id, original=kept, pages=pages)
    if ext == "html" and not out.get("duplicate"):  # its main image and its figures, downloaded too
        from engine.sources import images

        raw = data.decode("utf-8", errors="replace")
        chosen = images.pick_from_html(raw, url.strip())
        if chosen:
            out["images"] = images.keep_for_source(conn, client, out["id"], images.fetch_all(chosen), title, text,
                                                   images.html_lang(raw))
    return out


IMAGE_PROMPT = ("Cette image a été gardée depuis la page web « {page} ». Décris-la de façon factuelle: ce qu'elle "
                "montre, ce qu'elle apprend (schéma, graphique, tableau: les données importantes), le texte visible "
                "(transcris-le fidèlement). 3 à 8 phrases. N'invente rien. Écris toute la description en {language}, "
                "la langue de la page.")


def ingest_image(conn: sqlite3.Connection, client: Any | None, data: bytes, page_url: str, page_title: str = "",
                 alt: str = "", image_url: str = "", space_id: str | None = None, lang: str = "") -> dict[str, Any]:
    """One picture the user chose on a page (right-click → Send this image to the Brain): an item of its own,
    like an image dropped on the window, that remembers the page it came from."""
    from engine.sources import images, originals

    page_url = (page_url or "").strip()
    if not page_url.startswith(("http://", "https://")):
        raise extract.ExtractError("only pictures from web pages (http/https) can be sent from the browser")
    mime = images.sniff(data)
    if mime is None:
        raise extract.ExtractError("this picture's format cannot be kept (PNG, JPEG, WebP or GIF only)")
    if len(data) > images.MAX_IMAGE_BYTES:
        raise extract.ExtractError("this picture is larger than 8 MB")
    root = originals.data_root(conn)
    kept = originals.keep_bytes(root, data, images.KEEP_TYPES[mime])
    dup = conn.execute("SELECT id FROM sources WHERE original = ? AND status = 'ready'", (kept[0],)).fetchone()
    if dup:
        return {**get_source(conn, dup["id"]), "duplicate": True}
    desc = ""
    if client is not None:
        try:
            desc = describe_image(conn, client, data, mime, IMAGE_PROMPT.format(
                page=(page_title or page_url)[:160], language=images.language(lang, page_title + " " + alt)))
        except Exception as exc:  # the picture is still kept and shown
            desc = f"(description unavailable: {exc.__class__.__name__})"
    path = originals.resolve(root, kept[0])
    seen = _local_ocr_image(path) if path is not None and mime != "image/gif" else ""
    host = page_url.split("/")[2] if page_url.count("/") >= 2 else page_url
    text = f"Image from {page_title or host}\n\n{desc or 'No description yet (add your OpenAI key).'}"
    if image_url and not image_url.startswith("data:"):
        text += f"\n\nImage address: {image_url[:500]}"
    text_engine = None
    if seen:
        text += "\n\nText in the image:\n" + seen
        text_engine = "ocr-" + ("windows" if ocr.engine_name() == "recorded" else str(ocr.engine_name()))
    title = alt.strip() if len(alt.strip()) >= 8 else f"Image from {page_title or host}"
    return ingest(conn, client, "url", page_url, title[:200], text, mime, len(data), space_id, original=kept, pages=1,
                  text_engine=text_engine)


# ------------------------------------------------- embeddings status, search
def embeddings_model(conn) -> str:
    return database.get_setting(conn, "embeddings_model", EMBED_MODEL_DEFAULT)


def should_try_embeddings(conn) -> bool:
    st = database.get_setting(conn, "embeddings_status") or {}
    if st.get("available", True):
        return True
    try:  # an unavailable model is re-checked at most every 6 hours
        checked = datetime.fromisoformat(str(st.get("checked_at", "")).replace("Z", "+00:00"))
    except ValueError:
        return True
    return datetime.now(timezone.utc) - checked > timedelta(hours=6)


def search_any(conn, client, query: str, limit: int = 8) -> list[dict[str, Any]]:
    """Meaning first when embeddings exist, words otherwise (or as a complement)."""
    results: list[dict[str, Any]] = []
    st = database.get_setting(conn, "embeddings_status") or {}
    if client is not None and st.get("available"):
        try:
            results = [{**x, "match": "meaning"} for x in semantic_search(conn, client, embeddings_model(conn), query, limit)]
        except Exception:
            results = []
    seen = {x["id"] for x in results}
    for x in search_chunks(conn, query, limit):
        if x["id"] not in seen and len(results) < limit:
            results.append({**x, "match": "words"})
    return results
