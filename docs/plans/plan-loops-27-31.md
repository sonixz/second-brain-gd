# Plan: Loops 27 to 31 — self-contained install, backups, your data, open source

Agreed with the owner on 2026-11-05. Goal: anyone can install Second Brain GD without installing Python, never lose
their Brain, start fresh or leave cleanly, and the repository can be opened to the public.

Decisions already taken:
- Windows first, then Linux. **macOS is out of scope** for now.
- Backups are **not encrypted** at first: protection comes from BitLocker / the destination (OneDrive…); the docs say
  so plainly. (Encryption would need `cryptography`, which Loop 27 removes.)
- Everything about data (backups, export, packs, start fresh, uninstall) lives in **the engine room** (System
  Console, the operations dashboard), not in the Brain screen and not in Captures.
- **Several Brains (multiple graphs) is parked.** Loops 29–30 are built so it can come later without rework.
- Nothing is published automatically: builds produce files; the owner publishes. The repo stays private until
  the owner decides; the licence is the owner's choice.
- Erasing is never possible by voice and never without a verified backup first.

Each loop: build, test, review screenshots (English and French), document, commit and push, then a short report.
Development happens in a separate git worktree, so the owner's running copy stays stable until a loop is done.

---

## Loop 27 — Fewer dependencies

| What | How |
|---|---|
| Replace `keyring` (and the ~9 packages it pulls: `cryptography`, `cffi`, `pycparser`, `jaraco.*`, `more-itertools`, `secretstorage`, `jeepney`, `pywin32-ctypes`) | Our own credential store: Windows Credential Manager called directly (ctypes, `CredWriteW` / `CredReadW` / `CredDeleteW`); on Linux, the private file that already exists as the fallback (0600). |
| No migration needed | Credentials are written and read the way `keyring` did on Windows (same names, same encoding, same persistence), so a key saved before is found as it is. Checked on Windows against `keyring` itself, on a test service name, never on the real key. |
| Drop `pypdf` | `pypdfium2` (already used to show pages) extracts the text too. Same results checked on the sample PDFs. |
| Lock | `engine/requirements.lock` regenerated with hashes; the installer reinstalls the dependencies when the lock changes (already does). |

Result expected: 27 → about 15 packages. Tests: credential store (save, read, delete, migration), PDF text identical.
**Confidence 85 %.**

## Loop 28 — Python inside the package (Windows, then Linux)

| What | How |
|---|---|
| Build script (`tools/package/`) | Takes a pinned *python-build-standalone* CPython (version and SHA-256 fixed in the repo), installs the locked wheels into it (`--require-hashes`), checks it: SQLite with FTS5 and WAL, every migration, engine start, `/health`. A failed check fails the build. |
| The app | Uses the bundled interpreter. The current path (system Python + venv) stays as **developer mode** for contributors. |
| Codex | Becomes optional: downloaded (with its fingerprint check) the first time the agent room is opened, after the user says yes. Today it is 458 MB on the owner's disk. |
| Build on GitHub | A workflow builds the Windows (then Linux) package and publishes its SHA-256 sums as build artifacts. It never publishes a release. |
| Linux notes | Local OCR needs `tesseract-ocr` (documented, not bundled); the API key is kept in the private file. |

Expected size: about +30–40 MB over the Godot export. **Confidence 85 % Windows, 75 % Linux.**

**Done 2026-11-05.** Runtime: Windows 50 MB, Linux 94 MB unpacked; Windows app zip 79 MB (the Godot template is 109 MB of it). Checked for real: the Linux runtime runs the whole setup in 9.8 s, the Windows one in 3.7 s on Windows, and the exported Windows app (headless, autosetup, throwaway data folder) found its own Python, set up and started the engine, which stopped with the app. The Linux app export needs Godot's Linux templates, not installed on the owner's machine: the GitHub workflow installs them (pinned, SHA-512 checked). The workflow has not been run yet: it is manual, the owner starts it.

## Loop 29 — Backups (the engine)

