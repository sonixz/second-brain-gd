# Typed items, the table, Letter export

## Typed items (engine/brain/types.py, migration 0015)

A type names the fields an item carries (`item_types`: fields with a key, English and French labels, a kind:
text, number, minutes, rating, choice, list, checkbox, url, date, ingredients, steps). An item of a type keeps its
values in `item_props` as JSON; an item without a row is a plain item. Values are coerced by kind; the item's text
is rewritten from its fields (what search, meaning and cards read), keeping what the user wrote under « My notes ».

- **Recipe** is built in. A page captured by the extension or a pasted link that carries a schema.org Recipe
  (JSON-LD, found anywhere in the page) becomes a recipe without AI (engine/sources/recipe.py): servings, times,
  rating, picture, steps with their sections, ingredients parsed into quantity, unit and name (French and English,
  metric equivalents, cans with their size).
- **Agents define types** from their instructions (`define_item_type`) and save typed items (`save_typed_item`);
  the assistant reads and rescales a recipe (`item_fields`, « la paella pour 6 »); mission drafts carry type + fields.

## The table and grocery lists (engine/brain/table.py)

Rows of one type (its short fields as columns) or every item; search reaches field values and ingredient names;
saved views live in the settings. The grocery list scales the ticked recipes to the servings asked, converts to ml
or g and sums (cans kept as cans), merges sizes and plurals, groups by aisle in shop order from a FR/EN word list
(unknown words go to « other »); saving makes a note linked to its recipes and fills the « Épicerie » checklist.

## Letter export (engine/brain/export_doc.py)

One Letter page per item (print CSS): a recipe with its facts, kept picture (embedded), ingredients beside the
numbered steps (rescaled when printed for other servings); a grocery list as boxes by aisle; other items as their
text. The PDF is printed by Microsoft Edge headless with a throwaway profile, no window; without Edge the HTML page
opens for Ctrl+P. Files go to `<data>/exports/`.
