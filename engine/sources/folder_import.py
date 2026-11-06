"""Import a folder of notes (Loop 39): an Obsidian vault, linked Markdown notes or a plain Markdown folder.

The source is detected, never put forward: the app says « Obsidian vault detected » in the preview only.
Structure is read without any model call: each .md file becomes an item (title = file name, as Obsidian
links by file name), front matter becomes fields, [[links]] become the author's links, #tags and front-matter
tags become themes, folders become places (PARA folders understood). The import is a layer, like a pack:
switch it off, merge it or remove it. Importing the same folder again adds only new or changed notes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine import brain
from engine.events import utc_now

MAX_NOTES = 20000
MAX_NOTE_BYTES = 2_000_000
EMBED_PRICE_PER_1M = 0.02       # text-embedding-3-small, USD per 1M tokens (estimate shown in the preview)
NOTE_TEXT_LIMIT = 6000          # what the meaning index reads of each note (engine/brain/meaning.py)
DOC_SUFFIXES = {".pdf", ".docx", ".txt", ".html", ".htm", ".csv", ".json"}
ATTACH_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".pdf", ".mp3", ".mp4", ".m4a", ".wav",
                   ".webm", ".ogg", ".mov", ".docx", ".xlsx", ".pptx", ".zip", ".canvas", ".excalidraw", ".base"}
TEMPLATE_DIRS = {"templates", "_templates", "template", "modeles", "modèles", "gabarits"}
HIDDEN_PROPS = {"tags", "tag", "aliases", "alias", "cssclasses", "cssclass", "publish", "permalink"}
SKIP_DIRS = {"node_modules", "__pycache__", "logseq", "_site"}

LINK_RE = re.compile(r"(!?)\[\[([^\[\]\n]{1,300})\]\]")
FENCE_RE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
TAG_RE = re.compile(r"(?:(?<=\s)|^)#([\w][\w/-]{0,48})", re.UNICODE)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")

PARA = {"projects": "project", "projets": "project", "project": "project", "projet": "project",
        "areas": "area", "area": "area", "domaines": "area", "domaine": "area", "zones": "area",
        "areas of responsibility": "area", "responsabilites": "area", "resources": "resource", "resource": "resource",
        "ressources": "resource", "ressource": "resource", "references": "resource",
        "archives": "archive", "archive": "archive"}
ITEM_TYPES = {"note", "idea", "article", "document", "reference", "quote", "list", "journal"}


class ImportError_(ValueError):
    pass


# ------------------------------------------------------------------ reading
def front_matter(text: str) -> tuple[dict[str, Any], str, bool]:
    """(properties, body, malformed). A small YAML subset: key: value, lists (inline or « - item »), quotes."""
    if not text.startswith("---"):
        return {}, text, False
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return {}, text, False
    end = next((i for i in range(1, len(lines)) if lines[i].strip() in ("---", "...")), None)
    if end is None:
        return {}, text, True
    props: dict[str, Any] = {}
    key = None
    bad = False
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_\- ]{1,60}):\s*(.*)$", raw)
        if m and not raw.startswith((" ", "\t", "-")):
            key, val = m.group(1).strip(), m.group(2).strip()
            props[key] = _value(val) if val else []
            continue
        item = re.match(r"^\s*-\s+(.*)$", raw)
        if item and key is not None:
            if not isinstance(props.get(key), list):
                props[key] = [] if props.get(key) in (None, "") else [props[key]]
            props[key].append(_value(item.group(1).strip()))
            continue
        if key is not None and raw.startswith((" ", "\t")):
            continue  # nested map: kept out
        bad = True
    body = "\n".join(lines[end + 1:]).lstrip("\n")
    return props, body, bad


def _value(v: str) -> Any:
    if v.startswith("[") and v.endswith("]"):
        return [_value(x.strip()) for x in v[1:-1].split(",") if x.strip()]
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    return v


def _as_list(v: Any) -> list[str]:
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in str(v).split(",") if x.strip()]


def parse_link(inner: str) -> tuple[str, str, str]:
    """« folder/Note#Heading|alias » -> (target, heading, alias); target keeps its folder, without « .md »."""
    inner = inner.replace("\\|", "|")  # inside a Markdown table the pipe is escaped: [[Note\|alias]]
    target, _, alias = inner.partition("|")
    target, _, heading = target.partition("#")
    target = target.strip()
    if target.lower().endswith(".md"):
        target = target[:-3]
    return target, heading.strip().lstrip("^"), alias.strip()


