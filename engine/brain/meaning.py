"""Meaning memory for notes: embeddings, search by meaning, and related ideas.

Stdlib only (no FastAPI) so the assistant tools and tests can use it directly.
Vectors are stored normalised, so cosine similarity is a plain dot product.
Everything degrades quietly: without a key or an embeddings model, nothing here
is called and keyword search keeps working.
"""
from __future__ import annotations

import hashlib
import math
import operator
import re
import sqlite3
import threading
from array import array
from typing import Any

from engine import database
from engine.events import utc_now

# Floors measured with text-embedding-3-small in tools/meaning_bench.py (2026-11-03):
# same idea across French and English scored 0.34-0.56, while two unrelated work
# notes reached 0.33. No fixed floor separates them, so a note keeps its single
# closest note when it scores at least RELATED_FLOOR, plus any note above RELATED_STRONG.
RELATED_FLOOR = 0.33
RELATED_STRONG = 0.45
SEARCH_SCORE = 0.25
RELATED_PER_NOTE = 5
NOTE_TEXT_LIMIT = 6000

# Words too common to be useful in keyword search (French and English).
STOPWORDS = frozenset("""
a à au aux avec ce ces c ça cela cet cette d dans de des du elle en est et être eu il ils j je l la le les leur
lui m ma mais me mes moi mon même n ne ni nos notre nous on ou où par pas pour qu que qui s sa se ses si son sur
t ta te tes toi ton tu un une vos votre vous y comment quoi quel quelle quels quelles est-ce faire fait
the an and are as at be by for from has have how i in is it its of on or that this to was were what when where
which who why will with my me you your we our do does
""".split())


def keywords(query: str) -> list[str]:
    """Search words without the common ones; falls back to all words if nothing is left."""
    words = [w for w in re.findall(r"[\w-]+", query, re.UNICODE) if len(w) > 1]
    kept = [w for w in words if w.casefold() not in STOPWORDS]
    return kept or words


def _hash(title: str, body: str) -> str:
    return hashlib.sha256(f"{title}\n{body}".encode("utf-8")).hexdigest()[:32]


def _text(title: str, body: str) -> str:
    return f"{title}\n\n{body}"[:NOTE_TEXT_LIMIT]


def pack(vec: list[float]) -> bytes:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return array("f", (x / norm for x in vec)).tobytes()


def unpack(blob: bytes) -> array:
    a = array("f")
    a.frombytes(blob)
    return a


def dot(a, b) -> float:
    return sum(map(operator.mul, a, b))


def pending_notes(conn: sqlite3.Connection, model: str, limit: int = 64) -> list[sqlite3.Row]:
    rows = conn.execute(
        "SELECT n.id, n.title, n.body, e.content_hash, e.model FROM notes n"
        " LEFT JOIN note_embeddings e ON e.note_id = n.id WHERE n.status != 'archived'").fetchall()
    out = [r for r in rows if r["model"] != model or r["content_hash"] != _hash(r["title"], r["body"])]
    return out[:limit]


def embed_notes(conn: sqlite3.Connection, client: Any, model: str, batch: int = 64) -> dict[str, Any]:
    """Embeds new or changed notes, then refreshes their related ideas. Records unavailability."""
    rows = [dict(r) for r in pending_notes(conn, model, batch)]
    if not rows:
        return {"embedded": 0}
    vectors, error = call_embed(client, model, rows)
    return store_notes(conn, model, rows, vectors, error)


def call_embed(client: Any, model: str, rows: list[dict[str, Any]]) -> tuple[list[list[float]] | None, str | None]:
    """The network part, kept apart so callers can run it without holding the database."""
    try:
        return client.embed(model, [_text(r["title"], r["body"]) for r in rows]), None
    except Exception as exc:
        return None, str(exc)


