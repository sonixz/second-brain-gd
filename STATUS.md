# Status (2026-11-07)

A snapshot of what works today. The history of each loop is in [DEVLOG](DEVLOG.md); the plans in
[docs/plans/](docs/plans/README.md); what is next in [BACKLOG](BACKLOG.md).

## What works

| Area | Today |
|---|---|
| **Intake** | Text, voice, links, files (PDF, Word, HTML, text), pictures, the page in your browser (Edge / Chrome extension), the clipboard; scanned PDFs read by local OCR; every original kept |
| **Imports** | A folder or a `.zip` of notes (Obsidian, Logseq, Notion export, Markdown) as a layer you can switch off; preview, Stop, re-import adds only what changed |
| **Voice memos** | A recording dropped on the window: transcribed (OpenAI), cut into ideas, tasks and notes linked to the memo, dated when recorded |
| **The archivist** | Files in PARA, builds the structure, links by meaning, answers with its sources; receipts and Undo |
| **The graph** | Zones per place, semantic zoom down to the text, paths between ideas, timeline, filters, folding; fluid with 1,000+ items (the layout runs on a worker thread) |
| **Typed items** | Recipes read without AI from their page (servings, times, ingredients with quantities, steps); types agents define |
| **Table** | Items in rows and columns, sort, search, edit in place, saved views, CSV; grocery lists added up by aisle |
| **Printing** | Recipes, grocery lists and notes on Letter paper; the PDF made by Edge in the background |
| **Agents** | The Archivist, Sparring, your own agents (Agent Builder); missions in the background with a plan, a question, a draft to approve; @ mentions |
| **Voice** | Push-to-talk with the interface driven by voice; the live conversation |
| **MCP in** | Claude Code (or any MCP tool) reads the Brain over MCP, on this computer only; it proposes, the archivist decides; a timeline with restore points undoes by author |
| **MCP out** | Agents use any MCP server you connect: a hand-checked starter list, the official registry, keys, account sign-in (OAuth), local programs with approval; writes outside confirmed each time; budget; ⇠● ⇢● lights |
| **Your data** | Backups, restore, export, packs, repair, start fresh, uninstall; English or French (FR / EN) |

## Tests (2026-11-07)

| Suite | Platform | Result |
|---|---|---|
| Python (346, 3 skipped without the PDF libraries) | Linux 3.12 | OK |
| Godot end-to-end (258 checks) | Linux, headless | 258 passed |

The suites were run natively on Windows at earlier loops (see DEVLOG); the app itself runs daily on the owner's
Windows PC. Real calls made while building (with the owner's key or free public servers) are noted in each loop.

## Waiting on the owner

- Restart the app to get the latest loops; try the MCP window (⇠● ⇢●).
- Connect Claude Code to the real Brain (the command from the MCP window; OK given 2026-11-07).
- A first account sign-in (Notion or GitHub) for an MCP server.
- Before going public: [docs/audit-before-public.md](docs/audit-before-public.md) (keys, `.env`, audio rights, the
  licence, visibility — the owner's decisions).