def _fold(s: str) -> str:
    return s.strip().replace("\\", "/").casefold()


def _clean_place(name: str) -> str:
    """« 1. Projects », « 01 - Projets » -> « Projects », « Projets »."""
    return re.sub(r"^[\s\d._\-–—)]+", "", name).strip() or name.strip()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def walk(root: Path) -> tuple[list[Path], list[Path], list[Path], int, int]:
    """(markdown files, other documents, attachments, skipped, templates) under root. Hidden folders are skipped,
    and template folders too (their notes are placeholders, not knowledge)."""
    md: list[Path] = []
    docs: list[Path] = []
    att: list[Path] = []
    skipped = 0
    templates = 0
    for here, dirs, files in os.walk(root):
        for d in dirs:
            if d.casefold() in TEMPLATE_DIRS:
                templates += sum(1 for _h, _d, fs in os.walk(Path(here) / d) for f in fs if f.lower().endswith(".md"))
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS and d.casefold() not in TEMPLATE_DIRS)
        for f in sorted(files):
            if f.startswith("."):
                continue
            p = Path(here) / f
            suf = p.suffix.lower()
            if suf in (".md", ".markdown"):
                try:
                    if p.stat().st_size > MAX_NOTE_BYTES:
                        skipped += 1
                        continue
                except OSError:
                    skipped += 1
                    continue
                md.append(p)
            elif suf in DOC_SUFFIXES:
                docs.append(p)
            elif suf in ATTACH_SUFFIXES:
                att.append(p)
    return md, docs, att, skipped, templates


def detect(root: Path, md: list[Path], docs: list[Path], linked: bool) -> str:
    if (root / ".obsidian").is_dir():
        return "obsidian"
    if (root / "logseq").is_dir() and (root / "pages").is_dir():
        return "logseq"
    if md and linked:
        return "linked"
    if md:
        return "markdown"
    return "documents" if docs else "empty"


class Note:
    def __init__(self, root: Path, path: Path):
        self.path = path
        self.rel = path.relative_to(root).as_posix()
        self.title = path.stem.strip() or "Untitled"
        raw = path.read_text(encoding="utf-8", errors="replace").lstrip("﻿").replace("\r\n", "\n")
        self.raw_hash = _hash(raw)
        self.props, body, self.malformed = front_matter(raw)
        shown = [f"{k}: {', '.join(_as_list(v)) if isinstance(v, list) else v}" for k, v in self.props.items()
                 if k.casefold() not in HIDDEN_PROPS and v not in (None, "", [])]
        if shown:  # properties stay readable, and the links they hold ([[Albums]]) become links
            body = "\n".join(shown) + ("\n\n" + body if body.strip() else "")
        self.folders = [p for p in Path(self.rel).parent.parts if p not in ("", ".")]
        bare = FENCE_RE.sub(" ", body)
        self.links = [(bool(m.group(1)), *parse_link(m.group(2))) for m in LINK_RE.finditer(bare)]
        tags = [t.lstrip("#") for t in _as_list(self.props.get("tags") or self.props.get("tag"))]
        tags += [m.group(1) for m in TAG_RE.finditer(bare)]
        self.tags = list(dict.fromkeys(t.lower() for t in tags if t and not t.replace("/", "").isdigit()))[:30]
        self.aliases = _as_list(self.props.get("aliases") or self.props.get("alias"))
        self.body = body


