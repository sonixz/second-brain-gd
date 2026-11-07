"""The table view (Loop 37C): items as rows, their fields as columns; and the grocery list added up from the
recipes the user ticks (quantities converted and summed, grouped by aisle, nothing invented).
"""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from typing import Any

from engine import brain, database
from engine.brain import types
from engine.sources import recipe

BASE_COLUMNS = [{"key": "title", "en": "Title", "fr": "Titre", "kind": "text"},
                {"key": "place", "en": "Place", "fr": "Lieu", "kind": "text"},
                {"key": "created_at", "en": "Added", "fr": "Ajouté", "kind": "date"}]
# Fields too long for a cell: shown on the card, not in the table.
HIDDEN_KINDS = ("ingredients", "steps")
HIDDEN_KEYS = ("picture", "description", "source", "votes", "keywords", "prep_min", "cook_min", "cuisine")


def rows(conn: sqlite3.Connection, type_id: str = "", place: str = "", query: str = "", lang: str = "en",
         limit: int = 2000) -> dict[str, Any]:
    """The rows of one type (its fields as columns), or of every item (title, place, type, date)."""
    from engine.brain.archivist import place_label

    t = types.get_type(conn, type_id) if type_id else None
    if type_id and t is None:
        raise types.TypeError_(f"unknown type « {type_id} »")
    cols = list(BASE_COLUMNS)
    if t:
        cols[2:2] = [{**f} for f in t["fields"] if f["kind"] not in HIDDEN_KINDS and f["key"] not in HIDDEN_KEYS]
    else:
        cols.insert(2, {"key": "item_type", "en": "Type", "fr": "Type", "kind": "text"})
    sql = ("SELECT n.id, n.title, n.space_id, n.created_at, n.kind, p.type, p.props, m.item_type FROM notes n"
           " LEFT JOIN item_props p ON p.note_id = n.id LEFT JOIN item_meta m ON m.note_id = n.id"
           " WHERE n.status != 'archived' AND n.source != 'seed'")
    args: list[Any] = []
    if t:
        sql += " AND p.type = ?"
        args.append(t["id"])
    if place:
        sql += " AND n.space_id = ?"
        args.append(place)
    sql += " ORDER BY n.created_at DESC LIMIT ?"
    args.append(limit)
    words = [w for w in _fold(query).split() if w]
    places: dict[str, str] = {}
    out = []
    for r in conn.execute(sql, args):
        props = json.loads(r["props"] or "{}")
        if words:
            hay = _fold(r["title"] + " " + " ".join(str(v) for v in props.values() if not isinstance(v, list))
                        + " " + " ".join(i.get("name", "") for i in props.get("ingredients", [])))
            if not all(w in hay for w in words):
                continue
        if r["space_id"] not in places:
            places[r["space_id"]] = place_label(conn, r["space_id"], lang)
        row = {"id": r["id"], "title": r["title"], "place": places[r["space_id"]], "created_at": r["created_at"],
               "item_type": r["type"] or r["item_type"] or r["kind"]}
        for c in cols:
            if c["key"] in props:
                row[c["key"]] = props[c["key"]]
        if props.get("ingredients"):
            row["_ingredients"] = len(props["ingredients"])
        out.append(row)
    return {"type": t, "columns": cols, "rows": out}


