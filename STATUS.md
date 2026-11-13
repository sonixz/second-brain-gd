# Status (2026-11-13)

A snapshot of what works today. The history of each loop is in [DEVLOG](DEVLOG.md); the plans in
[docs/plans/](docs/plans/README.md); what is next in [BACKLOG](BACKLOG.md).

## What works

| Area | Today |
|---|---|
| **Intake** | Text, voice, links, files (PDF, Word, HTML, text), pictures, the page in your browser (Edge / Chrome extension), the clipboard; scanned PDFs read by local OCR; every original kept |
| **Imports** | A folder or a `.zip` of notes (Obsidian, Logseq, Notion export, Markdown) as a layer you can switch off; preview, Stop, re-import adds only what changed |
| **Voice memos** | A recording dropped on the window: transcribed (OpenAI), cut into ideas, tasks and notes linked to the memo, dated when recorded |
| **The archivist** | Files in PARA, builds the structure, links by meaning, answers with its sources; receipts and Undo |
| **The graph** | Zones per place, semantic zoom down to the text, paths between ideas, filters, folding; fluid with 1,000+ items (the layout runs on a worker thread) |
| **Graph views** | A view picker: Zones, Timeline (lanes by place, type or origin), Focus (one item and what is linked to it, on rings), Meaning map (items placed by what they mean), Layers (3D) (a showcase: the zones stacked through time); saved views (« ★ Views »); a time cursor in every view, and ▶ plays the brain growing, arrivals lit one by one |
| **Typed items** | Recipes read without AI from their page (servings, times, ingredients with quantities, steps); types agents define |
| **Table** | Items in rows and columns, sort, search, edit in place, saved views, CSV; grocery lists added up by aisle |
| **Printing** | Recipes, grocery lists and notes on Letter paper; the PDF made by Edge in the background |
| **Agents** | The Archivist, Sparring, your own agents (Agent Builder); missions in the background with a plan, a question, a draft to approve; @ mentions |
| **Voice** | Push-to-talk with the interface driven by voice; the live conversation |
| **MCP in** | Claude Code (or any MCP tool) reads the Brain over MCP, on this computer only; it proposes, the archivist decides; a timeline with restore points undoes by author |
| **MCP out** | Agents use any MCP server you connect: a hand-checked starter list, the official registry, keys, account sign-in (OAuth), local programs with approval; writes outside confirmed each time; budget; ⇠● ⇢● lights |
| **Your data** | Backups, restore, export, packs, repair, start fresh, uninstall; English or French (FR / EN) |
| **Themes** | Seven built in (Morning, Focus, Evening, Forest, Terminal, Paper, Neon), each with its own style; contrast checked for every theme |
| **Docs and How-to** | The Docs page for every feature, 21 step-by-step guides captured from the real app (19 replayed on 2026-11-11; the two that drive a real Edge date from 2026-11-05), the home page's loops up to the graph views; a check that links, pictures, guides and counts hold together (`tools/check_docs.py`, run by the tests); the rule that keeps them current is in [AGENTS](AGENTS.md) |

## Tests (2026-11-13, on `main`)

| Suite | Platform | Result |
|---|---|---|
| Python (353, 1 skipped), with the app's own environment | Windows venv run from WSL | OK |
| Godot end-to-end (287 checks) | Linux, headless | 287 passed |
| How-to guides replayed on the real app (19 of 21; two need a real Edge) | Linux, virtual display | every step captured |

One Godot check, « the Captures view lists what came in, newest first », failed in two runs out of five on
2026-11-10 and has passed in every run since (2026-11-11 and 2026-11-13, here and on the CI); its cause is not found.

The system python3 in WSL has no fastapi: run the Python suite with the app's environment,
`PYTHON=/mnt/c/Users/<you>/AppData/Local/SecondBrainGD/.venv/Scripts/python.exe tools/test.sh`.

The suites were run natively on Windows at earlier loops (see DEVLOG); the app itself runs daily on the owner's
Windows PC. Real calls made while building (with the owner's key or free public servers) are noted in each loop.

## GitHub CI (2026-11-13): passing

The CI workflow (`.github/workflows/ci.yml`) passes in its five jobs since 2026-11-13 (run 43522978578, b33cbfe):
Python 3.12 and 3.13 on Ubuntu and on Windows, and the Godot headless end-to-end (287 checks). It had failed on
every run on `main` from 2026-11-07: the workflow installed no package (no `fastapi` on the runner), and behind
that one Godot check failed on the runner, a live conversation ended as « closed » instead of « goodbye » (fixed in
the engine). Both are told in [DEVLOG](DEVLOG.md), CI-H.

## Repository and branches (2026-11-11)

- Public on GitHub since 2026-11-10, under the MIT licence. Its page has a description, the website's link and
  twenty topics since 2026-11-13; still no tag and no release.
- `main`, in one folder (`C:\git-2026\second-brain-gd`), the same as GitHub; the owner's launcher starts the app
  from here. Since 2026-11-13 a second branch, `site-film`, in its own folder beside it
  (`second-brain-gd-worktrees\site-film`): the website and the film of [the plan](docs/plans/plan-site-film.md),
  not merged and not online until the owner's go. The graph views were built on a branch (`am/second-brain-gd`, in its own folder, with a « beta »
  shortcut), tried by the owner, then merged on 2026-11-11; the branch, its folder and the shortcut were removed.

## Waiting on the owner

- [The website and film plan](docs/plans/plan-site-film.md) (CI-H to REL-P, agreed 2026-11-13) runs on a branch,
  `site-film`. At its end: the film to check by ear, then the go to merge and publish, and the first pre-release.
- VIEW-G, the constellation in 3D: go or not ([plan](docs/plans/plan-graph-views.md)).
- The rights on the ElevenLabs audio (the plan of the account): not confirmed since the audit, needed before a film
  is published.
- From the [audit](docs/audit-before-public.md), not confirmed done: rotate the OpenAI, OpenAI admin and ElevenLabs
  keys; GitHub's « Keep my email addresses private ».
- A first account sign-in (Notion or GitHub) for an MCP server.
- A few minutes of the screen for the two How-to guides that drive a real Edge
  (`tools/howto.sh --edge browser images`): their pictures date from 2026-11-05.
