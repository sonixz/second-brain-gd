# Backlog

Ordered by priority. ✅ = done.

## Next (2026-11-07)

Agreed and waiting for the owner's go, in docs/plans/:
- **Routines (Loops 41–42):** a mission on a schedule, output template, catch-up, Routines card, remembered answers.
- **Fill by identifier:** DOI (Crossref), ISBN (Open Library), BibTeX / Zotero import, a bibliography in the export.
- **Docs and website refresh (DOC-A → SITE-D):** under way.

Follow-ups noted while building (not planned yet):
- MCP: tools switched off per agent (today per server); `listChanged` through a standing stream; MCP resources and
  prompts in both directions; a one-click « undo this client's session » beside the timeline.
- Voice memos: a converter for .ogg / .opus / .aac (would need an approved tool); longer memos split over 25 MB.
- Recipes: ingredients as graph nodes (only if wanted after real use); the card's own field layout and editing.
- Graph beyond ~5,000 items: MultiMesh drawing (the layout already runs on a worker thread since 2026-11-07).
- Archivist: detect the language from the original text, not the French summary note.

Done since the last update of this file (2026-11-03): see [DEVLOG](DEVLOG.md) — Loops 8–40, the graph's glide and
big-graph work, zip import, voice memos, typed items and recipes, the table and grocery lists, Letter export, and
MCP-A → MCP-F (the Brain as an MCP server and client).

### Older notes (2026-11-03)

Cadence from 2026-11-03: 5b ✅ meaning memory → 6b ✅ Responses API and gpt-6-astra → 6c ✅ agent room → 7a ✅
hands-free → 7b ✅ real-time conversation.

Agent room follow-ups (6c):
- Persist sessions across restarts (`thread/resume`).
- ✅ Expose the brain to agents as an MCP server — done as MCP-A/B (2026-11-07).

Small follow-ups from 5b:
- ✅ Search box: hits by meaning shown apart.
- ✅ Related ideas: dismiss a suggestion, or turn it into a real link.
- Embed in a local model later (offline); the worker already isolates the network call.

## Loop 2 candidates (older list)

1. Voice: run the real benchmark, then test with the owner's voice and microphone; record a dozen of their own
   clips with expected text to tune `languages`, `delay` and `prompt` (project names as keywords).
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

## Decisions taken

- 2026-11-02: assistant voice = OpenAI `gpt-4o-mini-tts`, voice **marin** with the Québec-accent instruction (chosen by ear from 16 samples of a
  morning briefing). Tone set by instructions per theme. ElevenLabs stays a possible premium option.
- 2026-11-02: voice-to-text = `gpt-realtime-whisper`, each user brings their own OpenAI key.

## Decisions for the owner

- Licence (MIT, Apache-2.0, AGPL-3.0…) before any public release.
- When to make the repository and the site public.
- Language of the UI (English now) and whether to add French.
- Voice model default after the benchmark (`gpt-realtime-whisper` vs `gpt-live-transcribe`).
- Whether a local Whisper fallback is ever needed (offline use, businesses that refuse cloud audio).
- Music licensing for business distribution.

## Out of scope until later loops

Voice transcription, language models, embeddings, vector search, agents, Microsoft 365 / GitHub connectors,
cloud sync.

## Done

- ✅ Loop 0: setup wizard, bootstrap, SQLite, local API, System Console, landing page, tests, docs.
- ✅ Loop 3: assistant (briefing spoken by marin, chat with tools and citations, auto-filing with undo, voice in
  and out, action journal).
- ✅ Loop 2: BYOK voice onboarding, OS credential store, mic capture, local WebSocket
  relay to OpenAI realtime transcription, voice notes, engine-room Voice card, benchmark tool.
- ✅ Loop 1: knowledge model (spaces, notes, links, tags, FTS5), brain screen with living graph, capture,
  briefing, search, inspector; themes; generated music, ambience and sound effects.
