# Architecture overview

## Today (2026-11-07)

A Godot app in front, a Python engine behind it on 127.0.0.1, one SQLite database and a folder of kept originals
on the user's disk. Every model call goes out with the user's own OpenAI key; nothing else leaves the computer
unless the user connects it (an MCP server, a sign-in, the browser extension).

| Layer | Where | What |
|---|---|---|
| Interface | `scenes/brain/` | the graph (`graph_view.gd`), table (`table_view.gd`), captures, projects, agent panels, document viewer, import and voice-memo dialogs, the MCP lights and window (`mcp_lights.gd`), the timeline (`timeline_dialog.gd`) |
| Startup | `scenes/startup/`, `engine/bootstrap.py`, `engine/installer/` | Python located (or the bundled one), venv, pinned dependencies, migrations, the engine started and checked |
| Engine API | `engine/api/` | FastAPI routers: brain, sources, assistant, agents, voice, missions, packs, backups, billing, capture, MCP |
| Knowledge | `engine/brain/` | notes, places (PARA), links, themes; the archivist (`archivist.py`), meaning (`meaning.py`), paths (`connect.py`), @ mentions, packs, typed items (`types.py`), the table and grocery lists (`table.py`), Letter export (`export_doc.py`), the timeline and restore points (`timeline.py`) |
| Intake | `engine/sources/` | files, pages, links, pictures, local OCR, folders and zips of notes (`folder_import.py`, `zip_import.py`), voice memos (`audio.py`), recipes read from their page (`recipe.py`), kept originals |
| Assistant and agents | `engine/assistant/`, `engine/missions.py` | chat with tools, agents as profiles with capabilities, missions in the background |
| Voice | `engine/voice/` | push-to-talk, the live conversation, keys in the OS credential store (`secrets.py`) |
| MCP | `engine/mcp/` | the Brain as an MCP server (`server.py`, `proposals.py`, `relay.py`) and client (`client.py`, `catalog.py`, `oauth.py`, `local.py`); see [mcp.md](mcp.md) |
| Browser | `engine/browser/`, `browser-extension/` | the Edge / Chrome extension: send the page you see, tabs by voice |
| Data | `engine/database/migrations/` | 20 checksummed migrations (0001 → 0020) |

Python dependencies (engine/requirements.in): fastapi, uvicorn, psutil, websockets, pypdfium2; everything else uses
the standard library (the MCP protocol, OAuth, PDF printing through Edge, audio headers, the zip import).

More: [intake.md](intake.md) (with voice memos), [knowledge-model.md](knowledge-model.md),
[typed-items.md](typed-items.md) (recipes, table, export), [missions.md](missions.md), [mcp.md](mcp.md),
[backups.md](backups.md), [packs.md](packs.md), [live-conversation.md](live-conversation.md).

## Startup and engine lifecycle (Loop 0)

```
┌──────────────────────────── Godot app (GDScript) ────────────────────────────┐
│ Welcome ── Setup ── System Console                                           │
│   │          │  PythonLocator: runs `bootstrap.py detect` on a worker thread │
│   │          │  BootstrapRunner: OS.create_process + tails events-*.jsonl     │
│   │          ▼                                                                │
│   │   Backend: install_state.json, runtime/server.json, api_token            │
│   │          │  ApiClient (HTTPRequest) → 127.0.0.1:<port>, Bearer token      │
└───┼──────────┼───────────────────────────────────────────────────────────────┘
    │          │ spawn (no console window)
    ▼          ▼
 engine/bootstrap.py  — standard library only
   python → directories → venv → dependencies → database → service → health
   writes JSON Lines events, install_state.json, logs/bootstrap.log
              │ spawn detached, token via environment variable
              ▼
 engine/api/server.py — FastAPI + uvicorn on 127.0.0.1 only
   /health (public) · /system/status · /system/storage · /system/events · POST /system/shutdown
   parent-pid watchdog · writes runtime/server.json · records events in SQLite
              │
              ▼
 <data dir>/data/second_brain.sqlite3 — application_settings, schema_migrations,
                                        system_events, service_status
```

