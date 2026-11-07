"""Typed items (Loop 37B): a type names the fields an item carries, and the engine keeps their values as data it can
sort, add up and export. The recipe is built in; an agent can define its own type (« Livre : auteur, année, lu »)
from its instructions. An item without a type is a plain item, as before.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from engine.events import utc_now

KINDS = ("text", "number", "minutes", "rating", "choice", "list", "ingredients", "steps", "url", "date", "checkbox")

RECIPE_FIELDS: list[dict[str, Any]] = [
    {"key": "servings", "en": "Servings", "fr": "Portions", "kind": "number"},
    {"key": "prep_min", "en": "Prep", "fr": "Préparation", "kind": "minutes"},
    {"key": "cook_min", "en": "Cooking", "fr": "Cuisson", "kind": "minutes"},
    {"key": "total_min", "en": "Total time", "fr": "Temps total", "kind": "minutes"},
    {"key": "rating", "en": "Rating", "fr": "Note", "kind": "rating"},
    {"key": "votes", "en": "Votes", "fr": "Votes", "kind": "number"},
    {"key": "category", "en": "Category", "fr": "Catégorie", "kind": "text"},
    {"key": "cuisine", "en": "Cuisine", "fr": "Cuisine", "kind": "text"},
    {"key": "keywords", "en": "Keywords", "fr": "Mots-clés", "kind": "list"},
    {"key": "description", "en": "Description", "fr": "Description", "kind": "text"},
    {"key": "tried", "en": "Tried", "fr": "Essayée", "kind": "checkbox"},
    {"key": "picture", "en": "Picture", "fr": "Image", "kind": "url"},
    {"key": "source", "en": "Source", "fr": "Source", "kind": "url"},
    {"key": "ingredients", "en": "Ingredients", "fr": "Ingrédients", "kind": "ingredients"},
    {"key": "steps", "en": "Steps", "fr": "Étapes", "kind": "steps"},
]
BUILTIN = {"recipe": {"en": "Recipe", "fr": "Recette", "fields": RECIPE_FIELDS}}


class TypeError_(ValueError):
    pass


def ensure_builtin(conn: sqlite3.Connection) -> None:
    now = utc_now()
    for tid, t in BUILTIN.items():
        conn.execute("INSERT INTO item_types (id, name_en, name_fr, fields, builtin, created_by, created_at, updated_at)"
                     " VALUES (?, ?, ?, ?, 1, 'app', ?, ?) ON CONFLICT(id) DO UPDATE SET fields = excluded.fields,"
                     " name_en = excluded.name_en, name_fr = excluded.name_fr, updated_at = excluded.updated_at"
                     " WHERE item_types.builtin = 1", (tid, t["en"], t["fr"], json.dumps(t["fields"], ensure_ascii=False),
                                                      now, now))


def _row(r: sqlite3.Row) -> dict[str, Any]:
    return {"id": r["id"], "en": r["name_en"], "fr": r["name_fr"], "fields": json.loads(r["fields"] or "[]"),
            "builtin": bool(r["builtin"]), "created_by": r["created_by"]}


def list_types(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_builtin(conn)
    out = []
    for r in conn.execute("SELECT * FROM item_types ORDER BY builtin DESC, name_en"):
        t = _row(r)
        t["count"] = conn.execute("SELECT COUNT(*) FROM item_props p JOIN notes n ON n.id = p.note_id"
                                  " WHERE p.type = ? AND n.status != 'archived'", (t["id"],)).fetchone()[0]
        out.append(t)
    return out


def get_type(conn: sqlite3.Connection, type_id: str) -> dict[str, Any] | None:
    ensure_builtin(conn)
    r = conn.execute("SELECT * FROM item_types WHERE id = ?", (type_id,)).fetchone()
    return _row(r) if r else None


def slug(name: str) -> str:
    s = re.sub(r"[^\w]+", "_", name.strip().lower()).strip("_")
    return s[:40]


def define_type(conn: sqlite3.Connection, name_en: str, name_fr: str, fields: list[dict[str, Any]],
                created_by: str = "agent", type_id: str | None = None) -> dict[str, Any]:
    """Creates or updates a type an agent (or the user) describes. Built-in types cannot be redefined."""
    tid = slug(type_id or name_en or name_fr)
    if not tid:
        raise TypeError_("a type needs a name")
    if tid in BUILTIN:
        raise TypeError_(f"« {tid} » is built in; its fields are fixed")
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for f in fields[:30]:
        key = slug(str(f.get("key") or f.get("en") or f.get("fr") or ""))
        if not key or key in seen or key in ("title", "place", "created", "type"):
            continue
        kind = str(f.get("kind", "text"))
        kind = kind if kind in KINDS else "text"
        field = {"key": key, "en": str(f.get("en") or f.get("fr") or key)[:40], "fr": str(f.get("fr") or f.get("en") or key)[:40],
                 "kind": kind}
        if kind == "choice":
            field["choices"] = [str(c)[:40] for c in (f.get("choices") or [])][:12]
        if f.get("unit"):
            field["unit"] = str(f["unit"])[:12]
        clean.append(field)
        seen.add(key)
    if not clean:
        raise TypeError_("a type needs at least one field")
    now = utc_now()
    conn.execute("INSERT INTO item_types (id, name_en, name_fr, fields, builtin, created_by, created_at, updated_at)"
                 " VALUES (?, ?, ?, ?, 0, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET name_en = excluded.name_en,"
                 " name_fr = excluded.name_fr, fields = excluded.fields, updated_at = excluded.updated_at",
                 (tid, (name_en or name_fr)[:60], (name_fr or name_en)[:60], json.dumps(clean, ensure_ascii=False),
                  created_by[:60], now, now))
    return get_type(conn, tid) or {}


def _coerce(field: dict[str, Any], v: Any) -> Any:
    kind = field["kind"]
    if v is None or v == "":
        return None
    if kind in ("number", "minutes", "rating"):
        try:
            x = float(str(v).replace(",", ".").strip())
        except ValueError:
            m = re.search(r"\d+(?:[.,]\d+)?", str(v))
            if not m:
                return None
            x = float(m.group(0).replace(",", "."))
        if kind == "rating":
            x = max(0.0, min(5.0, x))
        return int(x) if x == int(x) and kind != "rating" else round(x, 2)
    if kind == "checkbox":
        return v if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "yes", "oui", "x", "vrai")
    if kind == "list":
        items = v if isinstance(v, list) else re.split(r"[,;]", str(v))
        return [str(x).strip()[:60] for x in items if str(x).strip()][:30]
    if kind == "ingredients":
        from engine.sources.recipe import parse_ingredient
        items = v if isinstance(v, list) else str(v).splitlines()
        out = []
        for x in items[:80]:
            if isinstance(x, dict) and x.get("raw"):
                out.append(x)
            elif str(x).strip():
                out.append(parse_ingredient(str(x).strip().lstrip("-• ")))
        return out
    if kind == "steps":
        items = v if isinstance(v, list) else [s for s in str(v).splitlines() if s.strip()]
        out = []
        for x in items[:80]:
            if isinstance(x, dict) and str(x.get("text", "")).strip():
                out.append({"section": str(x.get("section", ""))[:80], "text": str(x["text"]).strip()[:2000]})
            elif str(x).strip():
                out.append({"section": "", "text": re.sub(r"^\s*\d+[.)]\s*", "", str(x)).strip()[:2000]})
        return out
    if kind == "choice":
        s = str(v).strip()[:60]
        return next((c for c in field.get("choices", []) if c.casefold() == s.casefold()), s)
    return str(v).strip()[:2000]


def clean_props(t: dict[str, Any], props: dict[str, Any]) -> dict[str, Any]:
    by_key = {f["key"]: f for f in t["fields"]}
    out = {}
    for k, v in (props or {}).items():
        f = by_key.get(k)
        if f is None:
            continue
        cv = _coerce(f, v)
        if cv is not None and cv != []:
            out[k] = cv
    return out


def set_props(conn: sqlite3.Connection, note_id: str, type_id: str, props: dict[str, Any], merge: bool = True,
              rewrite_body: bool = False) -> dict[str, Any]:
    t = get_type(conn, type_id)
    if t is None:
        raise TypeError_(f"unknown type « {type_id} »")
    clean = clean_props(t, props)
    old = get_props(conn, note_id)
    if merge and old and old["type"] == type_id:
        merged = {**old["props"], **clean}
        for k, v in (props or {}).items():  # an explicit empty value clears the field
            if (v is None or v == "") and k in merged:
                merged.pop(k)
        clean = merged
    conn.execute("INSERT INTO item_props (note_id, type, props, updated_at) VALUES (?, ?, ?, ?) ON CONFLICT(note_id)"
                 " DO UPDATE SET type = excluded.type, props = excluded.props, updated_at = excluded.updated_at",
                 (note_id, type_id, json.dumps(clean, ensure_ascii=False), utc_now()))
    conn.execute("UPDATE item_meta SET item_type = ? WHERE note_id = ?", (type_id, note_id))
    if rewrite_body:
        from engine import brain
        from engine.assistant.core import ui_language
        note = brain.get_note(conn, note_id)
        brain.update_note(conn, note_id, body=body_for(t, clean, ui_language(conn), keep=_kept_tail(note["body"])))
    return {"type": type_id, "props": clean}


def get_props(conn: sqlite3.Connection, note_id: str) -> dict[str, Any] | None:
    r = conn.execute("SELECT type, props FROM item_props WHERE note_id = ?", (note_id,)).fetchone()
    return {"type": r["type"], "props": json.loads(r["props"] or "{}")} if r else None


def _kept_tail(body: str) -> str:
    """What the user wrote under « Notes » survives a rewrite of the fields' text."""
    m = re.search(r"^(?:Mes notes|My notes)\s*:?\s*$", body or "", re.M)
    return body[m.end():].strip() if m else ""


