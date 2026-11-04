# Originals and the document viewer (Loop 12)

## Originals
Every file and web page the Brain receives is copied to **`<data>/originals/<2 hex>/<sha256>.<ext>`**:
- the same content is kept once, whatever its name;
- moving or deleting the file on disk never loses the source;
- web pages are kept as fetched (`.html`, or `.pdf` when the link was a PDF), as they were on the day they
  were added.

`sources.original` holds the relative path, along with `original_bytes` and `pages` (migration 0009).
`originals.resolve()` only returns paths that really are inside `<data>/originals`. The System Console's
storage card has an `originals` entry.

**Before Loop 12,** only the extracted text and the file's path were stored. Sources added earlier have
no original.

## Images
PNG, JPG, WebP and GIF are inputs too. A vision model (`assistant_vision_model`, default `gpt-4o-mini`)
writes a factual description, including any visible text, and that description becomes the item's
searchable body. Without a key, the image is still kept and shown, with a placeholder description.

## Pages as images
`engine/sources/render.py` renders PDF pages with **PDFium** (`pypdfium2` 4.30.0: prebuilt wheels for
Windows and Linux, no system install, no admin rights).
- **Widths.** Pages come in fixed widths: 320, 640, 1024, 1600 and 2400 px. The viewer asks for the one
  it needs, so pages get sharper as you zoom.
- **Encoding.** PNG encoding uses the stdlib (zlib), so no Pillow is needed.
- **Cache.** Rendered pages are cached in `<data>/runtime/pages`.

| Route | Returns |
|---|---|
| `GET /sources/{id}/document` | kind (pdf, image, html, text), pages, the original's path, and `viewable` |
| `GET /sources/{id}/page/{n}?width=` | A PNG of the page. For an image, the original bytes |

## In Godot
- **The graph.** At the near and read zoom levels, a document's card shows its first page on the right.
  The page is fetched again in higher resolution as the card grows. Double-click an item to open it.
- **The viewer** (`DocumentViewer`) fills the screen:
  - wheel to zoom around the cursor (0.25×–8×);
  - drag to move;
  - ← → or PageUp/PageDown to turn pages;
  - + / − / 0 to zoom or fit;
  - Esc to close.
- **Open original** opens the kept file in the system's app (PDF reader, image viewer, browser).
- **The inspector** has *View document* and *Open original* buttons when the item has a kept original.
- **Voice.** « ouvre le document X », « page suivante / précédente / page 3 », « ouvre l'original »,
  « ferme le document ».

## Packs
**Include the original files** (an option in the export) adds `originals/…` entries to the `.brain` zip.
On import, each file must hash to its own name, or the whole import is refused. Kept files go to the local
`originals/`.

## Found along the way
The viewer was created hidden with full-rect anchors before it was in the tree, and stayed at its minimum
size (64 × 64). It now sizes itself to its parent when it opens.
