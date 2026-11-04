# Devlog

## Loop 7b follow-up — first real live conversation (2026-11-03)

- The owner enabled `gpt-realtime-2.1-mini`, but the session still said `model_not_found`. The culprit was
  the input transcription model: `gpt-realtime-whisper` is refused inside a realtime session.
  `gpt-4o-mini-transcribe` is now the default.
- Real run: a spoken « Ouvre la vue des captures » produced the tool call, the view opening, and a spoken
  answer, for $0.0033.

## Loop 11 — Brain packs: export, import, share (2026-11-03)

- **What a pack is.** A `.brain` file: a zip holding a manifest and a subset database. It carries items,
  places, links, themes, the archivist's records, meaning vectors and the sources' text. It never carries
  keys, settings, conversations, events or costs.
- **Export.** Everything, a place (with its projects), a theme, or a search. A preview shows exactly what
  leaves.
- **Import as a layer.** New ids, duplicates skipped, and vectors reused when the embedding model matches
  (otherwise re-embedded automatically). A layer can be switched off or on, merged into your Brain, or
  removed.
- **Defensive import.** Exactly two entries, a size limit, a checksum, a read-only database, and a newer
  schema refused. Imported text is data and is never obeyed.
- **Voice and gestures.**
  - « exporte le projet X / exporte tout », « importe un pack », « désactive / réactive / fusionne /
    retire le pack X ».
  - Drop a `.brain` on the window.
  - A Packs dialog in Captures.
  - In the graph, items from packs have a dotted ring.
- **Bug fixed on the way.** Wikilinks to titles starting with an accented capital never resolved
  (« [[Économie]] »): SQLite's `lower()` is ASCII-only, so titles are now compared with `casefold()`.
- **Polish.** Dialogs now use the app's theme and a fixed size; the screenshot first showed a grey,
  full-height window.
- **Tests.** Python 125 (7 pack tests, plus the accent regression) and Godot 131. Linux and native
  Windows.

## Loop 10 — The Graph first, semantic zoom (2026-11-03)

- **The Brain comes first.** The top bar shows Graph and Captures. Today, Projects and Agents are
  **modules**, hidden behind a Modules switch. A module opened by voice still shows its tab while it is
  open. Nothing was removed.
- **Semantic zoom**, from 0.15× to 40× (it was 0.35×–2.6×). The point under the cursor stays put.
  - **Far (< 0.55×).** Each place is a named cluster with its item count, and the items are points.
    Places now push each other apart more strongly, so the clusters separate.
  - **Mid.** The classic graph, with circles and titles.
  - **Near (≥ 2.2×).** Items become **cards** showing title, place, themes and summary. Each card fetches
    its item through `/brain/items/{id}` when it first appears on screen.
  - **Read (≥ 6×).** The card shows the item's **full text** at a readable size. The scale fades away.
- **Minimap**, above the music button: the whole graph with the visible area. Click it to jump.
- **Camera.** « Zoome sur X » follows the item until you pan, and centres it in the free area right of
  the panel.
- **Voice.**
  - « zoome sur X » flies into the item (`ui_zoom`, level read; places get closer).
  - « vue d'ensemble » / « recule » zoom out.
  - Keys: + / − / 0.
- **Screenshots** of the overview, cards and reading levels are in docs/screenshots/loop-10.
  - The first take showed the Today view over the graph, the reading card off-centre under the panel,
    and the minimap over the music button. All three are fixed.
- **Tests.** Python 117 and Godot 127, on Linux and native Windows.
- **Known limit.** The force layout is O(n²): fine for hundreds of items. Thousands will need a spatial
  grid or Barnes–Hut (backlog).

## Loop 9 — One intake and the archivist (2026-11-03)

- **Refocus.** The Brain is about data: capture anything, file it, link it, find it again. The AI at the
  intake is an **archivist**: data-oriented, no opinions, and it asks only what it needs to file an item.
- **`engine/brain/archivist.py` replaces the classifier.** It produces a structured record (type,
  language, summary, key points, entities, themes, confidence, receipt) in `item_meta` (migration 0007).
  - **It can create places.** The old classifier could only pick an existing space, so a fresh Brain
    would have sent everything to the Inbox.
  - **With the real API on an empty Brain,** it created « Ressources › Recettes », « Projets › Projet de
    pain » and « Ressources › Organisation de l'information », with confidence 0.88–0.99 and 2–4 s per
    item.
