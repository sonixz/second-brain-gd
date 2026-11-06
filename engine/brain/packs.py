"""Brain packs (Loop 11): export a Brain, or part of it, as one `.brain` file; import one as a layer.

A pack is a zip with exactly two entries:
  manifest.json  {"format": "sbgd-brain-pack", "version": 1, title, author, licence, description,
                  created_at, app_version, schema_version, embedding_model, selection, counts, sha256}
  data.sqlite    a Second Brain database holding only the selected items: places, items, links,
                 themes, the archivist's records, meaning vectors and related ideas, and the sources'
                 indexed text. Nothing else leaves: no settings, keys, conversations, events or costs.

Import is careful with what it reads: only those two entries, size limits, the checksum must
match, the database is opened read-only, and imported text is data (it is never run or obeyed).
Every imported item gets a new id and the layer's id; identical items already in the Brain are
skipped. Vectors are reused when the embedding model matches; otherwise the meaning worker
re-embeds the new items on its own.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

from engine import VERSION, brain, database
from engine.events import utc_now

FORMAT = "sbgd-brain-pack"
PACK_VERSION = 1
MAX_PACK_BYTES = 512 * 1024 * 1024
ENTRIES = {"manifest.json", "data.sqlite"}


class PackError(RuntimeError):
    pass


# ---------------------------------------------------------------- selection
def resolve(conn: sqlite3.Connection, selection: dict[str, Any], client: Any = None) -> list[str]:
    """Item ids for a selection: {"all": true} | {"space_id"} | {"place": name} | {"theme"} | {"query"} | {"note_ids"}."""
    base = "SELECT id FROM notes WHERE status != 'archived' AND source != 'seed'"
    if selection.get("note_ids"):
        ids = [str(i) for i in selection["note_ids"]]
        rows = conn.execute(f"SELECT id FROM notes WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()
        return [r["id"] for r in rows]
    if selection.get("space_id") or selection.get("place"):
        sid = selection.get("space_id")
        if not sid:
            row = conn.execute("SELECT id FROM spaces WHERE name = ? COLLATE NOCASE AND archived_at IS NULL",
                               (str(selection["place"]).strip(),)).fetchone()
            if row is None:
                raise brain.NotFound(f"place {selection['place']}")
            sid = row["id"]
        # a place and the projects filed under it (an area brings its projects)
        sids = [sid] + [r["id"] for r in conn.execute("SELECT id FROM spaces WHERE area_id = ?", (sid,))]
        return [r["id"] for r in conn.execute(base + f" AND space_id IN ({','.join('?' * len(sids))})", sids)]
    if selection.get("theme"):
        t = str(selection["theme"]).lstrip("#").strip().lower()
        return [r["id"] for r in conn.execute(
            base + " AND id IN (SELECT nt.note_id FROM note_tags nt JOIN tags g ON g.id = nt.tag_id WHERE g.name = ?)", (t,))]
    if selection.get("query"):
        from engine.brain import meaning

        return [h["id"] for h in meaning.search_notes(conn, client, str(selection["query"]), 60)]
    if selection.get("all"):
        return [r["id"] for r in conn.execute(base)]
    raise ValueError("empty selection")


def _space_ids(conn: sqlite3.Connection, note_ids: list[str]) -> list[str]:
    if not note_ids:
        return []
    q = ",".join("?" * len(note_ids))
    ids = {r["space_id"] for r in conn.execute(f"SELECT DISTINCT space_id FROM notes WHERE id IN ({q})", note_ids)}
    # keep the area above an exported project, so the structure travels with it
    for r in conn.execute(f"SELECT area_id FROM spaces WHERE id IN ({','.join('?' * len(ids))}) AND area_id IS NOT NULL",
                          list(ids)):
        ids.add(r["area_id"])
    return sorted(ids)


def preview(conn: sqlite3.Connection, selection: dict[str, Any], client: Any = None) -> dict[str, Any]:
    ids = resolve(conn, selection, client)
    q = ",".join("?" * len(ids)) or "''"
    titles = [r["title"] for r in conn.execute(f"SELECT title FROM notes WHERE id IN ({q}) ORDER BY created_at DESC LIMIT 12", ids)]
    sources = conn.execute(f"SELECT COUNT(*) FROM sources WHERE note_id IN ({q})", ids).fetchone()[0]
    sids = _space_ids(conn, ids)
    places = [r["name"] for r in conn.execute(f"SELECT name FROM spaces WHERE id IN ({','.join('?' * len(sids)) or chr(39) * 2})", sids)]
    return {"items": len(ids), "sources": sources, "places": places, "titles": titles,
            "never_included": NEVER_INCLUDED["fr" if database.get_setting(conn, "ui_language", "en") == "fr" else "en"]}


NEVER_INCLUDED = {"en": ["your API keys", "settings", "conversations", "costs and system events"],
                  "fr": ["tes clés d’API", "les réglages", "les conversations", "les coûts et les événements système"]}


# ---------------------------------------------------------------- export
def _cols(conn: sqlite3.Connection, schema: str, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA {schema}.table_info({table})")]


def _copy(conn: sqlite3.Connection, table: str, where: str, args: list[Any]) -> int:
    cols = [c for c in _cols(conn, "src", table) if c in set(_cols(conn, "main", table))]
    names = ", ".join(cols)
    cur = conn.execute(f"INSERT OR IGNORE INTO main.{table} ({names}) SELECT {names} FROM src.{table} WHERE {where}", args)
    return cur.rowcount


def slug(text: str) -> str:
    s = re.sub(r"[^\w-]+", "-", text.strip().lower()).strip("-")
    return (s or "brain")[:48]


ORIGINAL_ENTRY = re.compile(r"^originals/[0-9a-f]{2}/([0-9a-f]{64})\.[a-z0-9]{1,8}$")


def export(db_path: Path, selection: dict[str, Any], out_dir: Path, title: str, author: str = "",
           licence: str = "", description: str = "", client: Any = None, include_originals: bool = False) -> dict[str, Any]:
    with database.session(db_path) as conn:
        ids = resolve(conn, selection, client)
        if not ids:
            raise ValueError("nothing to export for this selection")
        spaces = _space_ids(conn, ids)
        from engine.sources.core import embeddings_model

        model = embeddings_model(conn)
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="sbgd-pack-"))
    try:
        data = work / "data.sqlite"
        database.migrate(data)
        conn = database.connect(data)
        try:
            conn.execute("ATTACH DATABASE ? AS src", (str(db_path),))
            conn.execute("DELETE FROM main.spaces")  # the fresh schema's own Inbox row, if any
            n = {}
            qs = ",".join("?" * len(spaces))
            qn = ",".join("?" * len(ids))
            n["places"] = _copy(conn, "spaces", f"id IN ({qs})", spaces)
            conn.execute("UPDATE main.spaces SET layer_id = NULL, archived_at = NULL")
            n["items"] = _copy(conn, "notes", f"id IN ({qn})", ids)
            conn.execute("UPDATE main.notes SET layer_id = NULL")
            n["links"] = _copy(conn, "links", f"from_note IN ({qn}) AND to_note IN ({qn})", ids + ids)
            _copy(conn, "tags", f"id IN (SELECT tag_id FROM src.note_tags WHERE note_id IN ({qn}))", ids)
            _copy(conn, "note_tags", f"note_id IN ({qn})", ids)
            _copy(conn, "item_meta", f"note_id IN ({qn})", ids)
            n["vectors"] = _copy(conn, "note_embeddings", f"note_id IN ({qn})", ids)
            _copy(conn, "note_related", f"owner IN ({qn}) AND other IN ({qn})", ids + ids)
            n["sources"] = _copy(conn, "sources", f"note_id IN ({qn})", ids)
            _copy(conn, "source_chunks", "source_id IN (SELECT id FROM main.sources)", [])
            n["pictures"] = _copy(conn, "source_images", "source_id IN (SELECT id FROM main.sources)", [])  # Loop 25
            version = conn.execute("SELECT MAX(version) FROM main.schema_migrations").fetchone()[0]
            originals = [r[0] for r in conn.execute("SELECT DISTINCT original FROM main.sources WHERE original IS NOT NULL")]
            pictures = [r[0] for r in conn.execute("SELECT DISTINCT original FROM main.source_images")]
            conn.commit()
            conn.execute("DETACH DATABASE src")
            conn.execute("VACUUM")
        finally:
            conn.close()
        digest = hashlib.sha256(data.read_bytes()).hexdigest()
        from engine.sources import originals as kept_files

        root = db_path.parent.parent if db_path.parent.name == "data" else db_path.parent
        files = [(rel, kept_files.resolve(root, rel)) for rel in originals] if include_originals else []
        # a page's pictures always travel with it: a few small files that its card and reading view show
        files += [(rel, kept_files.resolve(root, rel)) for rel in pictures if rel not in originals or not include_originals]
        files = [(rel, p) for rel, p in dict(files).items() if p is not None]
        n["originals"] = len(files)
        manifest = {"format": FORMAT, "version": PACK_VERSION, "title": title.strip()[:120] or "Brain pack",
                    "author": author.strip()[:120], "licence": licence.strip()[:120],
                    "description": description.strip()[:1000], "created_at": utc_now(), "app_version": VERSION,
                    "schema_version": version, "embedding_model": model, "selection": selection, "counts": n,
                    "sha256": digest}
        name = f"{slug(manifest['title'])}-{dt.date.today().isoformat()}.brain"
        target = out_dir / name
        k = 2
        while target.exists():
            target = out_dir / name.replace(".brain", f"-{k}.brain")
            k += 1
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            z.write(data, "data.sqlite")
            for rel, p in files:
                z.write(p, rel)
        return {"path": str(target), "bytes": target.stat().st_size, "manifest": manifest}
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- import
def read_pack(path: Path, work: Path) -> tuple[dict[str, Any], Path]:
    """Validates a pack and extracts its database into `work`. Raises PackError with a plain reason."""
    if not path.is_file():
        raise PackError("file not found")
    if path.stat().st_size > MAX_PACK_BYTES:
        raise PackError("this pack is larger than 512 MB")
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise PackError("not a Brain pack (not a zip file)") from None
    with z:
        names = set(z.namelist())
        extra = {n for n in names - ENTRIES if not ORIGINAL_ENTRY.match(n)}
        if extra or not ENTRIES <= names:
            raise PackError(f"unexpected content in the pack: {sorted(extra) or sorted(ENTRIES - names)}")
        total = sum(z.getinfo(n).file_size for n in names)
        if total > MAX_PACK_BYTES * 2:
            raise PackError("this pack unpacks to more than 1 GB")
        info = z.getinfo("data.sqlite")
        if info.file_size > MAX_PACK_BYTES:
            raise PackError("the pack's database is too large")
        try:
            manifest = json.loads(z.read("manifest.json").decode("utf-8"))
        except ValueError:
            raise PackError("unreadable manifest") from None
        if manifest.get("format") != FORMAT:
            raise PackError("not a Second Brain pack")
        if int(manifest.get("version", 0)) > PACK_VERSION:
            raise PackError("this pack was made by a newer version of the app")
        data = work / "data.sqlite"
        with z.open("data.sqlite") as src, data.open("wb") as out:
            shutil.copyfileobj(src, out)
    if hashlib.sha256(data.read_bytes()).hexdigest() != manifest.get("sha256"):
        raise PackError("the pack is damaged (checksum mismatch)")
    return manifest, data


def import_originals(path: Path, root: Path) -> int:
    """Copies the pack's originals into <data>/originals. Each file must hash to its own name."""
    count = 0
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            m = ORIGINAL_ENTRY.match(name)
            if not m:
                continue
            content = z.read(name)
            if hashlib.sha256(content).hexdigest() != m.group(1):
                raise PackError(f"a document in the pack is damaged ({name.rsplit('/', 1)[-1][:12]}…)")
            target = root / name
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            count += 1
    return count