def _num(v: Any) -> str:
    from engine.sources.recipe import fmt_qty
    return fmt_qty(float(v)) if isinstance(v, (int, float)) else str(v)


def ingredient_line(i: dict[str, Any], lang: str = "fr") -> str:
    """A parsed ingredient written back (after scaling): « 1 ½ tasse (375 ml) lait », or its original text."""
    from engine.sources.recipe import fmt_qty
    if i.get("qty") is None:
        return str(i.get("raw") or i.get("name") or "")
    words = {"fr": {"cup": "tasse", "tbsp": "c. à soupe", "tsp": "c. à thé", "can": "boîte", "clove": "gousse",
                    "pinch": "pincée", "slice": "tranche", "bunch": "botte", "package": "paquet", "sachet": "sachet",
                    "jar": "pot", "bottle": "bouteille", "sprig": "brin", "leaf": "feuille", "handful": "poignée"},
             "en": {"tbsp": "tbsp", "tsp": "tsp"}}
    unit = i.get("unit")
    shown = words.get(lang, {}).get(unit, unit) if unit else ""
    if shown and float(i["qty"]) >= 2 and unit not in ("tbsp", "tsp", "ml", "l", "g", "kg", "mg", "cl", "dl", "lb", "oz"):
        shown = {"leaf": "leaves", "pinch": "pinches", "bunch": "bunches", "feuille": "feuilles"}.get(shown, shown + "s")
    parts = [fmt_qty(i["qty"], unit) + (f"–{fmt_qty(i['qty_max'], unit)}" if i.get("qty_max") else "")]
    if shown:
        parts.append(shown)
    name = str(i.get("name", ""))

    def of(word: str) -> str:  # « 82 g de beurre », « 30 ml d'huile » (English needs nothing)
        if lang != "fr":
            return ""
        return "d’" if re.match(r"[aeiouyhàâéèêëîïôûœ]", word, re.I) else "de "
    if i.get("size"):
        size = f"{float(i['size']['qty']):g} {i['size']['unit']}".replace(".", ",")  # as printed on the can
        parts.append(f"de {size}" if lang == "fr" else size)
    if i.get("metric") and unit not in ("ml", "l", "g", "kg"):
        parts.append(f"({fmt_qty(i['metric']['qty'], i['metric']['unit'])} {i['metric']['unit']})")
    line = " ".join(parts) + " " + ((of(name) if unit else "") + name).replace("’ ", "’")
    return line + (f", {i['note']}" if i.get("note") else "")