# ------------------------------------------------------------------ saved views
def views(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    v = database.get_setting(conn, "table_views", [])
    return v if isinstance(v, list) else []


def save_view(conn: sqlite3.Connection, name: str, type_id: str = "", query: str = "", sort: str = "",
              desc: bool = False) -> list[dict[str, Any]]:
    name = name.strip()[:60]
    if not name:
        raise ValueError("a view needs a name")
    keep = [v for v in views(conn) if str(v.get("name", "")).casefold() != name.casefold()]
    keep.append({"name": name, "type": type_id, "query": query[:200], "sort": sort[:40], "desc": bool(desc)})
    database.set_setting(conn, "table_views", keep[-30:])
    return keep[-30:]


def delete_view(conn: sqlite3.Connection, name: str) -> list[dict[str, Any]]:
    keep = [v for v in views(conn) if str(v.get("name", "")).casefold() != name.strip().casefold()]
    database.set_setting(conn, "table_views", keep)
    return keep


# ------------------------------------------------------------------ grocery list
AISLES = ["produce", "meat", "dairy", "bakery", "pantry", "spices", "frozen", "other"]
AISLE_NAMES = {"fr": {"produce": "Fruits et légumes", "meat": "Viandes et poissons", "dairy": "Produits laitiers et œufs",
                      "bakery": "Boulangerie", "pantry": "Épicerie", "spices": "Épices et condiments",
                      "frozen": "Surgelés", "other": "Autres"},
               "en": {"produce": "Produce", "meat": "Meat and fish", "dairy": "Dairy and eggs", "bakery": "Bakery",
                      "pantry": "Pantry", "spices": "Spices and condiments", "frozen": "Frozen", "other": "Other"}}
_WORDS = {
    "frozen": "surgele surgeles congele congeles frozen",
    "spices": ("sel poivre paprika cumin safran cannelle muscade origan thym romarin laurier curcuma piment cari curry "
               "herbes moutarde ketchup mayonnaise sauce_soya soya tamari vinaigre vanille clou_de_girofle gingembre_moulu "
               "salt pepper cinnamon nutmeg oregano thyme rosemary bay turmeric chili mustard vinegar spice spices "
               "assaisonnement epices"),
    "meat": ("poulet boeuf bœuf porc veau agneau dinde bacon jambon saucisse saucisses crevette crevettes saumon morue "
             "moule moules petoncle petoncles poisson fruits_de_mer tilapia aiglefin chorizo prosciutto canard "
             "chicken beef pork veal lamb turkey ham sausage shrimp salmon cod mussels scallops fish seafood duck"),
    "dairy": ("lait creme beurre fromage mozzarella parmesan parmigiano cheddar yogourt yaourt oeuf oeufs œuf œufs "
              "ricotta feta brie gruyere emmental mascarpone cottage babeurre "
              "milk cream butter cheese yogurt egg eggs buttermilk"),
    "bakery": "pain pains baguette tortilla tortillas pita pitas brioche croissant bread buns bun naan",
    "produce": ("oignon oignons ail carotte carottes pomme_de_terre pommes_de_terre patate patates tomate tomates "
                "poivron poivrons celeri laitue epinard epinards champignon champignons courgette courgettes brocoli "
                "chou citron citrons lime limes pomme pommes banane bananes orange oranges fraise fraises bleuet bleuets "
                "avocat avocats concombre concombres echalote echalotes poireau poireaux gingembre persil coriandre "
                "basilic menthe ciboulette aneth rutabaga navet panais patate_douce haricots_verts asperge asperges "
                "chou-fleur aubergine courge citrouille radis betterave mais_frais raisin raisins mangue ananas "
                "onion onions garlic carrot carrots potato potatoes tomato tomatoes bell_pepper celery lettuce spinach "
                "mushroom mushrooms zucchini broccoli cabbage lemon lemons apple apples banana bananas avocado cucumber "
                "shallot shallots leek ginger parsley cilantro basil mint chives dill"),
    "pantry": ("farine sucre cassonade riz pates pate spaghetti spaghettis nouilles macaroni penne huile bouillon "
               "conserve tomates_en_des pate_de_tomates haricots lentilles pois_chiches sirop miel chocolat levure "
               "fecule bicarbonate poudre_a_pate avoine gruau chapelure noix amandes arachides beurre_d'arachide "
               "lait_de_coco thon sardines olives cornichons capres "
               "flour sugar rice pasta noodles oil broth stock beans lentils chickpeas syrup honey chocolate yeast "
               "cornstarch baking oats breadcrumbs nuts almonds peanuts coconut tuna"),
}
_MULTI = {a: sorted((w.replace("_", " ") for w in v.split() if "_" in w), key=len, reverse=True) for a, v in _WORDS.items()}
_SINGLE = {a: {w for w in v.split() if "_" not in w} for a, v in _WORDS.items()}


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s).casefold().replace("œ", "oe"))
    return "".join(c for c in s if not unicodedata.combining(c)).replace("’", "'")