- **Fresh start.**
  - The default areas and demo data are gone from real installs: the Inbox plus a French Getting started
    guide only. The demo seed is still available with `SBGD_SEED=demo`.
  - The owner's data was wiped as agreed, with no backup. The setup was re-run through Godot
    `--autosetup`: all 8 steps OK in 45 s, Codex package included.
  - Running the bootstrap directly with the Store Python put `.venv` in its private folder. Godot is the
    supported way, as documented.
- **Ways in.** One gesture each:
  - the capture bar (text or links);
  - files;
  - voice, with the receipt spoken back;
  - **Ctrl+Shift+V** or « ajoute ça au Brain » for the clipboard;
  - the browser **« Envoyer au Brain »** bookmarklet: a page or a selection, with a dedicated capture key.
- **Working context.** « Je veux structurer le projet X » files the next items into X.
- **Godot.**
  - A **Captures** view, next to the Graph.
  - Receipt cards in the assistant panel.
  - The assistant greets as the archivist.
- **Tests.** Python 117 (7 archivist, plus capture and fresh-seed checks against a real engine) and Godot
  121. Linux and native Windows.

## Loop 8b — Voice fixes (2026-11-03)

- **Owner's feedback:** « il parle très lentement » and « je peux pas relire le weekly review ».
- **Pace is now controlled in the app.** The model's own pace is unreliable: the same sentence with the
  same instructions took 6.35 s, then 9.5 s. The `speed` parameter of gpt-4o-mini-tts barely changes it
  (6.55 → 6.36 s).
  - The Voice bus now plays faster and an `AudioEffectPitchShift` keeps the voice's natural height.
  - The default is 1.2×, adjustable from 0.8× to 1.6× (slider in Voice settings).
  - « parle plus vite / moins vite » changes it by voice.
  - The live conversation (F9) uses the same speed.
- **Shorter answers.**
  - Messages that arrive by voice carry `spoken: true`, and the assistant then answers in one or two
    sentences.
  - The general rule went from 2–5 sentences to 1–3.
  - The voice tones no longer ask for a slow pace.
- **Replay.**
  - Every answer, briefing and review has a **▶ Replay** button. It is free, because the audio is
    cached.
  - « relis-moi ça » reads the previous answer again (`ui_replay`), and « relis la revue » reads the last
    weekly review.
- **Tests.** Python 109 and Godot 114, on Linux and native Windows.

## Loop 7b — Live conversation (2026-11-03)

- **What it is.** Speech to speech through OpenAI Realtime, relayed by the engine at `/voice/live`.
  - The assistant keeps its persona, voice and every tool. A spoken « montre-moi ma journée » opens Today,
    the same way a typed request does.
  - Voice-driven project mode: « on travaille sur Atlas » calls `focus_project`, which loads the project's
    context and opens its card.
  - « Merci, c'est tout » ends the conversation.
- **Lives at the app level.** A theme switch rebuilds the brain screen, which would have cut the
  conversation mid-sentence. `LiveConversation` is therefore owned by the app, and a test switches the
  theme mid-conversation.
- **Echo.** Godot has no echo cancellation. With speakers, the microphone pauses while she speaks, and F8
  interrupts her: playback stops, and the engine cancels the response and truncates it to what was heard.
  With headphones (a new Voice setting), you can just talk over her.
- **Cost.** A running cost per conversation, from OpenAI's usage in each `response.done`; nothing is
  stored. Limits per conversation: $1, 20 minutes, and 3 idle minutes. The model defaults to
  `gpt-realtime-2.1-mini`, as the owner chose.
- **Blocked on model access.** The real probe found that the project has no speech-to-speech model
  (`model_not_found`), so the app explains how to enable it. Everything is tested against a scripted fake
  Realtime server that uses the same events.
- **Bugs found in the screenshots:**
  - the status pill had no size, because its parent had no full-rect offsets;
  - the pill covered the view's header, so it moved above the capture bar;
  - a missing text key blocked the live session, so the text client is now optional.
