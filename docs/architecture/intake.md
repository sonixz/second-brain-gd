# One intake and the archivist (Loop 9)

Everything that enters the Brain goes through one funnel:

```
typed text, spoken thought, pasted link, dropped file, browser bookmark, clipboard
        │
        ▼
  a note in the graph (+ the original as a source: file or page, chunked and indexed)
        │
        ▼
  the archivist (engine/brain/archivist.py) ── understands, files, links, writes a receipt
        │
        ▼
  item_meta: type, language, summary, key points, entities, themes, confidence, receipt
```

## The archivist
- **Role.** Data-oriented: it receives, understands, files and links. It gives no opinions and does not
  challenge. It asks only when it cannot file the item without an answer. The chat assistant has the same
  role (`core.PERSONA`).
- **What it reads:**
  - the item, plus an excerpt of the original text for files and pages;
  - every existing place (PARA kind, a few example titles, goal, area);
  - the existing themes;
  - the 6 closest items by meaning;
  - the working context, if one is set.
- **What it decides:**
  - a title, an item type and the language;
  - a summary and key points, for long items and sources;
  - entities: people, organisations, concepts, places, dates;
  - a place: an existing one, or a **new** project, area or resource when none fits. A fresh Brain builds
    its own structure this way;
  - 1–3 themes, links, a confidence score, an optional question, and a one-line receipt.
- **When unsure.** Below the confidence threshold, the item stays in the Inbox and its question is shown.
- **Undo.** Every filing is journaled and can be undone (the toast, « annule ça », the receipt's Undo).
  Undoing also removes a place the archivist had just created if it is empty again.

**Measured with the real API** (gpt-6-sol, a fresh Brain, 2026-11-03):

| Input | Filed in | Created | Confidence | Time |
|---|---|---|---|---|
| A dark-mode idea | Resources › App de notes | yes | 0.94 | — |
| A sourdough recipe | Resources › Recettes | yes | 0.99 | 2.1 s |
| A reminder about the bread project | Projects › Projet de pain | yes | 0.88 | 2.2 s |
| A real Forte Labs article on PARA | Resources › Organisation de l'information | yes | 0.94 | 4.4 s (fetch + summary + filing) |

For the PARA article, the archivist also found « Tiago Forte » and the PARA concepts.

**Known gap.** The language of a page is guessed from its French summary note (it said `fr` for an English
article).

## Working context
« Je veux structurer le projet X » (`set_working_context`) creates the project if needed and stores it.
Later items are filed with X in mind. Saying it with no name clears it. API: `GET/PUT /brain/context`.

## Ways in
- **Capture bar.** Text or a URL. Long text keeps its body.
- **Files.** Drop them on the window, or use the file picker (PDF, Word, Markdown, text, HTML).
- **Voice.** F8 or the mic. The receipt is spoken back.
- **Clipboard.** **Ctrl+Shift+V**, or say « ajoute ça au Brain » (`ui_capture_clipboard`).
- **Browser.** The « Envoyer au Brain » bookmarklet (Captures → Send from browser) opens
  `http://127.0.0.1:<port>/capture?key=…&url=…&title=…[&text=selection]`.
  - **Why a navigation.** It is a top-level navigation, which browsers allow toward the local engine
    (they often block page scripts from calling 127.0.0.1).
  - **The capture key** is stored in the database and can be renewed. It is not the session token and
    not an API key, and it can only add a page or a selection.
  - **Selection or page.** A selection becomes a quote with its page as source. Without a selection, the
    page is fetched, summarised and indexed.
  - **The port.** If the engine had to use another port, copy the link again.

## Where you see it
- **Assistant panel.** A **receipt** card: FILED, or IN THE INBOX · WAITING, with the summary, themes
  and Undo.
- **Captures view.** Everything that came in, newest first: place, type, origin, summary, themes, the
  question it is waiting on, and the source. Click a card to open the item in the graph.

## Fresh start
- **A new install** seeds only the Inbox and a French **Getting started** guide (CODE and PARA,
  capture, finding things, voice commands). There are no preset areas.
- **Tests and screenshots** use the older demo seed through `SBGD_SEED=demo`.