def aisle_of(name: str, unit: str | None = None) -> str:
    n = _fold(name)
    words = re.findall(r"[\w'-]+", n)
    first = words[0] if words else ""
    if any(w in _SINGLE["frozen"] for w in words):
        return "frozen"
    if unit in ("can", "jar", "bottle", "package", "sachet"):
        return "pantry"
    for a in ("pantry", "spices", "meat", "dairy", "bakery", "produce"):  # multi-word names first (« pâte de tomates »)
        if any(re.search(rf"(^|\s){re.escape(_fold(m))}(\s|$)", n) for m in _MULTI[a]):
            return a
    for a in ("spices", "meat", "dairy", "bakery", "produce", "pantry"):  # the main word decides (« bouillon de poulet »)
        if first in _SINGLE[a]:
            return a
    for a in ("meat", "dairy", "bakery", "produce", "spices", "pantry"):
        if any(w in _SINGLE[a] for w in words):
            return a
    return "other"


_SIZES = {"petit", "petite", "petits", "petites", "moyen", "moyenne", "moyens", "moyennes", "gros", "grosse", "grosses",
          "grand", "grande", "grands", "grandes", "small", "medium", "large", "big"}


def _key(name: str) -> str:
    """« carottes moyennes » and « carotte » are the same line; sizes and plurals do not split a line."""
    words = [w for w in re.findall(r"[\w'-]+", _fold(name)) if w not in _SIZES]
    return " ".join(w[:-1] if len(w) > 3 and w[-1] in "sx" else w for w in words)


def _amount(v: float, unit: str) -> str:
    if unit == "ml" and v >= 1000:
        return f"{v / 1000:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " l"
    if unit == "g" and v >= 1000:
        return f"{v / 1000:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " kg"
    return f"{recipe.fmt_qty(v, unit)} {unit}"