- **Tests.** Python 107 (8 live, plus the route through a real engine) and Godot 111 (5 live). Linux and
  native Windows.

## Loop 8a — Real costs on the dashboard (2026-11-03)

- The owner asked for OpenAI's real billed costs on the dashboard, with tokens and charts. They do not
  want estimates or a local copy, because OpenAI already stores it all.
  - A first approach, a local ledger that priced tokens, was dropped before commit at the owner's request.
- **A project key cannot read costs.** The call returned HTTP 403, "Missing scopes: api.usage.read". The
  app therefore takes an optional **admin key** restricted to "Usage API: Read". It is stored in the OS
  keyring, as the `openai_admin` provider.
- **What the engine reads.** `engine/billing.py` reads the Costs API (daily, by line item) and the Usage
  API (by model) live, with only a 5-minute memory cache. Errors (401, 403, 429, offline) become plain
  messages, and the key never appears in them.
- **The System Console's new "Real costs · OpenAI billing" card:**
  - totals for this month, today and the last 30 days, plus tokens this month;
  - a 30-day stacked bar chart, with hover details per day;
  - a legend with each product's amount;
  - a per-model table and the month's billed line items.
- **Chart colours.** The palette was validated with the data-viz checker on all four themes. On the
  Morning theme the contrast is only partly sufficient, so the legend and table carry the values.
- **Tests.** Python 99 (7 new billing tests, plus route checks against a real engine) and Godot 104.
- **Still to do.** Verify against the owner's real admin key, then Loop 7b.

## Loop 6c follow-up — First real Codex run (2026-11-03)

- The owner allowed running the real app-server, so the room is no longer tested only against the fake.
- **Finding 1, the bare binary is not enough.** The pinned asset was the bare `codex-app-server`. The
  handshake, API-key login and `gpt-6-sol` worked at once, but every tool call failed with "failed to
  spawn code-mode host".
  - The release also ships `codex-app-server-package-<target>.tar.gz`. It contains the app-server plus
    the code-mode host, the exec server, ripgrep, and the sandbox helpers (`bwrap` on Linux; the command
    runner and sandbox setup on Windows).
  - The manifest now pins those packages, and the installer unpacks the whole package. It unpacks to a
    staging folder before swapping it in, refuses links, absolute paths and `..`, and removes older
    versions.
  - Download size goes from 95 to 160 MB.
- **Finding 2, commands had no Decline button.** For commands, the server suggests only `accept` and
  `cancel`, and the card showed only what was suggested, so a command could only be approved.
  - `decline` works (tested), and the agent continues.
  - The engine now always offers Decline, and the fake app-server mirrors the real suggestions.
- **Results.** Install, then a turn with approvals, on Linux and native Windows, about 11 s each. Details
  and the key-leak check are in docs/architecture/agent-room.md.
- **Tests.** Python 92 (Linux and Windows) and Godot 100 (Linux and Windows).

## Loop 7a — Hands-free (2026-11-03)

- Interface tools: `ui_open_view`, `ui_open_project`, `ui_open_note`, `ui_set_theme`, `ui_set_volume`,
  `ui_start_weekly_review`, and `undo_last_action`. The engine validates ids and values, collects the
  actions per turn, and returns them as `ui_actions`. Godot runs them, with the theme always last because
  it rebuilds the screen.
- Push-to-talk: hold F8, release to send. The reply is always spoken for a voice turn. A listening pill
  shows while the mic is open. The wake word is set aside, as the owner decided.
- Real-API finding: gpt-4o sometimes said « je l'ouvre », « la revue est lancée » or « j'annule » without
  calling the tool. Fixes:
  - an explicit rule in the prompt;
  - past interface actions noted in the history;
  - `CLAIM_RE`, which gives one nudge when a reply claims an action in a turn where no tool ran.

  After the fixes, every interface command ran in the last 3 sequences.
- Destructive actions: the assistant has no delete tool, and every brain change stays undoable by voice, so
  no extra spoken confirmation was needed yet.


## Loop 6c — Agent room on by default (2026-11-03)

- The owner chose the agent room on by default. Codex ships official native binaries, so no Node.js is
  needed. A setup step downloads the pinned `codex-app-server` and verifies its SHA-256 (GitHub's
  release digest). It is resumable and never fatal: the new event status `unavailable` means an optional
  step ended without its feature.
