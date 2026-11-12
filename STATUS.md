# Status (2026-11-11)

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

## Tests (2026-11-11, on `main` after the views were merged)

| Suite | Platform | Result |
|---|---|---|
| Python (352, 1 skipped), with the app's own environment | Windows venv run from WSL | OK |
| Godot end-to-end (287 checks) | Linux, headless | 287 passed |

One Godot check, « the Captures view lists what came in, newest first », failed in two runs out of five on
2026-11-10 and passed in this one; its cause is not found.

The system python3 in WSL has no fastapi: run the Python suite with the app's environment,
`PYTHON=/mnt/c/Users/<you>/AppData/Local/SecondBrainGD/.venv/Scripts/python.exe tools/test.sh`.

The suites were run natively on Windows at earlier loops (see DEVLOG); the app itself runs daily on the owner's
Windows PC. Real calls made while building (with the owner's key or free public servers) are noted in each loop.

## GitHub CI (2026-11-11): failing

The CI workflow (`.github/workflows/ci.yml`) has failed on each of its last twelve runs on `main` (2026-11-07 to
2026-11-11), in all five jobs: Python 3.12 and 3.13 on Ubuntu and on Windows, and the Godot headless end-to-end. The
same suites pass on the owner's computer (table above). The cause is not found: the run logs need a GitHub sign-in.
The owner, 2026-11-11: « on va y revenir ».

## Repository and branches (2026-11-11)

- Public on GitHub since 2026-11-10, under the MIT licence. Its page still has no description, no topics, no
  website link and no release.
- One branch, `main`, in one folder (`C:\git-2026\second-brain-gd`), the same as GitHub; the owner's launcher starts
  the app from here. The graph views were built on a branch (`am/second-brain-gd`, in its own folder, with a « beta »
  shortcut), tried by the owner, then merged on 2026-11-11; the branch, its folder and the shortcut were removed.

## Waiting on the owner

- Restart the app to get the graph views (close it, then the usual shortcut).
- VIEW-G, the constellation in 3D: go or not ([plan](docs/plans/plan-graph-views.md)).
- The public repository's page: description, topics, website link, a first release (owner's note, 2026-11-10). It
  needs a GitHub sign-in: the agents' key only pushes code.
- From the [audit](docs/audit-before-public.md), not confirmed done: rotate the OpenAI, OpenAI admin and ElevenLabs
  keys; GitHub's « Keep my email addresses private ».
- A first account sign-in (Notion or GitHub) for an MCP server.
