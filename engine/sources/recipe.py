"""A recipe read without AI (Loop 37B): the schema.org Recipe a page carries (JSON-LD), turned into the recipe type's
fields. Ingredient lines are parsed into quantity, unit and name, in French and English, so quantities can be
scaled and added up for a grocery list. Nothing is guessed: a line the parser does not understand keeps its text.
"""
from __future__ import annotations

import html as htmllib
import json
import re
from fractions import Fraction
from typing import Any

_LD = re.compile(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S | re.I)
_FRACTIONS = {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3", "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8",
              "⅕": "1/5", "⅙": "1/6"}

# Units: what is written → (canonical unit, kind). Kinds: mass, volume, count (a container or a piece).
_UNITS: list[tuple[str, str, str]] = [
    (r"kilogrammes?|kg", "kg", "mass"), (r"grammes?|gr|g", "g", "mass"), (r"milligrammes?|mg", "mg", "mass"),
    (r"livres?|lbs?|pounds?", "lb", "mass"), (r"onces?|oz", "oz", "mass"),
    (r"millilitres?|ml", "ml", "volume"), (r"centilitres?|cl", "cl", "volume"), (r"décilitres?|dl", "dl", "volume"),
    (r"litres?|l", "l", "volume"),
    (r"c(?:\.|uill(?:è|e)res?)?\s*(?:à|a)\s*(?:soupe|s\.|table)|cuil\.?\s*à\s*soupe|tablespoons?|tbsps?|tbs", "tbsp", "volume"),
    (r"c(?:\.|uill(?:è|e)res?)?\s*(?:à|a)\s*(?:thé|the|café|cafe|c\.)|cuil\.?\s*à\s*(?:thé|café)|teaspoons?|tsps?", "tsp", "volume"),
    (r"tasses?|cups?", "cup", "volume"),
    (r"pincées?|pinch(?:es)?", "pinch", "count"), (r"gousses?|cloves?", "clove", "count"),
    (r"boîtes?|boites?|conserves?|cans?|tins?", "can", "count"), (r"tranches?|slices?", "slice", "count"),
    (r"bottes?|bunch(?:es)?", "bunch", "count"), (r"paquets?|packages?|packs?", "package", "count"),
    (r"sachets?|sachet|envelopes?", "sachet", "count"), (r"pots?|jars?", "jar", "count"),
    (r"bouteilles?|bottles?", "bottle", "count"), (r"brins?|sprigs?", "sprig", "count"),
    (r"feuilles?|leaves|leaf", "leaf", "count"), (r"poignées?|handfuls?", "handful", "count"),
]
UNIT_KIND = {u: k for _p, u, k in _UNITS}
# Converted to a base unit for adding up: ml for volumes, g for masses (kitchen measures, Canada: 1 cup = 250 ml).
TO_BASE = {"ml": 1.0, "cl": 10.0, "dl": 100.0, "l": 1000.0, "tsp": 5.0, "tbsp": 15.0, "cup": 250.0,
           "g": 1.0, "kg": 1000.0, "mg": 0.001, "lb": 454.0, "oz": 28.35}
_UNIT_RE = re.compile(r"^(" + "|".join(f"(?:{p})" for p, _u, _k in _UNITS) + r")(?=[\s.(),]|$)\.?", re.I)
_NUM = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)"
_QTY_RE = re.compile(rf"^({_NUM})(?:\s*(?:à|a|-|–|to|ou|or)\s*({_NUM}))?\s*", re.I)
_PAREN = re.compile(r"\(([^)]*)\)")
_OF = re.compile(r"^(?:de\s+la\s+|de\s+l['’]\s*|des\s+|du\s+|de\s+|d['’]\s*|of\s+)", re.I)


def _num(s: str) -> float:
    s = s.strip().replace(",", ".")
    if " " in s and "/" in s:
        whole, frac = s.split(None, 1)
        return float(int(whole) + Fraction(frac))
    if "/" in s:
        return float(Fraction(s))
    return float(s)


def _unit_of(text: str) -> tuple[str | None, str]:
    m = _UNIT_RE.match(text)
    if not m:
        return None, text
    word = m.group(1)
    for pattern, unit, _kind in _UNITS:
        if re.fullmatch(pattern, word, re.I):
            return unit, text[m.end():].lstrip()
    return None, text


def _measure(text: str) -> dict[str, Any] | None:
    """« 796 ml », « 30 ml », « 1 lb » → {qty, unit}; None when it is not a plain measure."""
    q = _QTY_RE.match(text.strip())
    if not q:
        return None
    unit, rest = _unit_of(text.strip()[q.end():])
    if unit is None:
        return None
    return {"qty": _num(q.group(1)), "unit": unit}


