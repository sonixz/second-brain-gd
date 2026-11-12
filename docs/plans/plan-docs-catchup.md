# Plan: documentation catch-up after the graph views (DOC-E to SITE-G)

Asked by the owner on 2026-11-11, the day after the repository became public: « Est-ce que la documentation et
how-to sont tout à jour ? Il faudrait consigner ça quelque part pour le rendre systématique », then « peux-tu
structurer la mise à jour du repo dans la doc ». Two things came out of it:

1. **The rule**, so the gap does not come back: « Documentation is part of the work » in [AGENTS.md](../../AGENTS.md).
   A loop is done only when its documentation is, or when what is left is written in BACKLOG.md with the reason.
2. **This plan**, to catch up what the rule would have asked for since 2026-11-07. It follows on from
   [plan-docs-site.md](plan-docs-site.md) (DOC-A to SITE-D), hence the letters.

State found (2026-11-11, at 4a19673): STATUS, BACKLOG, DEVLOG, the views plan and the French translations are
current. Behind: `public/docs.html` names only Zones and Timeline in the graph; `public/howto.html` has no guide for
the views and its 19 guides were last replayed on 2026-11-07 (the graph guide's step 7 has today's words and the old
picture); the home page's loops list stops at the MCP loop of 2026-11-07 and still said the repository was private;
the README names neither the views nor the three themes of 2026-11-07.

As in DOC-A to SITE-D: screenshots come from the showcase Brain only (never the owner's data or third-party
content), the website keeps its concept and its look, and every claim is checked against the code.

| Loop | Content | Size |
|---|---|---|
| DOC-E | Docs and repository documents: the graph section of `docs.html` (the views, saved views, time and the play) with pictures of today's app; README; architecture | ½ |
| DOC-F | How-to: two new captured guides (the views; time and the 3D layers), every existing guide replayed on today's app | 1 |
| SITE-G | Home page: the loops list brought up to 2026-11-10 (the themes, the graph views), the sentences that stopped being true | ½ |

## DOC-E — Docs and repository documents

- **`public/docs.html`, « The graph »:** a « Views » part (the picker and what each view is for: Zones, Timeline
  and its lanes, Focus, Meaning map, Layers (3D)), « Saved views », « Time » (the cursor, the play, its speed),
  with pictures taken by `tools/views_shots.gd`. The opening line no longer says the repository is private.
- **README:** the views in « Using it », the seven themes, a picture of a view.
- **Architecture:** where the views live (the layouts of `graph_view.gd`, `graph_layers.gd`, the engine's
  `/brain/meaning/map`), in the document that already describes the graph.

**DOC-E done 2026-11-11.** `docs.html#graph-views`, `#graph-saved-views`, `#graph-time`: a table of the five views
(what you see, what it is good for), what each needs (the Meaning map needs the meaning memory), saved views, the
Time bar and the play, five pictures (`public/assets/showcase/views-*.webp`), links to the two guides; by voice
only the timeline and the zones exist, and the page says so. README: a « Views » line, a row of three pictures
(`docs/screenshots/views/`), the seven themes. `docs/architecture/overview.md`: « The graph's views ». The section
was looked at rendered in a browser. Left: the older pictures (see BACKLOG).

## DOC-F — How-to

- **« See your Brain from another angle »:** the picker, the timeline and its lanes, the focus view and a walk to a
  neighbour, the meaning map, a view saved under a name.
- **« Watch your Brain grow »:** the Time bar, the brain as it was on a day, the play and its speed, the layers in
  3D, the flight to an item.
- **Every guide replayed** (`tools/howto.sh`): the pictures show today's filter bar, and a step that no longer
  works fails the run. The guides that drive a real Edge keep their pictures (they take the owner's screen).

**DOC-F done 2026-11-11.** Guides `views` and `time` (five steps each, « App only »), placed after the graph guide.
Full replay: 19 guides of 21 ran, every step captured (first-minutes, panels, scanned-pdf, graph, views, time,
packs, vault, backups, connect, web, organise, sparring, own-agent, mission, voice-memo, recipe-grocery, ai-tool,
mcp-servers); 81 pictures of the site changed. Not replayed: `browser` and `images`, which drive a real Edge on the
owner's desktop (`tools/howto.sh --edge`); their pictures date from 2026-11-05. The page is rebuilt from
`guides.py`: 21 guides.

## SITE-G — Home page

- Two cards in « built in loops »: the themes (2026-11-07) and the graph views (2026-11-10), each with its
  thumbnail and its button on the loops line; the instant approvals of 2026-11-08 join the MCP card's text.
- « Open source »: the repository is public, under the MIT licence, with a link to the AI notice.

**SITE-G done 2026-11-11.** Cards `loop-views` (Graph) and `loop-themes` (Foundations) with their thumbnails
(`public/assets/journal/`) and their dots on the line; the approvals sentence in the MCP card, whose link pointed to
a guide renamed since (`howto.html#ai-tool`); « What works »: the views, twenty-one guides; « Alive »: seven themes;
« Show all 50 loops ». `tools/theme_shots.gd` takes the themes' pictures. The cards were looked at rendered in a
browser. Not done, on purpose: a card for the repository going public (no loop behind it; the owner's to word).

## The check that came with it

`tools/check_docs.py` (run by `tests/python/test_docs.py`): internal links, pictures and anchors of `public/*.html`,
relative links of the documents, every guide of `guides.py` present on the How-to page, the loop count of the home
page. It counts only files git knows or would add, so a picture that exists only on one disk does not pass.

The list of AGENTS.md, applied to itself: a « Done » note here, an entry in DEVLOG.md, STATUS.md and BACKLOG.md,
tests where code changed (`tools/test.sh`; the How-to run is its own test), a commit on `main`. One push at the end.