| What | How |
|---|---|
| Snapshot | The database copied while the app runs (SQLite online backup: consistent), with a manifest (app and schema version, counts, checksums). |
| Originals | Copied once: they are already stored by fingerprint, so a daily backup only adds new files. |
| What is in | Everything: items, places, links, themes, sources and passages, pictures, conversations, agents, undo history, graph positions, settings. **Never** the API keys (they stay in the credential store). |
| Destination and rotation | A folder chosen by the user (another disk, OneDrive, a USB key); 7 daily + 4 weekly + 6 monthly; automatic (at start and every N hours while open). |
| Verify | Each backup is reopened and checked after writing. |
| Restore | Pick a date → the current state is backed up first → replace → migrations run if the backup is older. |
| Start fresh | Verified backup first (no backup, no erase) → the Brain's content is emptied → a new Brain with its starter notes. Kept: Python, the agent room, the API key, preferences, browser pairing. |
| Out of the database | Browser pairing tokens and the bookmark's capture key move to app-level storage, so Start fresh (and, later, several Brains) keep them. |
| Packs | Fix: pictures from web pages (Loop 25) now travel in packs too. |

Tests: back up → restore into an empty folder → compare everything; Start fresh → nothing of the old Brain is left
except what is kept on purpose; restore an older-schema backup. **Confidence 85 %.**

**Done 2026-11-05** (docs/architecture/backups.md). Checked on a read-only copy of the owner's real Brain: backup 0.08 s, the second one copies no file, restore into an empty folder gives identical tables and files, Start fresh then restoring its safety copy gives the starting Brain back. Encryption: not done, as decided.

## Loop 30 — "Your data" in the engine room

| What | How |
|---|---|
| Backups card | "Last backup: 2 h ago ✓", Back up now, destination, frequency, list of backups, Restore. Warning when the last backup is too old. |
| Export everything | One file to move to another computer (same zip format as packs, kind "backup"). |
| Packs | Moved here from Captures (share a project / import a pack). |
| Start fresh | Two steps, a word to type, automatic verified backup before. |
| Repair the installation | Reinstalls the Python environment without touching the data. |
| Uninstall | Removes the folder, the key in the credential store and the app preferences, after a typed confirmation; a backup is offered first. |
| Voice | "Back up now", "when was the last backup?". Never a voice command that erases. |
| Language and guides | English and French; every screen reviewed in both; How-to guide "Back up and restore". |

**Confidence 85 %.**

**Done 2026-11-05.** Also: rotation keeps the last 5 manual backups (two the same day were collapsing into one, seen in the screenshots); the typed-word dialog had a stretched height (fixed width label). Uninstall keeps the backups folder by default when it sits inside the data folder.

## Loop 31 — Before opening the repository

| What | How |
|---|---|
| Secrets | Scan the whole git history (every commit, every branch) for keys and tokens. |
| Assets | Check the right to redistribute every music track, sound and font; replace what cannot be shipped. |
| Documents | README for newcomers, CONTRIBUTING, third-party licence notices, the Uninstall page, the Linux notes. |
| Licence | The owner's choice; the dependencies' licences are listed for that choice. |

**Confidence 90 %** for the audit itself; the music is the open question.

**Done 2026-11-05**: see docs/audit-before-public.md. History clean (fake test keys only; the committed .env holds only encrypted values, the private key was never committed). Godot's licence notices were missing from the package: added. Open for the owner: rotate the three keys, decide about versioning .env, the ElevenLabs plan for the audio, two third-party pages stored in the How-to recordings, the licence.

---

## What the owner can test meanwhile

The running copy stays on the last finished loop until the owner restarts the app after a "ready" message.
Useful now (today's work):
1. Restart the app; it opens in English: click **FR**, close, reopen: still French.
2. `edge://extensions` → Second Brain GD → **Reload**; right-click a picture → *Envoyer cette image au Brain*.
3. On a page with pictures: the extension's icon → *Envoyer cette page*: the receipt counts the pictures kept;
   the page's card shows its main image; open it: the pictures come first.
4. Speak to the Archivist in English with the app in French (and the reverse): it answers in the language spoken.
5. Ask something whose answer describes links ("c'est quoi le Brain?"): the answer must not be replaced by
   "Aucun changement n'a été fait".

Anything odd: a screenshot is not needed, a sentence is enough (what you did, what you saw).
