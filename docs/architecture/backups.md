# Backups, restore, start fresh (Loop 29)

Code: `engine/backups.py`, routes `engine/api/backup_routes.py`, app-level state `engine/appstate.py`.
The engine room shows it (Loop 30).

## Where
The destination is a folder the user chooses (another disk, OneDrive, a USB key), saved in `<data>/config.json`
under `backups`. Until one is chosen, `<data>/backups`: that protects against mistakes, not against a dead disk,
and the status says so (`same_disk`).

```
<destination>/brain-<id>/
  snapshots/<UTC stamp>-<kind>/brain.sqlite3   the whole database (SQLite online backup: consistent while running)
  snapshots/<UTC stamp>-<kind>/manifest.json   counts, checksum, schema and app version, the originals it uses
  originals/<xx>/<sha256>.<ext>                kept files, copied once (their name is their fingerprint)
```
`<id>` is the Brain's id (`app_state.json`), so several Brains can share a destination later.

## What is in, what is not
Everything the database holds: items, places, links, themes, documents and passages, page pictures,
conversations, agents, undo history, graph positions, settings. **Never the API keys**: they stay in the Windows
Credential Manager (or the private file on Linux). Not the Python runtime, the agent room or the logs.

## Kinds and rotation
`auto` (every N hours while the app is open, default 24, first check a minute after start), `manual`,
`before-restore`, `before-fresh`. Rotation keeps the newest backup of each of the last 7 days, 4 weeks and 6
months, the last 5 manual backups, every safety copy of the last 30 days, and always the newest; originals no kept backup uses are removed.

## Verify
After writing, each backup is reopened: database checksum, `PRAGMA quick_check`, counts against the manifest,
every original present. A backup that does not read back is deleted and the error raised. `verify` (deep) also
re-hashes every original against its name.

## Restore and start fresh
Both take a **verified** backup first (`before-restore` / `before-fresh`); if it fails, nothing is touched.
- Restore: the chosen backup is verified (deep), its files copied back, its database migrated in a temporary
  copy (an older backup gets the newer migrations), then the live database takes its content in place (SQLite
  backup): the engine keeps running. Files of the replaced Brain are removed (they are in the safety copy).
- Start fresh: a new database with the starter notes takes the live database's place; the originals are cleared.

Kept by both: `app_state.json` (browser pairing, bookmark capture key, the Brain's id, the last backup),
`config.json`, the API keys, the Python runtime, the agent room, the app preferences.

## API (local, token required)
| Route | |
|---|---|
| `GET /data/backups` | status: settings, destination, same disk?, last backup and its age, overdue?, the list |
| `POST /data/backups` | back up now |
| `PUT /data/backups/settings` | `{destination, every_hours, enabled}` (the destination must be writable) |
| `POST /data/backups/{id}/verify` | deep check of one backup |
| `POST /data/backups/{id}/restore` | `{"confirm": "RESTORE"}` |
| `POST /data/fresh` | `{"confirm": "START FRESH"}` |

`SBGD_BACKUPS=off` stops the automatic backups (tools that need a quiet engine).
