# Backlog

Ordered by priority. ✅ = done.

## Next (2026-11-13)

**The website and its film** ([plan](docs/plans/plan-site-film.md), owner, 2026-11-13): done, on `main` and online since that evening. The
front page is short: a film of the real app in the hero, the Archivist as the keeper of the door, ten tiles to the
Docs. What is left of it:
- The film has not been listened to by anyone yet (the agent cannot): the pronunciation of « G.D. », the music, the
  mix. The rights on its ElevenLabs audio depend on the account's plan: to confirm, the film being public now.
- **A first release** (loop REL-P): a tag, the package rebuilt (the last one dates from 2026-11-05), its name.
- ✅ GitHub CI (loop CI-H, 2026-11-13): green again in its five jobs. ✅ The repository's page: description,
  website link and topics (2026-11-13).
- The scripted demonstration that stood in the hero is no longer shown (its script still draws the hero's graph):
  to bring back somewhere, or to take out of the script.

Documentation: caught up on 2026-11-11 ([plan](docs/plans/plan-docs-catchup.md), DOC-E to SITE-G); the rule in
[AGENTS](AGENTS.md) and `tools/check_docs.py` keep it current. What is left of it:
- The pictures of the README's first rows and of the older Docs sections (`docs/screenshots/showcase/`,
  `public/assets/showcase/`) date from 2026-11-07: their graph bar still shows the Timeline toggle. A full
  `tools/showcase.sh` run and the copy to the site would refresh them.
- No card on the home page for the repository going public (2026-11-10): the owner's to word, if wanted.
- Two How-to guides drive a real Microsoft Edge on the owner's desktop (`browser`, `images`) and were not replayed
  on 2026-11-11: their pictures date from 2026-11-05 (`tools/howto.sh --edge browser images`, a few minutes of the
  owner's screen).

Graph views ([plan](docs/plans/plan-graph-views.md)): A to F, H and I are on `main` since 2026-11-11. What is left:
- **VIEW-G, the constellation in 3D** (meaning on the ground, time as height): waits for the owner's go.
- The assistant's words for them: open a saved view by name, « focus on X », « replay my week ».
- The play: skip the quiet stretches of time; a sound on arrivals.
- Layers (3D): place names that avoid each other; the Paper theme, where additive light shows little; the camera's
  angle in a saved view; planes per place.
- Timeline: lanes by theme and by author (needs the author in the graph's data), a free from/to date range. With
  eleven lanes (one per place) the density strip slides under the graph's bar (seen on the How-to picture of the
  graph guide, step 7, 2026-11-11).
- Meaning map: point out misfiled and lone items, keep old points still when items arrive, name the islands by theme.
- A Godot check that fails now and then (« the Captures view lists what came in, newest first »): cause not found.
- ✅ The automatic restore point before a tool's changes, and the two lines a tool's proposal leaves in an item,
  follow the interface's language (2026-11-13); the « Connect an AI tool » guide was captured again.
- A theme switch writes about two hundred font errors in the log (`_font_get_ascent: Parameter "fd" is null`,
  from `set_theme_choice`); nothing shows on screen. Seen while filming, 2026-11-13; cause not looked for.

Agreed and waiting for the owner's go, in docs/plans/:
- **Routines (Loops 41–42):** a mission on a schedule, output template, catch-up, Routines card, remembered answers.
- **Fill by identifier:** DOI (Crossref), ISBN (Open Library), BibTeX / Zotero import, a bibliography in the export.

Follow-ups noted while building (not planned yet):
- MCP: tools switched off per agent (today per server); `listChanged` through a standing stream; MCP resources and
  prompts in both directions; a one-click « undo this client's session » beside the timeline.
- Voice memos: a converter for .ogg / .opus / .aac (would need an approved tool); longer memos split over 25 MB.
- Recipes: ingredients as graph nodes (only if wanted after real use); the card's own field layout and editing.
- Graph beyond ~5,000 items: MultiMesh drawing (the layout already runs on a worker thread since 2026-11-07).
- Archivist: detect the language from the original text, not the French summary note.

Done since 2026-11-03: see [DEVLOG](DEVLOG.md) — Loops 8–40, the graph's glide and big-graph work, zip import, voice
memos, typed items and recipes, the table and grocery lists, Letter export, MCP-A → MCP-F (the Brain as an MCP
server and client); then the docs and website refresh (DOC-A → SITE-D), the themes (Terminal, Paper, Neon), the
site's living hero and « How it thinks » page, the AI notice, the repository made public (2026-11-10), and the graph
views VIEW-A → VIEW-I without G (2026-11-10, merged 2026-11-11).

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

- ✅ CI runs on every push to `main` and passes (2026-11-13).
- Godot UI tests for error states (no Python, failing pip) with fake interpreters.
- Accessibility pass on the Godot UI (keyboard focus order, font scaling).

## Decisions taken

- 2026-11-13: the film comes first (« c'est le vidéo qui va débloquer tout »); the front page is short: the film in
  the hero, the Archivist as the keeper of the door (« gardien des portes »), ten tiles to the Docs; the recipes'
  section is off it. The film's narration is the nine lines the owner agreed to, in the voice of Agent Manager's film.
- 2026-11-11: the graph views are merged into `main` after the owner tried them (« c'était très bon »); the failing
  CI comes after (« on va y revenir »).
- 2026-11-10: the repository is public.
- 2026-11-10: 3D in the graph is a showcase, a way to explore, not a daily working view; the light version first
  (layers), a sober rendering that stays in GL Compatibility.
- 2026-11-09: the `.env` is no longer versioned, and commits carry the GitHub `noreply` address (the history was
  rewritten before going public).
- 2026-11-08: the licence is MIT.
- English is the product's language and French the other choice (FR / EN), every interface text in both.
- 2026-11-02: assistant voice = OpenAI `gpt-4o-mini-tts`, voice **marin** with the Québec-accent instruction (chosen by ear from 16 samples of a
  morning briefing). Tone set by instructions per theme. ElevenLabs stays a possible premium option.
- 2026-11-02: voice-to-text = `gpt-realtime-whisper`, each user brings their own OpenAI key.

## Decisions for the owner

- VIEW-G, the constellation in 3D: build it, polish what is there first, or leave it.
- Voice model default after the benchmark (`gpt-realtime-whisper` vs `gpt-live-transcribe`).
- Whether a local Whisper fallback is ever needed (offline use, businesses that refuse cloud audio).
- Music licensing for business distribution.

## Out of scope at Loop 0 (older list)

Voice transcription, language models, embeddings, vector search and agents were all built since. Still out:
Microsoft 365 / GitHub connectors built into the app (agents reach outside tools through MCP servers), cloud sync.

## Done

- ✅ Loop 0: setup wizard, bootstrap, SQLite, local API, System Console, landing page, tests, docs.
- ✅ Loop 3: assistant (briefing spoken by marin, chat with tools and citations, auto-filing with undo, voice in
  and out, action journal).
- ✅ Loop 2: BYOK voice onboarding, OS credential store, mic capture, local WebSocket
  relay to OpenAI realtime transcription, voice notes, engine-room Voice card, benchmark tool.
- ✅ Loop 1: knowledge model (spaces, notes, links, tags, FTS5), brain screen with living graph, capture,
  briefing, search, inspector; themes; generated music, ambience and sound effects.