class Resolver:
    """Obsidian's way: a link names a file (with or without its folder); the same folder wins a tie, then the
    shortest path."""

    def __init__(self, notes: list[Note]):
        self.by_stem: dict[str, list[Note]] = {}
        self.by_path: dict[str, Note] = {}
        for n in notes:
            self.by_stem.setdefault(_fold(n.title), []).append(n)
            self.by_path[_fold(n.rel[:-3] if n.rel.lower().endswith(".md") else n.rel.rsplit(".", 1)[0])] = n
            for a in n.aliases:
                self.by_stem.setdefault(_fold(a), []).append(n)

    def find(self, target: str, source: Note) -> tuple[Note | None, bool]:
        """(note, ambiguous)."""
        t = _fold(target)
        if not t:
            return source, False  # [[#Heading]]: a link inside the same note
        if "/" in t:
            if t in self.by_path:
                return self.by_path[t], False
            ends = [n for p, n in self.by_path.items() if p.endswith("/" + t)]
            if ends:
                return ends[0], len(ends) > 1
            t = t.rsplit("/", 1)[1]
        hits = list(dict.fromkeys(self.by_stem.get(t, [])))
        if not hits:
            return None, False
        if len(hits) == 1:
            return hits[0], False
        same = [n for n in hits if n.folders == source.folders]
        best = same[0] if same else min(hits, key=lambda n: (len(n.rel), n.rel))
        return best, True


def _read(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        raise ImportError_("this folder does not exist")
    md, docs, att, skipped, templates = walk(root)
    if len(md) > MAX_NOTES:
        raise ImportError_(f"more than {MAX_NOTES} notes: import a part of this folder")
    notes: list[Note] = []
    for p in md:
        try:
            notes.append(Note(root, p))
        except OSError:
            skipped += 1
    res = Resolver(notes)
    links = resolved = ambiguous = embeds = 0
    unresolved: dict[str, int] = {}
    for n in notes:
        n.targets = []
        for is_embed, target, _h, _a in n.links:
            if Path(target).suffix.lower() in ATTACH_SUFFIXES:
                embeds += 1  # an image, a PDF, an Obsidian base: an attachment, not a note
                continue
            if "<%" in target or "{{" in target or "}}" in target:
                continue  # a template placeholder
            links += 1
            hit, amb = res.find(target, n)
            if hit is None:
                unresolved[target] = unresolved.get(target, 0) + 1
                continue
            resolved += 1
            ambiguous += int(amb)
            if hit is not n:
                n.targets.append(hit)
    linked = any(n.links for n in notes)
    tokens = sum(min(len(n.title) + len(n.body) + 2, NOTE_TEXT_LIMIT) for n in notes) // 4
    return {"root": root, "notes": notes, "docs": docs, "attachments": att, "skipped": skipped,
            "kind": detect(root, md, docs, linked), "links": links, "resolved": resolved, "ambiguous": ambiguous,
            "embeds": embeds, "unresolved": unresolved, "tokens": tokens, "templates": templates,
            "malformed": [n.rel for n in notes if n.malformed]}


# ------------------------------------------------------------- by voice
def obsidian_vaults() -> list[str]:
    """The vaults Obsidian itself lists on this PC (its obsidian.json), most recently opened first. Read only."""
    homes = [os.environ.get("APPDATA", ""), str(Path.home() / ".config"), str(Path.home() / "Library/Application Support")]
    for h in homes:
        f = Path(h) / "obsidian" / "obsidian.json" if h else None
        if f and f.is_file():
            try:
                vaults = json.loads(f.read_text(encoding="utf-8")).get("vaults") or {}
            except (OSError, ValueError):
                return []
            rows = sorted(vaults.values(), key=lambda v: -float(v.get("ts") or 0) if isinstance(v, dict) else 0)
            return [str(v["path"]) for v in rows if isinstance(v, dict) and v.get("path") and Path(str(v["path"])).is_dir()]
    return []


def spoken_path(path: str, obsidian: bool = False) -> str:
    """A folder named by voice: absolute, or under the home folder (« Documents/Notes »); « mon vault Obsidian »:
    the one Obsidian opened last. "" when unknown (the folder picker opens)."""
    p = (path or "").strip().strip("«»\"' ")
    if p:
        for cand in (Path(p).expanduser(), Path.home() / p):
            if cand.is_dir():
                return str(cand)
        return ""
    if obsidian:
        vaults = obsidian_vaults()
        return vaults[0] if vaults else ""
    return ""


# ------------------------------------------------------------------ places
def place_for(note: Note, vault: str) -> tuple[str, str]:
    """(place name, PARA kind) for a note: its top folder, understood when it is a PARA folder."""
    if not note.folders:
        return vault, "resource"
    top = _clean_place(note.folders[0])
    kind = PARA.get(_fold(top))
    if kind:
        if len(note.folders) >= 2:
            return _clean_place(note.folders[1]), kind
        return top, kind
    return top, "resource"


def _layer_for(conn: sqlite3.Connection, root: Path) -> sqlite3.Row | None:
    key = _fold(str(root))
    for r in conn.execute("SELECT id, manifest FROM pack_layers"):
        try:
            m = json.loads(r["manifest"] or "{}")
        except ValueError:
            continue
        if m.get("kind") == "folder" and _fold(str(m.get("path", ""))) == key:
            return r
    return None


def _known(conn: sqlite3.Connection, layer_id: str) -> dict[str, tuple[str, str]]:
    """{relative path: (note id, file hash)} for the notes a layer already holds."""
    out = {}
    for r in conn.execute("SELECT n.id, m.proposal FROM notes n JOIN item_meta m ON m.note_id = n.id WHERE n.layer_id = ?",
                          (layer_id,)):
        try:
            p = json.loads(r["proposal"] or "{}")
        except ValueError:
            continue
        if p.get("path"):
            out[str(p["path"])] = (r["id"], str(p.get("hash", "")))
    return out


LABELS = {"obsidian": "Obsidian vault", "logseq": "Logseq graph", "linked": "Linked notes",
          "markdown": "Markdown folder", "documents": "Folder of documents", "empty": "Nothing to import"}


def vault_root(path: str) -> Path:
    """The folder to import: the one given, or the Obsidian vault inside it when a repository or a download holds
    the vault in one subfolder (« Vault/.obsidian »)."""
    root = Path(path).expanduser()
    if root.is_dir() and not (root / ".obsidian").is_dir():
        inner = [d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".") and (d / ".obsidian").is_dir()]
        if len(inner) == 1:
            return inner[0]
    return root


