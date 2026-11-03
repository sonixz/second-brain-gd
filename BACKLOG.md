# Backlog

Ordered by priority. ✅ = done.

## Loop 1 candidates (knowledge core)

1. Notes: `notes` table (migration 0002), CRUD API, Markdown files in `data/notes/` or SQLite-only (decide).
2. Notes UI in Godot: list, editor, quick capture.
3. Full-text search with SQLite FTS5.
4. Links between notes and a first graph view (Godot 2D, reuse the logo's graph drawing).
5. Navigation shell: sidebar with Notes / Search / Graph / System Console.

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

## Out of scope until later loops

Voice transcription, language models, embeddings, vector search, agents, Microsoft 365 / GitHub connectors,
cloud sync.

## Done

- ✅ Loop 0: setup wizard, bootstrap, SQLite, local API, System Console, landing page, tests, docs.