def parse_ingredient(line: str) -> dict[str, Any]:
    """« 1 boîte de 796 ml (28 oz) de tomates en dés » → qty 1, unit can, size 796 ml, name « tomates en dés »."""
    raw = re.sub(r"\s+", " ", htmllib.unescape(str(line))).strip()
    text = raw
    for k, v in _FRACTIONS.items():
        text = re.sub(rf"(\d)\s*{k}", rf"\1 {v}", text).replace(k, v)
    out: dict[str, Any] = {"raw": raw, "qty": None, "unit": None, "name": "", "note": "", "metric": None, "size": None}
    parens = _PAREN.findall(text)
    text = _PAREN.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    q = _QTY_RE.match(text)
    if q:
        out["qty"] = _num(q.group(1))
        if q.group(2):
            out["qty_max"] = _num(q.group(2))
        text = text[q.end():]
        unit, text = _unit_of(text)
        out["unit"] = unit
        if unit in ("can", "jar", "package", "bottle", "sachet"):  # « 1 boîte de 796 ml de tomates »
            m = re.match(rf"^(?:de\s+|d['’]\s*|of\s+)?({_NUM}\s*\S+)\s*", text, re.I)
            if m and _measure(m.group(1)):
                out["size"] = _measure(m.group(1))
                text = text[m.end():]
    for p in parens:  # « (30 ml) » beside « 2 c. à soupe »: the metric measure, preferred for adding up
        m = _measure(p)
        if m is None:
            continue
        if out["unit"] in ("can", "jar", "package", "bottle", "sachet") and out["size"] is None:  # « 1 (28 oz) can »
            out["size"] = m
            continue
        if out["unit"] is None and out["qty"] is not None and out["size"] is None:  # « 1 (796 ml) can » (English)
            unit, rest = _unit_of(text)
            if unit in ("can", "jar", "package", "bottle", "sachet"):
                out["unit"], out["size"], text = unit, m, rest
                continue
        if m["unit"] in ("ml", "l", "g", "kg") and out["metric"] is None:
            out["metric"] = m
    text = _OF.sub("", text.strip()).strip()
    parts = re.split(r",\s+", text, maxsplit=1)  # « 1,4 kg » keeps its comma
    name, note = parts[0], (parts[1] if len(parts) > 1 else "")
    out["name"] = name.strip().strip(".").strip()
    out["note"] = note.strip().strip(".").strip()
    return out


def base_amount(ing: dict[str, Any]) -> tuple[float, str] | None:
    """(amount, « ml » | « g ») to add up with others, from the metric measure when the page gave one."""
    for m in (ing.get("metric"), {"qty": ing.get("qty"), "unit": ing.get("unit")}):
        if m and m.get("qty") is not None and m.get("unit") in TO_BASE:
            kind = UNIT_KIND.get(m["unit"])
            return float(m["qty"]) * TO_BASE[m["unit"]], "ml" if kind == "volume" else "g"
    return None


def scale(ingredients: list[dict[str, Any]], factor: float) -> list[dict[str, Any]]:
    out = []
    for ing in ingredients:
        i = dict(ing)
        for k in ("qty", "qty_max"):
            if i.get(k) is not None:
                i[k] = round(float(i[k]) * factor, 3)
        if i.get("metric"):
            i["metric"] = {**i["metric"], "qty": round(float(i["metric"]["qty"]) * factor, 3)}
        out.append(i)
    return out


def fmt_qty(q: float | None, unit: str | None = None) -> str:
    """« 1 ½ » for cups, spoons and pieces; whole numbers for metric (« 560 ml », not « 562 ½ ml »)."""
    if q is None:
        return ""
    if unit in ("ml", "g", "cl", "dl", "mg") and q >= 10:
        return str(int(round(q / 5.0) * 5) if q >= 100 else int(round(q)))
    if unit in ("l", "kg") or (unit in ("ml", "g") and q < 10):
        return f"{q:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    whole = int(q)
    frac = q - whole
    for f, s in ((0.25, "¼"), (1 / 3, "⅓"), (0.5, "½"), (2 / 3, "⅔"), (0.75, "¾")):
        if abs(frac - f) < 0.04:
            return (f"{whole} {s}" if whole else s)
    if abs(frac) < 0.04:
        return str(whole)
    return f"{q:.2f}".rstrip("0").rstrip(".").replace(".", ",")


