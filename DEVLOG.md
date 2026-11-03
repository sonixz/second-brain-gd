# Devlog

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