- The engine speaks the app-server protocol (JSON-RPC over stdio) and turns it into a polled list of small
  UI events. Approvals are first-class: nothing is written until the user approves in Godot.
- Safety: the key travels over stdin only, `CODEX_HOME` sits in the data folder, and any `auth.json` is
  deleted when a session stops. Agents only run in added folders: whole drives, the home folder and the
  app's data folder are refused. Defaults are `untrusted` with `read-only`. At most 4 sessions.
- The Windows sandbox needs no admin rights in MXC (Windows 11 24H2 and later) or `unelevated` mode,
  according to OpenAI's documentation.
- Blocked: the development sandbox's classifier refused to execute the downloaded binary ("code from
  external"), so the real binary is untested. A fake app-server built from the documented protocol covers
  the flow in Python and Godot tests. The first real run waits for the owner's permission.
- Lessons: two keyword collisions again (`kind` passed into `_event`, which now takes a positional-only
  type). In GDScript, `_get` overrides `Object._get` and breaks compilation.


## Loop 6b — Responses API and gpt-6-astra (2026-11-03)

- `MODEL_CAPS` in `llm.py` replaces `startswith("gpt-6")` guesses. Astra goes through `/v1/responses`.
  Chat-style messages are translated to input items and back, so the tool loop in `core.py` is unchanged.
  The model's raw output items (reasoning included) ride along in a private `_items` key and are sent back
  verbatim. The key is stripped before any Chat Completions call.
- `store: false` with `include: reasoning.encrypted_content`, so nothing about the user's brain is kept on
  OpenAI's side between turns.
- Measured: the weekly review is clearly better on astra@low (10.6 s) than on gpt-4o (3.5 s). Medium effort
  (16.4 s) adds little. Chat stays on gpt-4o, which is faster with tools.
- `complete_with_fallback`: users bring their own key, and their project may lack gpt-6 models. A 403 or 404
  about the model falls back once per job, records a single warning event, and never hides other errors.


## Loop 5b — Meaning memory (2026-11-03)