# ------------------------------------------------------------------ schema.org Recipe
def find_recipe(html: str) -> dict[str, Any] | None:
    """The first schema.org Recipe in the page's JSON-LD, wherever it is nested (@graph, lists, mainEntity)."""
    def walk(node: Any) -> dict[str, Any] | None:
        if isinstance(node, dict):
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if "Recipe" in types:
                return node
            for v in node.values():
                hit = walk(v)
                if hit:
                    return hit
        elif isinstance(node, list):
            for v in node:
                hit = walk(v)
                if hit:
                    return hit
        return None

    for block in _LD.findall(html or ""):
        try:
            data = json.loads(block.strip())
        except ValueError:
            try:
                data = json.loads(re.sub(r"[\x00-\x1f]", " ", block.strip()))
            except ValueError:
                continue
        hit = walk(data)
        if hit:
            return hit
    return None


def minutes(iso: Any) -> int | None:
    """ISO 8601 durations (« PT1H20M », « P0DT0H30M ») to minutes."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", str(iso or "").strip(), re.I)
    if not m or not any(m.groups()):
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    total = d * 1440 + h * 60 + mi + (1 if s >= 30 else 0)
    return total or None


def _text(v: Any) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", str(v or "")))).strip()


def _first_url(v: Any) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return str(v.get("url") or v.get("contentUrl") or "")
    if isinstance(v, list):
        urls = [_first_url(x) for x in v]
        urls = [u for u in urls if u]
        wide = [u for u in urls if re.search(r"4x3|16x9|16_9|4_3", u)]
        return (wide or urls or [""])[0]
    return ""


def _steps(v: Any, section: str = "") -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if isinstance(v, str):
        for part in re.split(r"\n+|(?<=\.)\s{2,}", v):
            if _text(part):
                out.append({"section": section, "text": _text(part)})
    elif isinstance(v, list):
        for x in v:
            out.extend(_steps(x, section))
    elif isinstance(v, dict):
        t = v.get("@type")
        if t == "HowToSection" or "itemListElement" in v:
            out.extend(_steps(v.get("itemListElement", []), _text(v.get("name")) or section))
        elif _text(v.get("text") or v.get("name")):
            out.append({"section": section, "text": _text(v.get("text") or v.get("name"))})
    return out


def _servings(v: Any) -> float | None:
    for x in (v if isinstance(v, list) else [v]):
        m = re.search(r"\d+(?:[.,]\d+)?", str(x or ""))
        if m:
            return float(m.group(0).replace(",", "."))
    return None


def _words(v: Any) -> list[str]:
    items = v if isinstance(v, list) else re.split(r"[,;]", str(v or ""))
    return [w for w in (_text(x) for x in items) if w][:20]


def to_props(r: dict[str, Any], url: str = "") -> dict[str, Any]:
    rating = r.get("aggregateRating") if isinstance(r.get("aggregateRating"), dict) else {}
    lines = [_text(x) for x in (r.get("recipeIngredient") or r.get("ingredients") or []) if _text(x)]
    props: dict[str, Any] = {
        "name": _text(r.get("name")),
        "servings": _servings(r.get("recipeYield")),
        "prep_min": minutes(r.get("prepTime")),
        "cook_min": minutes(r.get("cookTime")),
        "total_min": minutes(r.get("totalTime")),
        "rating": round(float(rating["ratingValue"]), 1) if str(rating.get("ratingValue", "")).replace(".", "", 1).isdigit() else None,
        "votes": int(float(rating.get("ratingCount") or rating.get("reviewCount") or 0)) or None,
        "category": ", ".join(_words(r.get("recipeCategory"))[:3]) or None,
        "cuisine": ", ".join(_words(r.get("recipeCuisine"))[:3]) or None,
        "keywords": _words(r.get("keywords")),
        "picture": _first_url(r.get("image")) or None,
        "source": url or str(r.get("url") or "") or None,
        "ingredients": [parse_ingredient(x) for x in lines[:80]],
        "steps": _steps(r.get("recipeInstructions"))[:80],
        "description": _text(r.get("description"))[:600] or None,
    }
    if props["total_min"] is None and (props["prep_min"] or props["cook_min"]):
        props["total_min"] = (props["prep_min"] or 0) + (props["cook_min"] or 0)
    return props


def apply(conn, note_id: str, html: str, url: str = "") -> dict[str, Any] | None:
    """When the page carries a schema.org Recipe, its item becomes a recipe: fields filled, title and text written
    from them (no AI call). Returns the props, or None for a page without a recipe."""
    from engine import brain
    from engine.brain import types

    r = find_recipe(html)
    if not r:
        return None
    props = to_props(r, url)
    if not props["ingredients"] and not props["steps"]:
        return None
    name = props.pop("name", "") or ""
    out = types.set_props(conn, note_id, "recipe", props, merge=False, rewrite_body=True)
    if name:
        brain.update_note(conn, note_id, title=name[:200])
        conn.execute("UPDATE sources SET title = ? WHERE note_id = ?", (name[:300], note_id))
    return out["props"]