def grocery(conn: sqlite3.Connection, picks: list[dict[str, Any]], lang: str = "fr") -> dict[str, Any]:
    """Adds up the ingredients of the chosen recipes (each at the servings asked), grouped by aisle."""
    fr = lang == "fr"
    lines: dict[tuple[str, str], dict[str, Any]] = {}
    recipes = []
    for pick in picks[:40]:
        p = types.get_props(conn, str(pick.get("id", "")))
        if not p or not p["props"].get("ingredients"):
            continue
        props = p["props"]
        title = brain.get_note(conn, str(pick["id"]))["title"]
        factor = 1.0
        if pick.get("servings") and props.get("servings"):
            factor = float(pick["servings"]) / float(props["servings"])
        recipes.append({"id": pick["id"], "title": title, "servings": pick.get("servings") or props.get("servings")})
        for ing in recipe.scale(props["ingredients"], factor):
            name = ing.get("name") or ing.get("raw") or ""
            if not name.strip():
                continue
            unit = ing.get("unit")
            base = recipe.base_amount(ing) if not ing.get("size") else None
            if ing.get("size"):  # a can is bought as a can: « 2 boîtes de 796 ml »
                size = ing["size"]
                kind = f"{unit}:{size['qty']:g}{size['unit']}"
            elif base:
                kind = base[1]
            elif ing.get("qty") is not None:
                kind = f"n:{unit or ''}"
            else:
                kind = "taste"
            key = (_key(name), kind)
            line = lines.setdefault(key, {"name": name, "aisle": aisle_of(name, unit), "amount": 0.0, "kind": kind,
                                          "unit": unit, "size": ing.get("size"), "recipes": []})
            if len(name) < len(line["name"]):  # the plainest wording names the line
                line["name"] = name
            if base:
                line["amount"] += base[0]
            elif ing.get("qty") is not None:
                line["amount"] += float(ing["qty"])
            if title not in line["recipes"]:
                line["recipes"].append(title)
    words = {"can": ("boîte", "boîtes", "can", "cans"), "jar": ("pot", "pots", "jar", "jars"),
             "package": ("paquet", "paquets", "package", "packages"), "bottle": ("bouteille", "bouteilles", "bottle", "bottles"),
             "sachet": ("sachet", "sachets", "packet", "packets"), "clove": ("gousse", "gousses", "clove", "cloves"),
             "pinch": ("pincée", "pincées", "pinch", "pinches"), "slice": ("tranche", "tranches", "slice", "slices"),
             "bunch": ("botte", "bottes", "bunch", "bunches"), "sprig": ("brin", "brins", "sprig", "sprigs"),
             "leaf": ("feuille", "feuilles", "leaf", "leaves"), "handful": ("poignée", "poignées", "handful", "handfuls")}
    groups: dict[str, list[dict[str, Any]]] = {a: [] for a in AISLES}
    for line in lines.values():
        k, amt = line["kind"], line["amount"]
        if k == "taste":
            shown = "au goût" if fr else "to taste"
        elif k in ("ml", "g"):
            shown = _amount(amt, k)
        else:
            unit = line["unit"]
            q = recipe.fmt_qty(amt)
            if unit in words:
                w = words[unit][(0 if amt <= 1 else 1) + (0 if fr else 2)]
                size = line.get("size") or {}
                exact = f"{size.get('qty', 0):g} {size.get('unit', '')}".replace(".", ",")  # a can's size as printed on it
                shown = f"{q} {w}" + (f" {'de' if fr else 'of'} {exact}"
                                      if line.get("size") else "")
            else:
                shown = q
        line["display"] = shown
        line["text"] = f"{line['name']} — {shown}"
        groups[line["aisle"]].append(line)
    out_groups = []
    for a in AISLES:
        items = sorted(groups[a], key=lambda x: _fold(x["name"]))
        if items:
            out_groups.append({"aisle": a, "name": AISLE_NAMES["fr" if fr else "en"][a],
                               "items": [{k: v for k, v in i.items() if k in ("name", "display", "text", "recipes", "aisle")}
                                         for i in items]})
    return {"recipes": recipes, "groups": out_groups, "count": sum(len(g["items"]) for g in out_groups)}


def save_grocery(conn: sqlite3.Connection, picks: list[dict[str, Any]], lang: str = "fr") -> dict[str, Any]:
    """The list as a note linked to its recipes, and its lines added to the « Épicerie » checklist when there is one."""
    from datetime import datetime

    from engine.brain import structure

    g = grocery(conn, picks, lang)
    if not g["count"]:
        raise ValueError("no ingredient to add up: tick recipes that have their ingredients")
    fr = lang == "fr"
    now = datetime.now()
    months = (["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."] if fr
              else ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    title = (f"Liste d'épicerie du {now.day} {months[now.month - 1]}" if fr
             else f"Grocery list, {months[now.month - 1]} {now.day}")
    lines = [("Pour : " if fr else "For: ") + ", ".join(f"[[{r['title']}]]" for r in g["recipes"])]
    for grp in g["groups"]:
        lines.append("## " + grp["name"] + "\n" + "\n".join(f"- [ ] {i['text']}" for i in grp["items"]))
    note = brain.create_note(conn, title, "\n\n".join(lines), None, kind="note", source="typed")
    checklist = None
    try:
        cl = structure.find_checklist(conn, "Épicerie" if fr else "Groceries")
    except brain.NotFound:
        try:
            cl = structure.find_checklist(conn, "Épicerie")
        except brain.NotFound:
            cl = None
    if cl:
        checklist = structure.add_items(conn, cl["id"], [i["text"] for grp in g["groups"] for i in grp["items"]], "recipes")
    return {**g, "note_id": note["id"], "title": title, "checklist": checklist["name"] if checklist else None}
