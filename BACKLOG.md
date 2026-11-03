# Backlog

Ordered by priority. ✅ = done.

## Loop 2 candidates

1. Voice capture with local Whisper (design in docs/architecture/knowledge-model.md; owner picks model size).
2. Prerequisites script: `tools/install-prereqs.ps1` (winget: Python, Godot, Git; per-user, with consent) and an
   "Install Python" button on the welcome screen.
3. Daily router agent: proposes a space and links for each Inbox thought; approve or undo from the briefing.
4. Graph: remember node positions, label collision avoidance, cluster by space, mini-map.
5. Markdown rendering in the inspector (read mode), note history.
6. Per-space ambience and accent colour; more tracks per theme.

## Platform and install

- Packaged Windows build: ship `engine/` next to the exe (export filter + `OS.get_executable_path()` lookup).
- Guided Python install: open the official installer page with the right version; maybe `winget install Python.Python.3.12` with consent.
- Offline install: optional wheelhouse folder for the locked dependencies.
- macOS test pass; Linux desktop entry.
- Godot window: remember size/position; minimum size.

## Engine

- Structured logging with rotation for `bootstrap.log` and `server.log`.
- `/system/events` filters (component, status, since) and pagination.
- Backup / export of the data folder from the console.
- Health history table (latency over time) for a small chart in the console.

## Quality

- Run CI on the next push and fix anything platform-specific it finds.
- Godot UI tests for error states (no Python, failing pip) with fake interpreters.
- Accessibility pass on the Godot UI (keyboard focus order, font scaling).

## Decisions for the owner

- Licence (MIT, Apache-2.0, AGPL-3.0…) before any public release.
- When to make the repository and the site public.
- Language of the UI (English now) and whether to add French.
- Whisper model size and whether a cloud fallback is ever allowed.
- Music licensing for business distribution.

## Out of scope until later loops

Voice transcription, language models, embeddings, vector search, agents, Microsoft 365 / GitHub connectors,
cloud sync.

## Done

- ✅ Loop 0: setup wizard, bootstrap, SQLite, local API, System Console, landing page, tests, docs.
- ✅ Loop 1: knowledge model (spaces, notes, links, tags, FTS5), brain screen with living graph, capture,
  briefing, search, inspector; themes; generated music, ambience and sound effects.
