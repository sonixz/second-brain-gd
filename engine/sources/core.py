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
from engine.sources import extract

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
    system = ("Tu prépares une fiche de référence pour un second cerveau. Réponds en JSON avec: title (titre clair, "
              "langue du document), summary (3 à 5 phrases en français), key_points (3 à 6 points courts en français), "
              "tags (0 à 3 mots-clés en minuscules, tirets entre les mots). N'invente rien.")
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
           size: int | None, space_id: str | None = None, summary_model: str = "gpt-4o") -> dict[str, Any]:
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
    if client is not None:
        try:
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
        lines.append(text[:600] + ("…" if len(text) > 600 else ""))
    lines.append(f"Source: {uri}")
    tags = [str(t).strip().lower().replace(" ", "-") for t in (summary.get("tags") or [])][:3]
    if tags:
        lines.append(" ".join("#" + t for t in tags if t))
    note = brain.create_note(conn, note_title, "\n\n".join(lines), space_id, kind="reference", source="import")
    conn.execute("UPDATE sources SET status = 'ready', note_id = ?, chunks = ?, title = ?, updated_at = ? WHERE id = ?",
                 (note["id"], len(pieces), note_title, utc_now(), sid))
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
        " JOIN sources s ON s.id = c.source_id WHERE chunks_fts MATCH ? ORDER BY score LIMIT ?", (q, limit)).fetchall()
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


def ingest_file(conn: sqlite3.Connection, client: Any | None, path: str, space_id: str | None = None) -> dict[str, Any]:
    p = Path(path).expanduser()
    title, text, mime = extract.from_file(p)
    return ingest(conn, client, "file", str(p), title, text, mime, p.stat().st_size, space_id)


def ingest_url(conn: sqlite3.Connection, client: Any | None, url: str, space_id: str | None = None) -> dict[str, Any]:
    title, text, mime, size = extract.from_url(url)
    return ingest(conn, client, "url", url.strip(), title, text, mime, size, space_id)


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
