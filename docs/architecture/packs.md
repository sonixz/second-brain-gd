# Brain packs (Loop 11)

A pack is a `.brain` file: part or all of a Brain that can be shared, archived, or used to restart a
project somewhere else. Imported, it becomes a **layer** that can be switched off, merged or removed.

## The file
A zip with exactly two entries:

| Entry | Content |
|---|---|
| `manifest.json` | `format: "sbgd-brain-pack"`, `version: 1`, title, author, licence, description, `created_at`, `app_version`, `schema_version`, `embedding_model`, the selection, counts, and the `sha256` of the database |
| `data.sqlite` | A normal Second Brain database (same migrations) holding only the selected items |

**What `data.sqlite` holds:** the selected items' places (with the area above a project), the items,
links between them, themes, the archivist's records (`item_meta`), meaning vectors and related ideas, and
the sources with their indexed text.

**Never included:** settings, keys (they live in the OS credential store anyway), conversations, the action
journal, system events and costs. A test checks those tables are empty in an exported pack.

## Export
`POST /packs/preview` shows what would leave before anything is written. `POST /packs/export` writes
`<data>/exports/<title>-<date>.brain`.

| Selection | What it takes |
|---|---|
| everything | All items except the Getting started guide |
| a place | The place, plus the projects under it when it is an area |
| a theme | Items with that theme |
| a search | Items matching by meaning |
| ids | Explicit items |

By voice: « exporte le projet Atlas », « exporte tout ».

## Import
`POST /packs/import {path}`, a `.brain` dropped on the window, the Packs dialog, or « importe un pack ».

The import is defensive:
- **Only the two entries.** Anything else (for example `../escape.py`) is refused.
- **Size.** At most 512 MB.
- **Format.** The format and version must be known.
- **Integrity.** The checksum must match, and the database is opened **read-only**. A newer schema is
  refused.

What it does:
- **New ids.** Every item and place gets a new id and the layer's id. The pack's Inbox becomes a place
  named after the pack.
- **Duplicates.** Identical items (same title and body) are skipped. A source already present (same
  content hash) is not copied again.
- **Vectors.** They are reused when the embedding model matches. Otherwise the items are left for the
  meaning worker, which re-embeds them within seconds.
- **Safety.** Imported text is **data, never instructions**. The persona says so explicitly, and nothing
  in a pack is ever executed.

## Layers
| Action | Effect | By voice |
|---|---|---|
| **Off / on** | The layer's items are hidden everywhere (graph, search, meaning, feed), then restored with their exact previous status | « désactive / réactive le pack X » |
| **Merge** | The items become yours and the layer disappears | « fusionne le pack X » |
| **Remove** | Deletes the layer's items, sources and places, and never touches yours | « retire le pack X » |

In the graph, items from a pack have a dotted ring.

## Found along the way
SQLite's `lower()` only folds ASCII. A `[[Économie]]` link therefore never resolved to the note
« Économie ». Wikilinks now compare titles with Python's `casefold()`, and a regression test covers it.
