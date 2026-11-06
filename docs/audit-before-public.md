# Audit before opening the repository (Loop 31, 2026-11-05)

What was checked before the repository can be made public, what was found, and what the owner decides. Nothing
here changes the repository's visibility: that stays the owner's decision.

## 1. Secrets in the history: clean, one recommendation
Scanned: every commit of every branch (75 commits), added lines only, for OpenAI keys (`sk-`, `sk-proj-`,
`sk-admin-`), GitHub tokens (`ghp_`, `github_pat_`, `gho_`), AWS keys, Slack tokens, Google API keys and private-key
blocks; and every file name ever added for `.env`, `.pem`, `.key`, `id_rsa`, keystores, credentials.

| Found | Verdict |
|---|---|
| `sk-test-0123456789abcdef`, `sk-proj-not-a-real-key-000000000000`, `sk-admin-not-a-real-key-0000000000` | Fake values used by the tests. Fine. |
| `.env` committed (3 versions: f250dcc, 3bc6d0f, 61ee2ef), by design (dotenvx) | Every value is **encrypted** (`encrypted:…`; ELEVENLABS_API_KEY, OPENAI_API_KEY, OPENAI_ADMIN_KEY) plus the public key. The private key (`.env.keys`) was **never** committed. Not readable by anyone without the owner's private key. |

**Recommendation before going public (owner's action):** rotate the three keys (OpenAI, OpenAI admin, ElevenLabs).
Encrypted values stay in the history forever; once rotated, they are worthless even if the private key ever leaked.
Then decide whether `.env` keeps being versioned: a public repository does not need it (each developer has their own
keys). To stop versioning it without deleting your local copy, back it up first: removing a tracked file from git
deletes it from the working folder on the next update.

No personal path or user name in the files (the guides' recordings contain base64 data that matches such searches
by chance only). The commit metadata shows the author e-mail `the owner's personal e-mail` on every commit: GitHub can use a
`noreply` address for future commits if you prefer; past commits keep theirs unless the history is rewritten.

## 2. What the repository redistributes
| Part | Licence | Status |
|---|---|---|
| Godot Engine 4.7 (in the exported app) | MIT, with third-party components | **Fixed**: the package now carries `LICENSES/godot.txt` (licence + every bundled component), generated at build time (`tools/package/licenses.gd`). |
| CPython 3.12 (python-build-standalone, in the package) | PSF License, plus the libraries it is built with (OpenSSL, SQLite, zlib…) | `python/LICENSE.txt` is kept in the runtime. |
| The 15 Python packages (in the package) | MIT, BSD-3-Clause, Apache-2.0 / BSD-3-Clause (pypdfium2 + PDFium), PSF-2.0 | Their licence files stay in their `*.dist-info`. All permissive. |
| Codex app-server (agent room) | Apache-2.0 | Not in the package: downloaded on demand, from its publisher. |
| Fonts | — | None shipped: the app uses the system's fonts. |
| Icons (`assets/icons`, extension icons) | The project's own | Fine. |
| **Music, ambience and sound effects (26 files, `assets/audio`)** | Generated with **ElevenLabs** from the project's own prompts (`tools/audio-prompts.txt`) | **Owner to check**: the right to redistribute generated audio depends on the ElevenLabs plan used (paid plans grant commercial use; the free plan asks for attribution and non-commercial use). If unsure: regenerate on a paid plan, or replace with CC0 sounds. |
| **Pages stored in the How-to recordings** | Their publishers' | **Owner to decide**: `tools/howto/recordings/web.json` holds a full copy of a commercial blog page (ciarraappliances.com) and `browser.json` a Natural Resources Canada PDF (Crown copyright: reproduction for non-commercial purposes with attribution is generally allowed). Before going public: re-record the web guide on a source with an open licence (Wikipedia), or keep the recordings out of the public repository. |
| Screenshots of web pages in the How-to (Wikipedia, Government of Canada) | Wikipedia: CC BY-SA 4.0 | Credited on the How-to page. |

The full list is in `THIRD_PARTY_NOTICES.md` (repository root, copied into every package).

## 3. Documents for newcomers
- `README.md` rewritten: what it is, download and run, from the source, documentation, privacy and costs.
- `CONTRIBUTING.md`: setup, tests, the rules every change follows (English first + French, tests, docs, guides).
- `THIRD_PARTY_NOTICES.md`.
- Uninstalling: `public/docs.html#backups` (Uninstall in Your data) and by hand (`#uninstall`).
- Linux notes: `public/docs.html#install` (Tesseract optional, the key in a private file).

## 4. The licence: the owner's choice
Everything the project depends on is under permissive licences, so any common choice works:
- **MIT** or **Apache-2.0**: anyone may reuse the code, also in closed products (Apache-2.0 adds an explicit patent
  grant and asks to state changes);
- **GPL-3.0** or **AGPL-3.0**: whoever distributes a modified version (AGPL: also over a network) must publish its
  source under the same licence;
- **MPL-2.0**: in between, file by file.

The package build already copies `LICENSE` into the package when the file exists.

## Checklist before making the repository public
1. Rotate the OpenAI, OpenAI admin and ElevenLabs keys.
2. Decide about `.env` (keep it encrypted in git, or stop versioning it: back it up first).
3. Check the ElevenLabs plan for the audio files, or replace them.
4. Re-record the web guide on an openly licensed page, or keep the recordings private.
5. Choose and add the `LICENSE`.
6. Then, and only then, change the visibility (the owner).
