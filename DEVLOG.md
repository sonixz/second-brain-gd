# Devlog

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