def store_notes(conn: sqlite3.Connection, model: str, rows: list[dict[str, Any]],
                vectors: list[list[float]] | None, error: str | None) -> dict[str, Any]:
    if error is not None or vectors is None:
        database.set_setting(conn, "embeddings_status", {"available": False, "model": model,
                                                         "error": str(error)[:300], "checked_at": utc_now()})
        return {"embedded": 0, "error": str(error)}
    now = utc_now()
    current = {r["id"]: _hash(r["title"], r["body"]) for r in conn.execute(
        f"SELECT id, title, body FROM notes WHERE id IN ({','.join('?' * len(rows))})", [r["id"] for r in rows])}
    rows_vecs = [(r, v) for r, v in zip(rows, vectors) if current.get(r["id"]) == _hash(r["title"], r["body"])]
    rows = [r for r, _ in rows_vecs]  # notes deleted or edited during the call are picked up next time
    for r, v in rows_vecs:
        conn.execute("INSERT INTO note_embeddings (note_id, model, content_hash, embedding, updated_at)"
                     " VALUES (?, ?, ?, ?, ?) ON CONFLICT (note_id) DO UPDATE SET model = excluded.model,"
                     " content_hash = excluded.content_hash, embedding = excluded.embedding,"
                     " updated_at = excluded.updated_at",
                     (r["id"], model, _hash(r["title"], r["body"]), pack(v), now))
    database.set_setting(conn, "embeddings_status", {"available": True, "model": model, "checked_at": now})
    for r in rows:
        refresh_related(conn, r["id"], model)
    return {"embedded": len(rows)}


def _vectors(conn: sqlite3.Connection, model: str) -> list[tuple[str, array]]:
    return [(r["note_id"], unpack(r["embedding"])) for r in conn.execute(
        "SELECT e.note_id, e.embedding FROM note_embeddings e JOIN notes n ON n.id = e.note_id"
        " WHERE e.model = ? AND n.status != 'archived'", (model,))]


def _picks(scored: list[tuple[float, str]]) -> list[tuple[float, str]]:
    """scored is sorted best first: the closest note if close enough, plus strong ones."""
    out = [(sc, o) for i, (sc, o) in enumerate(scored)
           if sc >= RELATED_STRONG or (i == 0 and sc >= RELATED_FLOOR)]
    return out[:RELATED_PER_NOTE]


def _store_picks(conn: sqlite3.Connection, owner: str, picks: list[tuple[float, str]]) -> None:
    conn.execute("DELETE FROM note_related WHERE owner = ?", (owner,))
    conn.executemany("INSERT INTO note_related (owner, other, score) VALUES (?, ?, ?)",
                     [(owner, o, round(sc, 4)) for sc, o in picks])


def refresh_related(conn: sqlite3.Connection, note_id: str, model: str) -> int:
    """Recomputes one note's picks, and lets a note whose closest neighbour is now this one update its own."""
    row = conn.execute("SELECT embedding FROM note_embeddings WHERE note_id = ? AND model = ?",
                       (note_id, model)).fetchone()
    if row is None:
        conn.execute("DELETE FROM note_related WHERE owner = ?", (note_id,))
        return 0
    mine = unpack(row["embedding"])
    vecs = dict(_vectors(conn, model))
    scored = sorted(((dot(mine, v), other) for other, v in vecs.items() if other != note_id), reverse=True)
    picks = _picks(scored)
    _store_picks(conn, note_id, picks)
    for sc, other in scored:
        if sc < RELATED_FLOOR:
            break
        best = conn.execute("SELECT MAX(score) FROM note_related WHERE owner = ?", (other,)).fetchone()[0]
        if best is None or sc > best:  # this note may now be the other's closest: recompute that one too
            ov = vecs[other]
            _store_picks(conn, other, _picks(sorted(((dot(ov, v), o) for o, v in vecs.items() if o != other),
                                                    reverse=True)))
    return len(picks)


def _pairs(conn: sqlite3.Connection, where: str = "", args: tuple = ()) -> list[tuple[str, str, float]]:
    """Unordered pairs (a < b) with their score, from either note's picks, archived notes left out."""
    seen: dict[tuple[str, str], float] = {}
    for r in conn.execute("SELECT r.owner, r.other, r.score FROM note_related r"
                          " JOIN notes x ON x.id = r.owner AND x.status != 'archived'"
                          " JOIN notes y ON y.id = r.other AND y.status != 'archived'" + where, args):
        key = tuple(sorted((r["owner"], r["other"])))
        seen[key] = max(seen.get(key, 0.0), r["score"])
    # pairs the user already answered (kept as a link, or dismissed) are no longer suggestions
    answered = {(r["a"], r["b"]) for r in conn.execute("SELECT a, b FROM related_choices")}
    # and items already linked (a [[link]], the Archivist's link) have nothing to suggest
    linked = {tuple(sorted((r["from_note"], r["to_note"]))) for r in conn.execute(
        "SELECT from_note, to_note FROM links WHERE to_note IS NOT NULL")}
    return [(a, b, sc) for (a, b), sc in seen.items() if (a, b) not in answered and (a, b) not in linked]