- Migration 0006: `note_embeddings` (one normalised float32 vector per note, re-embedded when the title or
  body hash changes) and `note_related` (each note's own picks). `engine/brain/meaning.py` is stdlib only.
- A background worker in the engine embeds pending notes and passages every 30 s, and within seconds after
  any write (a middleware pokes it). It never holds SQLite during a network call: read, call, write, and it
  drops vectors for notes edited or deleted meanwhile.
- Related ideas: no fixed similarity floor works. With `text-embedding-3-small`, the same idea across French
  and English scored 0.34–0.56, while two unrelated work notes reached 0.33. Rule: a note keeps its closest
  note when it scores ≥ 0.33, plus any note ≥ 0.45. A pair is related when either note picked the other.
  `tools/meaning_bench.py`: 3 of 3 true pairs, 0 false.
- Search: meaning first (floor 0.25), then keyword hits. Keywords drop common French and English words, and
  when no note has every word, any word counts.
- Lesson: on Windows the Python tests found the owner's real key in the OS keyring, so a test engine would
  have called the real API. `tests/python/__init__.py` now uses a test keyring service and drops
  `OPENAI_API_KEY`. The Godot runner does the same. A slow shutdown (the worker held the database during the
  call) revealed it.
- Models: `gpt-6-astra` refuses `reasoning_effort: none` (lowest is `low`), and with reasoning on it refuses
  function tools in Chat Completions. Filing 10/10 in 2.7 s. Tools for it need the Responses API (Loop 6b).


## Loop 6, part 1 — Project mode (2026-11-02)

- Per-project assistant instructions are stored on the space and edited on the card. Project mode puts the
  card into the system prompt and scopes `search_notes` to the project plus resources.
- Stopped here on purpose: the agent room needs an Anthropic API key per user (claude.ai login is not allowed
  for third-party apps), and real-time voice (Loop 7) costs more. Both are the owner's call.


## Loop 5 — Sources (2026-11-02)

- Files and links become summarised reference notes, with indexed passages (migration 0005, `engine/sources/`).
  The assistant searches them with `search_sources`. Godot accepts dropped files, a native file picker, and
  links pasted in the capture bar. The engine room gained a Sources & memory card.
- Safety: web fetching refuses local and private networks. A test proves `127.0.0.1` is refused.
- Embeddings: the owner's OpenAI project refuses `text-embedding-3-small` (403). The pipeline records it and
  falls back to word search. Vectors are filled automatically once the model is enabled.
- Lesson: shared helpers belong in stdlib-only modules, because tests run without FastAPI. `search_any` moved
  out of the routes for that reason.


## Loop 4 — Structure (2026-11-02)

**Owner's critique:** "I see bubbles, but no structure, no project management." The answer is PARA plus
working loops: capture, process, triage, review, express (docs/ROADMAP.md).

- Engine: migration 0004 adds PARA cards, dated tasks and checklists, with Today, card and structure
  endpoints. The assistant gets structure tools and a weekly review. The classifier routes list items to
  checklists.
- Godot: a Graph / Today / Projects switcher, a Today view with checkboxes and inline lists, a Projects grid,
  and a project card. "@YYYY-MM-DD" adds a due date.
- Real-API findings: a multi-step request ran out of tool rounds ("could not finish"), and the next turn
  re-created a task because the history did not show past actions. Both are fixed with a forced summary and
  actions noted in the history. gpt-6 models refuse custom temperatures and need reasoning off. The
  classifier went from 5/10 (gpt-4o-mini) to 10/10 (gpt-6-sol) once it saw each space's kind, goal and area.
- Lessons: SQLite's `lower()` ignores accents (« Épicerie »). The migration splitter needed to accept
  trailing comments.


## Loop 3 — The assistant (2026-11-02)

**Owner's request:** "Open it in the morning, it summarises, it talks to me, every input gets filed, then we
work on a project." The voice is marin with a Québec accent, picked by ear from 16 samples.

- Engine `engine/assistant/`: an OpenAI client (stdlib), tools over the brain, a classification JSON
  contract, a fact-only briefing, spoken output with a tone per theme, and a journal plus undo for every
  change (migration 0003).
- Godot: an Assistant tab with bubbles, clickable `[[citations]]`, undo buttons under actions, a "Thinking…"
  indicator, a voice toggle and its own mic. A toast follows each auto-filed capture. Music ducks under the
  voice.
- Prompt tuning from real runs: tags came glued ("modenuit"), so hyphens are now asked for. Citations were
  missing, so they are now explicitly required, and they come back.
- Lessons: an edit script missed its anchor because earlier voice code sat between two lines, and the toast
  was never built. A moved GDScript block lost its indentation and filled the demo data twice. Tests now
  use a private settings file (`SBGD_SETTINGS`) instead of the user's.


## Loop 2 — Voice capture, bring your own key (2026-11-02)

**Owner's decision:** voice uses OpenAI's realtime transcription (`gpt-realtime-whisper`) with each user's own
key, entered during onboarding.

- The key never touches Godot beyond the input field. The engine verifies it for free, stores it in the OS
  credential store (tested on Windows Credential Manager) and relays audio to OpenAI.
- Godot captures the mic and converts it to 24 kHz mono PCM16. A unit test checks sample count, amplitude and
  continuity across buffers.
- Deltas stream into the capture bar. A voice note blooms on the second click.
- Lessons: a GDScript signal named `ready` collides with Node's own. A test must not read a screen after
  switching away, because the freed screen crashed Godot natively. Again, a `**details` keyword collided with a
  parameter named `status`. The ElevenLabs key lacks the text-to-speech permission, so test speech comes from
  the Windows voices.
- First real run: `gpt-realtime-whisper` refused `languages` (plural). It accepts `language`, so the default
  became auto-detect. English transcribed with 0 % errors, first words in about 1 s, final text 0.4 s after
  release. `gpt-live-transcribe` was not yet enabled for the key's project.
- The OpenAI docs disagree with themselves. The model page says `gpt-realtime-whisper`, while the
  transcription guide uses `gpt-live-transcribe`. The model is configurable, and the first real run decides.


## Loop 1 — Immersion & knowledge core (2026-11-02)

**Owner's direction:** "Godot is immersion, it needs sound." Soft, felted blue instead of green, cosy themes
like *Morning*, and above all the second brain itself, not only the system console.

### What was built

- **Knowledge model** (`engine/brain/`, migration 0002): spaces, notes, wikilinks, tags, FTS5 search, graph
  and briefing endpoints. A first run seeds four starter notes so the graph is never empty.
- **Brain screen** (`scenes/brain/`): a living graph drawn by hand. It has springs and repulsion, a pan/zoom
  camera, a birth bloom with ripple and sparks, pulses travelling along links, neighbour highlight, and
  parallax stars. Around it sit glass panels for the briefing, spaces and inspector, plus a capture bar.
- **Themes** (`SbTheme`): palettes as roles, switched at runtime. Auto picks by hour.
- **Audio** (`SbAudio`, `tools/audio.sh`, `tools/audio-prompts.txt`): prompts written for this project and
  generated through ElevenLabs. The key was moved into this repo's encrypted `.env` with dotenvx and never
  displayed. 26 files: 8 tracks (about 23 min), 4 ambience loops and 14 interface sounds. Every button gets
  hover and click sounds automatically.

### Things learned

- The ElevenLabs sound endpoint refuses effects shorter than 0.5 s.
- FastAPI 0.115 refuses a 204 route without an explicit `Response` class. The server crashed at startup and
  the bootstrap reported it correctly as "API exited during startup".
- A server whose parent app has died must not be reused. Its watchdog is about to stop it.
- A Windows CRLF copy of a migration looked "edited". Checksums now normalise line endings.
- `--quit-after` can stop Godot while the audio thread still holds a track. That is a benign "resource still
  in use". The real close path stops audio first.
- The briefing records a visit, so a theme switch (which rebuilds the screen) must reuse it.


## Loop 0 — Foundation, Bootstrap & System Console (2026-11-02)

**Goal:** clone, open in Godot, press Setup, watch a real install, land on a System Console with real values,
and never reinstall needlessly.

### What was built

- **Godot UI** (`scenes/`, `scripts/`): theme built in code, three screens, small components (animated graph logo,
  status dot, step row, info card). Screen changes fade. Python detection runs on a worker thread; the bootstrap
  runs as a separate process and Godot tails its event file every 100 ms, so the UI never blocks.
- **Bootstrap** (`engine/bootstrap.py`, `engine/installer/`): standard library only, seven checked steps,
  `install_state.json`, lock file against concurrent runs, JSON Lines events (protocol v1).
- **API** (`engine/api/`): FastAPI on 127.0.0.1, token auth on `/system/*`, psutil metrics, cached storage scan,
  parent watchdog, clean shutdown that removes its token.
- **Database** (`engine/database/`): checksummed migrations, transactional, refuses edited migrations.
- **Site** (`public/`): static, responsive, reduced-motion aware, honest status badges, real screenshots.

### Things learned the hard way

- **Microsoft Store Python silently redirects new folders under `%LOCALAPPDATA%`** to its private package folder.
  Measured: a folder created by Store Python was invisible from outside. Writes into a folder that already exists
  land in the real place. Godot now creates the data folder first; the bootstrap refuses the unsafe case.
- **TCP self-connect on Windows.** A health probe to an unused port in the ephemeral range connected to itself and
  read back its own request (`BadStatusLine: GET /health`). The probe now treats any HTTP protocol error as
  "not ready yet", and tests use ports below the ephemeral range.
- **Reusing a running API must follow the new parent.** A server left from a CLI run kept no watchdog for the new
  Godot instance. The bootstrap now restarts it when the parent changes.
- **Godot only tracks processes it started.** `OS.is_process_running()` is false for the API (a grandchild), so
  Godot checks `/health` instead.
- **Honest console.** The first screenshot after stopping the engine still said "Connected" and showed old CPU
  values. Cards now say "Last known · engine offline" and live process metrics show "Not available".
- `pip` package names in "Downloading" lines use underscores and versions; progress now matches the lock names.

### Tests

17 Python tests (real venv, real API process) on Linux 3.12 and Windows Store 3.13; 30-check Godot end-to-end
test (presses Setup, waits for the console, checks values, stops the engine, reopens the app, presses Start)
on Linux and native Windows Godot. All green. Screenshots in `docs/screenshots/loop-0/`.