def scan(conn: sqlite3.Connection, path: str, keep_folders: bool = True) -> dict[str, Any]:
    """The preview: what was detected, what would come in, and what it would cost."""
    root = vault_root(path)
    r = _read(root)
    notes: list[Note] = r["notes"]
    vault = root.name or "Vault"
    places = sorted({place_for(n, vault) for n in notes}) if keep_folders else [("Inbox", "inbox")]
    layer = _layer_for(conn, root)
    again = None
    if layer:
        known = _known(conn, layer["id"])
        new = sum(1 for n in notes if n.rel not in known)
        changed = sum(1 for n in notes if n.rel in known and known[n.rel][1] != n.raw_hash)
        again = {"layer_id": layer["id"], "new": new, "changed": changed, "same": len(notes) - new - changed}
    cost = round(r["tokens"] / 1_000_000 * EMBED_PRICE_PER_1M, 6)
    unresolved = sorted(r["unresolved"].items(), key=lambda kv: (-kv[1], kv[0].casefold()))
    return {"path": str(root), "name": vault, "kind": r["kind"], "label": LABELS[r["kind"]],
            "notes": len(notes), "links": r["links"], "resolved": r["resolved"], "ambiguous": r["ambiguous"],
            "unresolved": len(unresolved), "unresolved_list": [{"target": k, "count": v} for k, v in unresolved[:50]],
            "attachments": len(r["attachments"]), "embeds": r["embeds"], "documents": len(r["docs"]),
            "document_paths": [str(p) for p in r["docs"][:500]],
            "folders": len(places), "places": [{"name": n, "kind": k} for n, k in places[:40]],
            "tags": len({t for n in notes for t in n.tags}), "skipped": r["skipped"], "malformed": r["malformed"][:20],
            "templates": r["templates"], "inner": str(root) != str(Path(path).expanduser()),
            "tokens": r["tokens"], "cost_usd": cost, "again": again, "keep_folders": keep_folders}


