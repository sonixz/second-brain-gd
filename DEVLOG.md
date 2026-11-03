# Devlog

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
