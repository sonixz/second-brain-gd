# Plan: documentation, how-to and website refresh (DOC-A to SITE-D)

Asked by the owner on 2026-11-07: bring the repository's documents, the Docs and How-to pages and the website up to
date. **The website keeps its concept and its look** (« j'adore le site web en ce moment »): no feature list rolled
out on the home page; the second-brain idea stays the story. Each loop ends as usual (tests where code changes,
French where the app changes, screenshots from the showcase Brain only — never the owner's data or third-party
content —, commit on loop-32, fast-forward main, push). No GitHub Pages; the licence stays the owner's choice.

State found (2026-11-07): STATUS, DEVLOG and BACKLOG stop at Loop 7a (2026-11-03); README at 2026-11-05; the home
page at Loop 30 (2026-11-05); docs.html at Loop 40 (2026-11-06). Missing everywhere: zip import, voice memos, typed
items and recipes, the table and grocery lists, Letter export, the big-graph work, MCP in and out (catalogue, keys,
sign-in, local servers, the guard), the timeline and restore points. The showcase pictures show the old top bar.

| Loop | Content | Size | Confidence |
|---|---|---|---|
| DOC-A | Repository documents: README, STATUS, DEVLOG, BACKLOG, ROADMAP, architecture, troubleshooting, the public audit, plans moved to docs/plans | 1 | 90 % |
| DOC-B | docs.html: the missing sections, a clearer navigation, every claim checked against the code, pictures refreshed | 1 | 85 % |
| DOC-C | How-to: four new captured guides, every existing guide re-run on the current app | 1 | 75 % |
| SITE-D | The home page, same concept and design: pictures of today's app, « what works / next / parked » and « built in loops » brought up to date | ½ | 85 % |

## DOC-A — repository documents

- **README**: what the Brain is (unchanged spirit), getting it, where data lives, a short « what it does » in a few
  lines (pointing to Docs), the repository layout with today's modules (engine/mcp, sources/audio, brain/types,
  table, export_doc, timeline), tests, links.
- **STATUS**: a snapshot of today (what works, test counts on Linux and Windows, what waits on the owner), no longer
  a log of loops.
- **DEVLOG**: the loops since 7a, one dated entry each (8 → 42, 37B–D, MCP-A → F), short, from the plans and commits.
- **BACKLOG / ROADMAP**: what is next (routines 41–42, fill by identifier: DOI, ISBN, Zotero; MCP resources and
  prompts; per-agent tool lists…), what is parked.
- **docs/architecture**: the engine's modules, the data model (migrations up to 0020), the MCP server and client
  (transports, tokens, OAuth, the archivist gate, the guard), the security model (local only, secrets, approvals).
- **troubleshooting**: Edge PDF, transcription model not allowed, MCP 401 / sign-in, the WSL relay, a local server
  missing its runtime, the 4-second import limit fixed.
- **audit-before-public**: new items (MCP tokens and the relay's token file, OAuth tokens, local servers, sampling).
- **docs/plans/**: the plan-*.md files moved there with an index; links updated.

**DOC-A done 2026-11-07.** README (the MCP opening in one sentence, imports, Table, MCP in « Using it », today's
layout), STATUS rewritten as a snapshot (what works, tests, what waits on the owner), DEVLOG caught up from the
commit messages (66 entries, newest first), BACKLOG and ROADMAP refreshed, plans moved to docs/plans/ with an index,
architecture: today's overview, mcp.md, typed-items.md, intake (folders, zips, voice memos); troubleshooting (Edge
PDF, transcription model, refused audio formats, MCP key / sign-in, WSL relay, local runtimes, the import limit);
audit-before-public: MCP tokens, keys, local programs, sampling, screenshots. Every relative link checked.

## DOC-B — Docs page (public/docs.html)

- New sections: voice memos; typed items and recipes; the table and grocery lists; printing (Letter, PDF); zip
  import; « Connect AI tools (MCP in) » (Claude Code, the relay, proposals, the timeline); « MCP servers for your
  agents (MCP out) » (catalogue, keys, sign-in, local programs, the guard, budget); big graphs.
- Navigation grouped by what people do: Get started · Capture · Organise · Agents · Connect · Your data · Developers.
- Every sentence checked against the code; pictures re-captured (the new top bar with Table and the MCP lights).

## DOC-C — How-to (public/howto.html)

- Four new guides captured from the real app (tools/howto): « A voice memo becomes ideas », « From a recipe page to
  a grocery list on paper », « Connect Claude Code to your Brain », « Give an agent Microsoft Learn ».
- Every existing guide re-run on today's app (they double as end-to-end tests); the ones whose screens changed get
  new pictures.
- Real answers where they matter (recorded once, then replayed): a memo transcription and an agent answer with
  Microsoft Learn — a few cents with the owner's key, asked before.

## SITE-D — home page (public/index.html)

- Same concept, sections and design. Pictures re-captured from today's app (showcase Brain).
- « What works, what is next, what is parked »: brought up to date in its existing buckets (a few lines, not a list
  of every feature).
- « Built in loops »: the loops after 30 added to the line, each with its short card, like the existing ones.
- At most one sentence where it fits the story: the Brain also opens to your other AI tools, on your terms.
- Before merging: the changed sections shown to the owner (screenshots of the page) for a yes.