### Principles applied

- **Real or nothing.** Every number in the System Console comes from the API (psutil, `shutil.disk_usage`,
  SQLite) or from Godot itself (`OS.get_static_memory_usage`, FPS). Missing values show "Not available".
  When the engine is offline, cards are labelled "Last known · engine offline" and live process metrics are
  blanked.
- **Success only after verification.** The bootstrap's final `ok` event is emitted after `/health` answered
  with the expected instance id, an authenticated call succeeded, and an unauthenticated call was refused.
- **Idempotent and resumable.** Each step checks the real state first (venv runs with the right Python, lock
  hash matches and packages import, migrations recorded with checksums, API answers as our instance).
  A failed step is retried on the next run; finished steps are skipped.
- **User data outside the repo.** OS user data folder, overridable with `SBGD_HOME`.
- **No silent downloads of interpreters, no admin rights, no remote scripts.** Only pip wheels, pinned with
  SHA-256 hashes (`--require-hashes --only-binary=:all:`).

### Data folder layout

| Path | Content |
|---|---|
| `.venv/` | private virtual environment (one per OS, so Windows and WSL never collide) |
| `data/second_brain.sqlite3` | database (WAL mode) |
| `originals/` | kept originals (files, pages, pictures, voice memos), named by their SHA-256 |
| `exports/` | Letter pages and PDFs |
| `imports/zips/` | unpacked zips of notes (swept after a day) |
| `mcp/` | the token file of each MCP client using the WSL relay |
| `secrets/` | private key files where the OS credential store is not available |
| `logs/bootstrap.log`, `logs/server.log` | every event (including pip output), API log |
| `runtime/` | `events-*.jsonl` (last 10 kept), `server.json`, `api_token`, `bootstrap.lock` |
| `config.json` | user settings, currently `port` (default 8765) |
| `install_state.json` | verified steps, Python, lock hash, last success |

The venv lives in the data folder rather than in the repository: one checkout used from both WSL and Windows
would otherwise mix `bin/` and `Scripts/`, and the source tree stays clean.

### Dependencies

`engine/requirements.in` lists direct dependencies (FastAPI, uvicorn, psutil). The lock file is generated with
hashes for all platforms:

```bash
uv pip compile engine/requirements.in --universal --generate-hashes --python-version 3.12 --no-header -o engine/requirements.lock
```

Changing the lock changes its SHA-256, so the next setup reinstalls automatically.

### Security model (the engine API)

- The API binds to `127.0.0.1` only.
- A new random token (32 bytes, URL-safe) is created at each start, passed to the server through an environment
  variable (not the command line), stored in `runtime/api_token` (mode 600 on POSIX; the Windows user profile is
  private by default) and deleted when the server stops. It never appears in logs or events.
- `/health` is public and reveals nothing private. Every `/system/*` route requires `Authorization: Bearer`.
- No CORS, no docs endpoints. A browser page cannot read the API without the token.

### Extension points (deliberately small)

- New tables: add `engine/database/migrations/0002_*.sql`. Applied migrations are checksummed and immutable.
- New API routes: add them in `engine/api/app.py` (or a router module) with `Depends(require_token)`.
- New setup steps: add to `STEPS` in `engine/installer/steps.py` and to `STEPS` in `scenes/startup/setup.gd`.
- New console cards: `InfoCard.new().setup(title)` with rows from an API call.

### Supported platforms

| | Status |
|---|---|
| Windows 10/11, python.org or Microsoft Store Python 3.12/3.13 | primary, tested natively |
| Linux (tested on Ubuntu under WSL2, Python 3.12) | tested |
| macOS | paths implemented, not tested |
| Exported Godot build | not yet: Loop 0 runs from the source checkout (the engine is read from `res://engine`) |