def _hash(title: str, body: str) -> str:
    return hashlib.sha256((title.strip() + "\n" + body.strip()).encode("utf-8")).hexdigest()


def import_pack(db_path: Path, path: Path) -> dict[str, Any]:
    work = Path(tempfile.mkdtemp(prefix="sbgd-import-"))
    try:
        manifest, data = read_pack(path, work)
        src = sqlite3.connect(f"file:{data}?mode=ro", uri=True)
        src.row_factory = sqlite3.Row
        ours_version = database.schema_version(db_path)
        theirs = src.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] or 0
        if theirs > ours_version:
            raise PackError("this pack needs a newer version of the app")
        with database.session(db_path) as conn:
            from engine.sources.core import embeddings_model

            same_model = manifest.get("embedding_model") == embeddings_model(conn)
            layer = uuid.uuid4().hex[:16]
            now = utc_now()
            conn.execute("INSERT INTO pack_layers (id, title, author, licence, description, manifest, imported_at)"
                         " VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (layer, str(manifest.get("title") or path.stem)[:120], manifest.get("author"),
                          manifest.get("licence"), manifest.get("description"), json.dumps(manifest), now))
            # places: new rows in the layer; the pack's Inbox becomes a place named after the pack
            space_map: dict[str, str] = {}
            spaces = [dict(r) for r in src.execute("SELECT * FROM spaces")]
            for sp in sorted(spaces, key=lambda s: 0 if s["kind"] == "area" else 1):
                new = uuid.uuid4().hex[:16]
                space_map[sp["id"]] = new
                name = sp["name"] if sp["kind"] != "inbox" else str(manifest.get("title") or "Pack")
                kind = sp["kind"] if sp["kind"] != "inbox" else "resource"
                cols = {k: sp[k] for k in sp if k in set(_cols_main(conn, "spaces"))}
                cols.update(id=new, name=name, kind=kind, layer_id=layer, archived_at=None,
                            area_id=space_map.get(sp.get("area_id")) if sp.get("area_id") else None,
                            created_at=now, updated_at=now)
                _insert(conn, "spaces", cols)
            existing = {_hash(r["title"], r["body"]): r["id"] for r in conn.execute("SELECT id, title, body FROM notes")}
            note_map: dict[str, str] = {}
            dupes = 0
            for n in src.execute("SELECT * FROM notes"):
                n = dict(n)
                h = _hash(n["title"], n["body"])
                if h in existing:
                    note_map[n["id"]] = existing[h]
                    dupes += 1
                    continue
                new = uuid.uuid4().hex[:16]
                note_map[n["id"]] = new
                cols = {k: n[k] for k in n if k in set(_cols_main(conn, "notes"))}
                cols.update(id=new, space_id=space_map.get(n["space_id"], "inbox"), layer_id=layer, source="import")
                _insert(conn, "notes", cols)
                existing[h] = new
            links = 0
            for lk in src.execute("SELECT * FROM links"):
                a, b = note_map.get(lk["from_note"]), note_map.get(lk["to_note"])
                if a and b and a != b:
                    links += conn.execute("INSERT OR IGNORE INTO links (from_note, to_note, kind, created_by, created_at)"
                                          " VALUES (?, ?, ?, 'import', ?)", (a, b, lk["kind"], now)).rowcount
            for r in src.execute("SELECT nt.note_id, t.name FROM note_tags nt JOIN tags t ON t.id = nt.tag_id"):
                nid = note_map.get(r["note_id"])
                if nid:
                    conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (r["name"],))
                    tid = conn.execute("SELECT id FROM tags WHERE name = ?", (r["name"],)).fetchone()["id"]
                    conn.execute("INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)", (nid, tid))
            ours = {r["id"] for r in conn.execute("SELECT id FROM notes WHERE layer_id = ?", (layer,))}
            for m in src.execute("SELECT * FROM item_meta"):
                nid = note_map.get(m["note_id"])
                if nid in ours:
                    cols = {k: m[k] for k in m.keys() if k in set(_cols_main(conn, "item_meta"))}
                    cols["note_id"] = nid
                    _insert(conn, "item_meta", cols)
            vectors = 0
            if same_model:
                for e in src.execute("SELECT * FROM note_embeddings"):
                    nid = note_map.get(e["note_id"])
                    if nid in ours:
                        cols = {k: e[k] for k in e.keys() if k in set(_cols_main(conn, "note_embeddings"))}
                        cols["note_id"] = nid
                        _insert(conn, "note_embeddings", cols)
                        vectors += 1
                for r in src.execute("SELECT * FROM note_related"):
                    a, b = note_map.get(r["owner"]), note_map.get(r["other"])
                    if a in ours and b:
                        conn.execute("INSERT OR IGNORE INTO note_related (owner, other, score) VALUES (?, ?, ?)", (a, b, r["score"]))
            have_sources = {r["content_hash"] for r in conn.execute("SELECT content_hash FROM sources WHERE content_hash IS NOT NULL")}
            for s in src.execute("SELECT * FROM sources"):
                nid = note_map.get(s["note_id"]) if s["note_id"] else None
                if s["content_hash"] in have_sources or nid not in ours:
                    continue
                sid = uuid.uuid4().hex[:16]
                cols = {k: s[k] for k in s.keys() if k in set(_cols_main(conn, "sources"))}
                cols.update(id=sid, note_id=nid)
                _insert(conn, "sources", cols)
                for c in src.execute("SELECT * FROM source_chunks WHERE source_id = ? ORDER BY idx", (s["id"],)):
                    conn.execute("INSERT INTO source_chunks (source_id, idx, text, embedding, model) VALUES (?, ?, ?, ?, ?)",
                                 (sid, c["idx"], c["text"], c["embedding"] if same_model else None,
                                  c["model"] if same_model else None))
                try:  # packs made before Loop 25 have no pictures table
                    pics = list(src.execute("SELECT * FROM source_images WHERE source_id = ?", (s["id"],)))
                except sqlite3.OperationalError:
                    pics = []
                for pic in pics:
                    cols = {k: pic[k] for k in pic.keys() if k in set(_cols_main(conn, "source_images"))}
                    cols["source_id"] = sid
                    _insert(conn, "source_images", cols)
            root = db_path.parent.parent if db_path.parent.name == "data" else db_path.parent
            kept = import_originals(path, root)
            counts = {"items": len(ours), "places": len(space_map), "links": links, "vectors_copied": vectors,
                      "duplicates": dupes, "re_embed": not same_model, "originals": kept}
            conn.execute("UPDATE pack_layers SET counts = ? WHERE id = ?", (json.dumps(counts), layer))
            database.record_event(conn, {"timestamp": now, "component": "packs", "stage": "import", "status": "ok",
                                         "message": f"Pack imported: {manifest.get('title')} ({len(ours)} items, "
                                                    f"{dupes} already here)", "details": counts})
        src.close()
        return {"layer_id": layer, "title": manifest.get("title"), "counts": counts, "manifest": manifest}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _cols_main(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def _insert(conn: sqlite3.Connection, table: str, cols: dict[str, Any]) -> None:
    names = ", ".join(cols)
    conn.execute(f"INSERT INTO {table} ({names}) VALUES ({', '.join('?' * len(cols))})", list(cols.values()))


# ---------------------------------------------------------------- layers
def layers(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    out = []
    for r in conn.execute("SELECT * FROM pack_layers ORDER BY imported_at DESC"):
        d = dict(r)
        d["counts"] = json.loads(d["counts"] or "{}")
        d["manifest"] = json.loads(d["manifest"] or "{}")
        d["enabled"] = bool(d["enabled"])
        d["hidden"] = None
        d["items_now"] = conn.execute("SELECT COUNT(*) FROM notes WHERE layer_id = ?", (r["id"],)).fetchone()[0]
        out.append(d)
    return out


def _layer(conn: sqlite3.Connection, layer_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM pack_layers WHERE id = ?", (layer_id,)).fetchone()
    if row is None:
        raise brain.NotFound(f"pack layer {layer_id}")
    return row


def set_enabled(conn: sqlite3.Connection, layer_id: str, enabled: bool) -> dict[str, Any]:
    row = _layer(conn, layer_id)
    if bool(row["enabled"]) == enabled:
        return {"layer_id": layer_id, "enabled": enabled}
    now = utc_now()
    if not enabled:
        hidden = {r["id"]: r["status"] for r in conn.execute(
            "SELECT id, status FROM notes WHERE layer_id = ? AND status != 'archived'", (layer_id,))}
        conn.execute("UPDATE notes SET status = 'archived' WHERE layer_id = ?", (layer_id,))
        conn.execute("UPDATE spaces SET archived_at = ? WHERE layer_id = ?", (now, layer_id))
        conn.execute("UPDATE pack_layers SET enabled = 0, hidden = ? WHERE id = ?", (json.dumps(hidden), layer_id))
    else:
        hidden = json.loads(row["hidden"] or "{}")
        for nid, status in hidden.items():
            conn.execute("UPDATE notes SET status = ? WHERE id = ? AND layer_id = ?", (status, nid, layer_id))
        conn.execute("UPDATE spaces SET archived_at = NULL WHERE layer_id = ?", (layer_id,))
        conn.execute("UPDATE pack_layers SET enabled = 1, hidden = NULL WHERE id = ?", (layer_id,))
    return {"layer_id": layer_id, "enabled": enabled}


def merge(conn: sqlite3.Connection, layer_id: str) -> dict[str, Any]:
    """The pack's items become yours: the layer disappears, its items and places stay."""
    if not bool(_layer(conn, layer_id)["enabled"]):
        set_enabled(conn, layer_id, True)
    n = conn.execute("UPDATE notes SET layer_id = NULL WHERE layer_id = ?", (layer_id,)).rowcount
    conn.execute("UPDATE spaces SET layer_id = NULL WHERE layer_id = ?", (layer_id,))
    conn.execute("DELETE FROM pack_layers WHERE id = ?", (layer_id,))
    return {"merged": n}


def remove(conn: sqlite3.Connection, layer_id: str) -> dict[str, Any]:
    """Deletes the layer's items, sources and places (your own items are never touched)."""
    _layer(conn, layer_id)
    ids = [r["id"] for r in conn.execute("SELECT id FROM notes WHERE layer_id = ?", (layer_id,))]
    for nid in ids:
        conn.execute("DELETE FROM sources WHERE note_id = ?", (nid,))
        brain.delete_note(conn, nid)
    conn.execute("UPDATE notes SET space_id = 'inbox' WHERE space_id IN (SELECT id FROM spaces WHERE layer_id = ?)", (layer_id,))
    conn.execute("DELETE FROM spaces WHERE layer_id = ?", (layer_id,))
    conn.execute("DELETE FROM pack_layers WHERE id = ?", (layer_id,))
    return {"removed": len(ids)}