def body_for(t: dict[str, Any], props: dict[str, Any], lang: str = "fr", keep: str = "") -> str:
    """The item's text, written from its fields: what search, meaning, the cards and the assistant read."""
    fr = lang == "fr"
    lines: list[str] = []
    if t["id"] == "recipe":
        head = []
        if props.get("servings"):
            head.append((f"Pour {_num(props['servings'])} portions" if fr else f"Serves {_num(props['servings'])}"))
        for k, lab_fr, lab_en in (("prep_min", "Préparation", "Prep"), ("cook_min", "Cuisson", "Cooking"),
                                  ("total_min", "Total", "Total")):
            if props.get(k):
                head.append(f"{lab_fr if fr else lab_en} {_minutes(props[k])}")
        if props.get("rating"):
            votes = f" ({props['votes']} votes)" if props.get("votes") else ""
            head.append(f"★ {str(props['rating']).replace('.', ',') if fr else props['rating']}{votes}")
        if head:
            lines.append(" · ".join(head))
        if props.get("description"):
            lines.append(str(props["description"]))
        if props.get("ingredients"):
            lines.append(("Ingrédients :" if fr else "Ingredients:") + "\n" +
                         "\n".join(f"- {i.get('raw') or ingredient_line(i, lang)}" for i in props["ingredients"]))
        if props.get("steps"):
            out, section = [], None
            for n, s in enumerate(props["steps"], 1):
                if s.get("section") and s["section"] != section and len({x.get("section") for x in props["steps"]}) > 1:
                    out.append(f"{s['section']} :" if fr else f"{s['section']}:")
                section = s.get("section")
                out.append(f"{n}. {s['text']}")
            lines.append(("Étapes :" if fr else "Steps:") + "\n" + "\n".join(out))
        tail = [x for x in (props.get("category"), props.get("cuisine")) if x]
        if props.get("keywords"):
            tail.append(", ".join(props["keywords"][:8]))
        if tail:
            lines.append(" · ".join(tail))
        if props.get("source"):
            lines.append(f"Source: {props['source']}")
    else:
        for f in t["fields"]:
            v = props.get(f["key"])
            if v is None or v == []:
                continue
            label = f["fr"] if fr else f["en"]
            if f["kind"] == "list":
                v = ", ".join(v)
            elif f["kind"] == "checkbox":
                v = ("oui" if v else "non") if fr else ("yes" if v else "no")
            elif f["kind"] == "minutes":
                v = _minutes(v)
            elif f["kind"] in ("ingredients", "steps"):
                v = "\n" + "\n".join(f"- {x.get('raw') or x.get('text')}" for x in v)
            lines.append(f"{label} : {v}" if fr else f"{label}: {v}")
    if keep:
        lines.append(("Mes notes :" if fr else "My notes:") + "\n" + keep)
    return "\n\n".join(lines)


def _minutes(v: Any) -> str:
    m = int(float(v))
    return f"{m // 60} h {m % 60:02d}" if m >= 60 and m % 60 else (f"{m // 60} h" if m >= 60 else f"{m} min")