def related(conn: sqlite3.Connection, note_id: str, limit: int = RELATED_PER_NOTE) -> list[dict[str, Any]]:
    pairs = _pairs(conn, " WHERE r.owner = ? OR r.other = ?", (note_id, note_id))
    others = sorted(((sc, b if a == note_id else a) for a, b, sc in pairs), reverse=True)[:limit]
    out = []
    for sc, other in others:
        n = conn.execute("SELECT id, title, space_id, kind FROM notes WHERE id = ?", (other,)).fetchone()
        if n is not None:
            out.append({**dict(n), "score": sc})
    return out


def related_edges(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [{"from": a, "to": b, "type": "related", "score": sc} for a, b, sc in _pairs(conn)]


def search(conn: sqlite3.Connection, client: Any, model: str, query: str, limit: int = 8,
           min_score: float = SEARCH_SCORE) -> list[dict[str, Any]]:
    vecs = _vectors(conn, model)
    if not vecs:
        return []
    q = unpack(pack(client.embed(model, [query])[0]))
    scored = sorted(((dot(q, v), nid) for nid, v in vecs), reverse=True)
    keep = [(s, nid) for s, nid in scored if s >= min_score][:limit]
    if not keep:
        return []
    rows = {r["id"]: r for r in conn.execute(
        f"SELECT id, space_id, title, kind, updated_at, body FROM notes WHERE id IN ({','.join('?' * len(keep))})",
        [nid for _, nid in keep])}
    return [{"id": nid, "space_id": rows[nid]["space_id"], "title": rows[nid]["title"], "kind": rows[nid]["kind"],
             "updated_at": rows[nid]["updated_at"], "snippet": rows[nid]["body"][:200], "score": round(s, 4),
             "match": "meaning"} for s, nid in keep if nid in rows]


# ------------------------------------------------------------ the meaning map (VIEW-E)
MAP_DIMS = 48      # vectors are first folded down to this many numbers (random directions keep distances roughly)
MAP_ROUNDS = 80    # power-iteration rounds for each of the two axes
_MAP_FOLDS: dict[tuple[str, str, float, float, float], list[float]] = {}
_MAP_DIRS: dict[int, list[array]] = {}
_MAP_LAST: dict[str, Any] = {}


def _fold(model: str, note_id: str, vec: array) -> list[float]:
    """A note's vector in MAP_DIMS numbers; kept in memory, so a map after the first costs little."""
    if len(vec) <= MAP_DIMS:
        return list(vec)
    key = (model, note_id, vec[0], vec[1], vec[2])
    if key not in _MAP_FOLDS:
        if len(vec) not in _MAP_DIRS:
            import random
            rng = random.Random(1729)  # always the same directions: the map does not change between two runs
            _MAP_DIRS[len(vec)] = [array("f", (rng.gauss(0.0, 1.0) for _ in range(len(vec)))) for _ in range(MAP_DIMS)]
        _MAP_FOLDS[key] = [dot(vec, d) for d in _MAP_DIRS[len(vec)]]
    return _MAP_FOLDS[key]


def _main_axis(cov: list[list[float]]) -> list[float]:
    """The direction along which the points spread the most (power iteration, a fixed start)."""
    n = len(cov)
    v = [1.0 + 0.01 * i for i in range(n)]
    for _ in range(MAP_ROUNDS):
        w = [dot(row, v) for row in cov]
        norm = math.sqrt(dot(w, w))
        if norm < 1e-12:
            break
        v = [x / norm for x in w]
    big = max(range(n), key=lambda i: abs(v[i]))  # a fixed sign: the map is not mirrored from one run to the next
    return [-x for x in v] if v[big] < 0 else v


def meaning_map(conn: sqlite3.Connection, model: str) -> dict[str, Any]:
    """Every embedded note as a point on a plane, close points meaning close ideas: {points: {note_id: [x, y]}},
    x and y between -1 and 1. The two axes are the two directions along which the notes differ the most (PCA).
    Fewer than three embedded notes: no map."""
    vecs = _vectors(conn, model)
    total = conn.execute("SELECT COUNT(*) FROM notes WHERE status != 'archived'").fetchone()[0]
    sig = hash((model, tuple((nid, v[0], v[1], v[2]) for nid, v in vecs)))
    if _MAP_LAST.get("sig") == sig:
        return {**_MAP_LAST["map"], "notes": total}
    if len(vecs) < 3:
        return {"points": {}, "count": len(vecs), "notes": total}
    rows = [_fold(model, nid, v) for nid, v in vecs]
    dims = len(rows[0])
    mean = [sum(r[i] for r in rows) / len(rows) for i in range(dims)]
    rows = [[r[i] - mean[i] for i in range(dims)] for r in rows]
    cols = [[r[i] for r in rows] for i in range(dims)]
    cov = [[dot(cols[i], cols[j]) / len(rows) for j in range(dims)] for i in range(dims)]
    first = _main_axis(cov)
    spread = dot(first, [dot(row, first) for row in cov])
    cov2 = [[cov[i][j] - spread * first[i] * first[j] for j in range(dims)] for i in range(dims)]  # take the first axis out
    second = _main_axis(cov2)
    xy = [(dot(r, first), dot(r, second)) for r in rows]
    reach = max(max(abs(x), abs(y)) for x, y in xy) or 1.0
    out = {"points": {vecs[i][0]: [round(xy[i][0] / reach, 4), round(xy[i][1] / reach, 4)] for i in range(len(vecs))},
           "count": len(vecs)}
    _MAP_LAST.update(sig=sig, map=out)
    return {**out, "notes": total}


def status(conn: sqlite3.Connection, model: str) -> dict[str, Any]:
    total = conn.execute("SELECT COUNT(*) FROM notes WHERE status != 'archived'").fetchone()[0]
    done = conn.execute("SELECT COUNT(*) FROM note_embeddings e JOIN notes n ON n.id = e.note_id"
                        " WHERE n.status != 'archived' AND e.model = ?", (model,)).fetchone()[0]
    pairs = conn.execute("SELECT COUNT(*) FROM note_related").fetchone()[0]
    return {"notes": total, "embedded": done, "pending": len(pending_notes(conn, model, 10**6)), "related_pairs": pairs}


# ------------------------------------------------------------ background worker
_WAKE = threading.Event()


def poke() -> None:
    """Asks the worker to look for new or changed notes now instead of at its next tick."""
    _WAKE.set()


class Worker(threading.Thread):
    """Embeds pending notes and source chunks in the background, every `interval` seconds or when poked."""

    def __init__(self, db_path, get_client, interval: float = 30.0):
        super().__init__(name="meaning-worker", daemon=True)
        self.db_path = db_path
        self.get_client = get_client
        self.interval = interval
        self.stopped = threading.Event()
        self.last: dict[str, Any] = {}

    def stop(self) -> None:
        self.stopped.set()
        _WAKE.set()

    def tick(self) -> dict[str, Any]:
        from engine.sources import core as sources  # local import: sources imports brain

        client = self.get_client()
        if client is None:
            return {"skipped": "no key"}
        # The database is never held during a network call: read, call the API, then write.
        with database.session(self.db_path) as conn:
            if not sources.should_try_embeddings(conn):
                return {"skipped": "embeddings unavailable"}
            model = sources.embeddings_model(conn)
            rows = [dict(r) for r in pending_notes(conn, model)]
            pending_chunks = conn.execute("SELECT COUNT(*) FROM source_chunks WHERE embedding IS NULL").fetchone()[0]
        out: dict[str, Any] = {"notes": {"embedded": 0}}
        if rows:
            vectors, error = call_embed(client, model, rows)
            with database.session(self.db_path) as conn:
                out["notes"] = store_notes(conn, model, rows, vectors, error)
        if pending_chunks and not out["notes"].get("error"):
            with database.session(self.db_path) as conn:  # rare (sources are embedded when added)
                out["chunks"] = sources.embed_pending(conn, client, model)
        return out

    def run(self) -> None:
        while not self.stopped.is_set():
            try:
                self.last = self.tick()
            except Exception as exc:  # never kill the engine over a background job
                self.last = {"error": str(exc)[:200]}
            if (self.last.get("notes") or {}).get("embedded", 0) >= 64:
                continue  # more notes are waiting
            _WAKE.wait(self.interval)
            _WAKE.clear()


def search_notes(conn: sqlite3.Connection, client: Any | None, query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Meaning first when note embeddings exist, then keyword hits not already found."""
    from engine import brain
    from engine.sources import core as sources

    results: list[dict[str, Any]] = []
    st = database.get_setting(conn, "embeddings_status") or {}
    if client is not None and st.get("available"):
        try:
            results = search(conn, client, sources.embeddings_model(conn), query, limit)
        except Exception:
            results = []
    seen = {r["id"] for r in results}
    for r in brain.search(conn, query, limit):
        if r["id"] not in seen and len(results) < limit:
            results.append({**r, "match": "words"})
    return results
