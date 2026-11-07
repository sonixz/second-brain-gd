# Plan: typed items, the table view, Letter export (Loop 37 B–D)

Agreed with the owner on 2026-11-07 (« structure pour 1, 2 et 3 ; on garde le DOI et etc. pour plus tard »).
They follow the refocused Loop 37 (recipes first, grocery lists built from chosen recipes). Each part ends like
every loop: Python and Godot suites green, French for every new string, screenshots, docs, commit on loop-32,
fast-forward main, push.

| Part | Content | Size | Confidence |
|---|---|---|---|
| 37B | Typed items: properties the engine understands; the recipe type first, read without AI from a page | 1 | 80 % |
| 37C | Table view: rows and columns of items, sort, filter, edit in place, saved views, grocery totals | 1 | 85 % |
| 37D | Export: a clean Letter (8½ × 11) HTML page, and a PDF made by Edge without a window | ½ | 85 % |
| later | Fill by identifier: DOI (Crossref), ISBN (Open Library); BibTeX / Zotero import and a bibliography | 1 | 75 % |

## 37B — Typed items

- **Storage.** A table `item_props` (note_id, type, props JSON, updated_at). An item without a row is a plain item,
  as today. Types live in `item_types` (id, names EN/FR, fields, built-in or defined by an agent); a field has a
  key, labels, a kind (text, number, minutes, rating, choice, list, ingredients, steps, url, date) and a unit.
- **Built-in type: recipe.** Servings, prep / cook / total minutes, rating and votes, category, keywords, picture,
  source link, ingredients (each: quantity, unit, name, the original line), steps (sections kept).
- **Read without AI.** A page captured by the extension or a pasted link that carries a schema.org Recipe
  (JSON-LD, found anywhere in the page) becomes a recipe item: fields filled, the ingredient lines parsed (French
  and English: « 2 tasses (500 ml) de farine », « 1 boîte de 796 ml de tomates », « sel et poivre »). The summary
  call still runs for the meaning; the fields never depend on it.
- **Agents define types.** An agent's instructions can describe its own type (« fiche Livre : auteur, année, lu ou
  non »); a tool lets it create the type once and save items with their properties. Cuisin'Plan saves recipes as
  the recipe type.
- **The card.** A typed item's card shows its fields: a recipe shows its picture, servings, times, ingredients
  with quantities, steps and rating. Fields can be edited on the card.
- **By voice.** « la recette de paella, donne-moi les ingrédients » answers from the fields; « pour 6 portions »
  scales the quantities.
- Ingredients as graph nodes: not by default (twelve per recipe would flood the graph); the table view answers
  « recipes with chicken » instead. To revisit after real use.

**Done (engine) 2026-11-07.** Migration 0015 (item_types, item_props); engine/brain/types.py (built-in recipe, types
defined by agents, fields coerced by kind, the item's text written from its fields, « Mes notes » kept);
engine/sources/recipe.py (JSON-LD found anywhere, ingredient parser FR/EN with metric and can sizes, ISO
durations, scaling, metric rounded); a captured page or pasted link with a Recipe becomes a recipe item; the
archivist keeps the type; GET/POST /brain/types, POST /brain/items/{id}/props, props in /brain/items/{id};
assistant tools item_fields (« pour 6 »), set_item_fields, list_item_types, define_item_type, save_typed_item
(in the agents' capabilities); mission drafts carry type + fields. Measured on 3 saved RICARDO pages (local only):
every ingredient parsed, cans with their size. Tests: tests/python/test_types.py (8). The card's own field
layout and editing come with the table view (37C).

## 37C — The table view

- A fourth view beside the graph, the timeline and the cards: the same items in rows and columns.
- Rows: the items of a type or of the current filter. Columns: title, place, date, then the type's fields.
- Sort by a column, filter by text and by field, edit a cell in place (status, rating, servings), open the card.
- Saved views (« Recettes de moins de 30 min »), by voice too (« montre-moi en tableau mes recettes au poulet »).
- **Grocery totals.** Tick recipes, choose servings: the ingredients are added up (ml / l, g / kg, cups and
  spoons converted; « 1 boîte de 796 ml » kept as a can), grouped by aisle (produce, meat and fish, dairy, bakery,
  pantry, spices, frozen, other) and saved as a checklist item linked to its recipes. Unknown words go to
  « other »; nothing is invented.
- CSV export of the rows.

**Done 2026-11-07.** engine/brain/table.py (rows of a type with its short fields as columns, or every item;
search reaches field values and ingredient names; saved views in the settings; the grocery list: ingredients
scaled to the servings asked, converted to ml or g and summed, cans kept as cans with their printed size, sizes
and plurals merged, the plainest wording kept, aisles in shop order from a FR/EN word list, unknown → « Autres »;
saving makes a note linked to its recipes and fills the « Épicerie » checklist). GET /brain/table, POST/DELETE
/brain/table/views, POST /brain/grocery. scenes/brain/table_view.gd: the « Tableau » tab (type picker with counts,
search, saved views, sort by a column title, edit a cell in place, CSV with a BOM for Excel, tick recipes →
grocery dialog with servings per recipe). By voice: ui_open_view table with type, query or a saved view.
Tests: tests/python/test_table.py (4), Godot checks (rows, sort, grocery, save). Measured on 3 saved RICARDO
recipes: 31 lines in 5 aisles. Screenshots docs/screenshots/table-en and table-fr.

## 37D — Export

- Any item, a selection, a saved table view or a place: a clean HTML page in Letter format (8½ × 11, print CSS),
  with title, picture, sections; a recipe and a grocery list have their own layout.
- PDF: Microsoft Edge (already on Windows) prints the page to PDF headless, with a temporary profile, no window;
  the PDF opens. If Edge is missing or refuses, the HTML opens and Ctrl+P saves a PDF.
- By voice: « exporte la recette de paella en PDF », « imprime la liste d'épicerie ».

## Later — fill by identifier

DOI → Crossref, ISBN → Open Library, a page's schema.org data; BibTeX and Zotero import as « Article » items;
a bibliography in the export. Only sources whose terms allow it, as for the recipes.
