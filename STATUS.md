# Status

**Loop 0 — Foundation, Bootstrap & System Console: done (2026-11-02).**

## Acceptance criteria

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Godot opens the project | ✅ | load check without script errors (Godot 4.7.2 Linux and Windows) |
| 2 | Setup starts a real procedure | ✅ | Godot test presses the real Setup button; venv, pip, SQLite, API are created |
| 3 | User sees real progress | ✅ | progress from bootstrap events; dependency step observed running; live pip log |
| 4 | SQLite database is created | ✅ | 4 tables, migration 0001 recorded with checksum |
| 5 | Backend starts and answers `/health` | ✅ | verified by bootstrap, Python tests and Godot test |
| 6 | Dashboard shows real statuses | ✅ | console values checked against `server.json` pid, venv, schema |
| 7 | Reopening recognises the install | ✅ | second app instance shows "Start"; fast path 3–4 s |
| 8 | Re-running setup does not damage data | ✅ | `installed_at` unchanged, steps skipped, settings kept |
| 9 | `public/index.html` works standalone | ✅ | opened over `file://` in Edge, desktop and 360 px |
| 10 | Tests run and documented | ✅ | see below |

## Test results (final run, 2026-11-02)

| Suite | Platform | Result |
|---|---|---|
| Python unit + integration (17) | Linux, Python 3.12.3 | OK, 1 skipped (non-loopback check: hostname resolves to loopback in WSL) |
| Python unit + integration (17) | Windows 11, Microsoft Store Python 3.13.14 | OK |
| Godot headless load check | Linux, Godot 4.7.2 | no script errors |
| Godot end-to-end (30 checks) | Linux, Godot 4.7.2 + Python 3.12 | 30 passed |
| Godot end-to-end (30 checks) | Windows native, Godot 4.7.2 console + Store Python 3.13, data under `%LOCALAPPDATA%` | 30 passed |

Not run: the GitHub Actions workflow (it runs on the next push), macOS.

## What exists

- Welcome, Setup and System Console screens (dark forest/mint theme, animated graph logo).
- Standard-library bootstrap: detect, directories, venv, hash-locked deps, migrations, API start, verified health.
- FastAPI service on 127.0.0.1 with bearer token, parent-process watchdog, graceful shutdown.
- SQLite: `application_settings`, `schema_migrations`, `system_events`, `service_status`.
- Static landing page in `public/`, disabled Pages workflow, CI workflow.

## Known limitations

- Runs from the source checkout only. An exported Godot build would not find `engine/` yet.
- Python must be installed by the user (guided, not automated).
- First setup needs internet access to PyPI.
- macOS paths are implemented but untested.
- No knowledge features yet (by design).
- No licence file yet: the owner has to choose one before going public.