# ------------------------------------------------------------------- import
def _body(n: Note, res: Resolver) -> str:
    """The note's text with links our Brain understands: [[folder/Note#Heading|alias]] -> [[Note|alias]]; front-matter
    tags kept as a #tags line (so they survive an edit)."""
    def repl(m: re.Match) -> str:
        if m.group(1):
            return m.group(0)  # ![[embed]]: kept as written (attachments come in a later loop)
        target, heading, alias = parse_link(m.group(2))
        hit, _ = res.find(target, n)
        if hit is None:
            return m.group(0)
        shown = alias or ((hit.title + " › " + heading) if heading else "")
        return f"[[{hit.title}|{shown}]]" if shown else f"[[{hit.title}]]"
    body = LINK_RE.sub(repl, n.body).rstrip()
    inline = {m.group(1).lower() for m in TAG_RE.finditer(FENCE_RE.sub(" ", n.body))}
    extra = [t for t in n.tags if t not in inline and re.fullmatch(r"[\w][\w/-]{0,48}", t)]
    if extra:
        body += ("\n\n" if body else "") + " ".join("#" + t for t in extra)
    return body


def _when(n: Note) -> str:
    for k in ("created", "date", "created_at", "creation date"):
        v = n.props.get(k)
        if isinstance(v, str) and DATE_RE.match(v):
            return v[:10] + "T00:00:00Z"
    try:
        return datetime.fromtimestamp(n.path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except OSError:
        return utc_now()


def _item_type(n: Note) -> str:
    t = str(n.props.get("type") or "").strip().casefold()
    if t in ITEM_TYPES:
        return t
    if any(_fold(f) in ("daily", "daily notes", "journal", "journals", "journal quotidien") for f in n.folders) \
            or DATE_RE.fullmatch(n.title):
        return "journal"
    return "note"


def run(conn: sqlite3.Connection, path: str, keep_folders: bool = True) -> dict[str, Any]:
    """Imports (or imports again) a folder of notes as a layer. Returns an honest report."""
    from engine.brain import archivist

    root = vault_root(path)
    r = _read(root)
    notes: list[Note] = r["notes"]
    if not notes:
        raise ImportError_("no Markdown notes in this folder")
    vault = root.name or "Vault"
    now = utc_now()
    layer = _layer_for(conn, root)
    if layer:
        layer_id = layer["id"]
        if not conn.execute("SELECT enabled FROM pack_layers WHERE id = ?", (layer_id,)).fetchone()["enabled"]:
            from engine.brain import packs
            packs.set_enabled(conn, layer_id, True)
    else:
        layer_id = uuid.uuid4().hex[:16]
        manifest = {"kind": "folder", "source": r["kind"], "path": str(root), "title": vault}
        conn.execute("INSERT INTO pack_layers (id, title, author, licence, description, manifest, imported_at)"
                     " VALUES (?, ?, NULL, NULL, ?, ?, ?)",
                     (layer_id, vault[:120], LABELS[r["kind"]], json.dumps(manifest, ensure_ascii=False), now))
    known = _known(conn, layer_id)
    spaces: dict[tuple[str, str], str] = {}
    for s in conn.execute("SELECT id, name, kind FROM spaces WHERE layer_id = ?", (layer_id,)):
        spaces[(s["name"], s["kind"])] = s["id"]

    def space_id(n: Note) -> str:
        if not keep_folders:
            brain.ensure_inbox(conn)
            return brain.INBOX_ID
        name, kind = place_for(n, vault)
        if (name, kind) not in spaces:
            sid = uuid.uuid4().hex[:16]
            pos = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM spaces").fetchone()[0]
            conn.execute("INSERT INTO spaces (id, name, kind, color, icon, position, created_at, updated_at, layer_id)"
                         " VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?)",
                         (sid, name[:120], kind, archivist._next_color(conn), pos, now, now, layer_id))
            spaces[(name, kind)] = sid
        return spaces[(name, kind)]

    res = Resolver(notes)
    ids: dict[str, str] = {}
    created = updated = same = 0
    for n in notes:
        body = _body(n, res)
        if n.rel in known:
            nid, h = known[n.rel]
            ids[n.rel] = nid
            if h == n.raw_hash:
                same += 1
                continue
            conn.execute("UPDATE notes SET title = ?, body = ?, space_id = ?, updated_at = ?, status = 'active'"
                         " WHERE id = ?", (n.title[:300], body, space_id(n), now, nid))
            updated += 1
        else:
            nid = uuid.uuid4().hex[:16]
            ids[n.rel] = nid
            kind = "journal" if _item_type(n) == "journal" else ("idea" if _item_type(n) == "idea" else "note")
            when = _when(n)
            conn.execute("INSERT INTO notes (id, space_id, title, body, kind, source, created_at, updated_at, layer_id)"
                         " VALUES (?, ?, ?, ?, ?, 'import', ?, ?, ?)",
                         (nid, space_id(n), n.title[:300], body, kind, when, when, layer_id))
            created += 1
        url = next((str(n.props[k]) for k in ("url", "source", "link") if str(n.props.get(k, "")).startswith("http")), None)
        summary = next((str(n.props[k]) for k in ("summary", "description", "abstract") if isinstance(n.props.get(k), str)), None)
        props = {k: v for k, v in n.props.items() if k not in ("tags", "tag", "aliases", "alias")}
        archivist.save_meta(conn, nid, item_type=_item_type(n), origin="import", origin_uri=url,
                            summary=summary[:2000] if summary else None, themes=n.tags[:10],
                            filed=1 if keep_folders else 0,
                            proposal={"path": n.rel, "hash": n.raw_hash, "properties": props, "aliases": n.aliases})
    # The author's links, resolved the Obsidian way (not by our title match), then the themes.
    layer_notes = [ids[n.rel] for n in notes]
    for nid in layer_notes:
        conn.execute("DELETE FROM links WHERE from_note = ? AND kind = 'wikilink'", (nid,))
        conn.execute("DELETE FROM note_tags WHERE note_id = ?", (nid,))
    for n in notes:
        for t in dict.fromkeys(x.rel for x in n.targets):
            conn.execute("INSERT OR IGNORE INTO links (from_note, to_note, kind, created_by, created_at)"
                         " VALUES (?, ?, 'wikilink', 'import', ?)", (ids[n.rel], ids[t], now))
        for tag in n.tags:
            if not re.fullmatch(r"[\w][\w/-]{0,48}", tag):
                continue
            conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
            tag_id = conn.execute("SELECT id FROM tags WHERE name = ?", (tag,)).fetchone()[0]
            conn.execute("INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)", (ids[n.rel], tag_id))
    conn.execute("DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM note_tags)")
    missing = len([p for p in known if p not in {n.rel for n in notes}])
    unresolved = sorted(r["unresolved"].items(), key=lambda kv: (-kv[1], kv[0].casefold()))
    counts = {"items": len(notes), "places": len(spaces), "links": r["resolved"], "created": created, "updated": updated}
    conn.execute("UPDATE pack_layers SET counts = ? WHERE id = ?", (json.dumps(counts), layer_id))
    try:
        from engine.brain import meaning
        meaning.poke()  # the meaning index embeds the new notes in the background
    except Exception:
        pass
    return {"layer_id": layer_id, "name": vault, "kind": r["kind"], "label": LABELS[r["kind"]],
            "notes": len(notes), "created": created, "updated": updated, "unchanged": same, "missing_in_folder": missing,
            "links": r["links"], "resolved": r["resolved"], "ambiguous": r["ambiguous"], "unresolved": len(unresolved),
            "unresolved_list": [{"target": k, "count": v} for k, v in unresolved[:50]],
            "places": len(spaces) if keep_folders else 1, "tags": len({t for n in notes for t in n.tags}),
            "attachments": len(r["attachments"]), "documents": len(r["docs"]), "malformed": r["malformed"][:20],
            "templates": r["templates"]}
