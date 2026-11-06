# Contributing

Thanks for looking. Second Brain GD is built in small, finished steps ("loops"): each one works, is tested,
documented and shown before the next starts. The same rules apply to every change.

## Set up
- Godot 4.7 (standard build), Python 3.12 or 3.13, Git. Clone, open `project.godot`, press **Run**, then **Setup**:
  the engine gets its own virtual environment and the 15 hash-locked packages of `engine/requirements.lock`.
- Your data never lives in the repository: `%LOCALAPPDATA%\SecondBrainGD` (Linux `~/.local/share/second-brain-gd`),
  or `SBGD_HOME` to use another folder (a throwaway one for experiments).
- An OpenAI key is optional for most work; the tests never use one (they use a fake model).
- Running from the source without the editor (`godot --path .`)? After pulling, run `godot --headless --path . --import`
  once: it refreshes Godot's list of named classes, which only the editor updates by itself.

## Test
```bash
./tools/test.sh            # Linux / WSL: Python tests, then the Godot end-to-end run (headless)
.\tools\test.ps1 -Godot C:\path\Godot_console.exe     # Windows
```
The Python tests start the real engine in temporary folders; the Godot test presses the real buttons, headless.
Every change keeps both green and adds tests for what it adds.

## The rules every change follows
- **English first, French second.** Every text the interface shows is written in English inside
  `I18n.t("...")` (`scripts/core/i18n.gd`) and translated in `i18n/fr.json` in the same change;
  `python3 tools/i18n.py --check` fails otherwise (the tests run it). The website is English only.
- **No secrets.** Keys come from the environment (developers: `dotenvx run`), never in code, logs or tests.
- **Nothing silent.** The app never downloads an interpreter or runs remote code on its own; anything that
  replaces or erases data takes a verified backup first and asks the user.
- **Shown, not told.** UI changes are checked on real screenshots, in both languages
  (`SBGD_UI_LANG=fr tools/showcase.sh <name>`, `SBGD_CAPTURE_SCRIPT=screens tools/showcase.sh <name>`), on a private
  virtual display: no window opens.
- **Documented.** `public/docs.html` for users, `docs/architecture/` for developers, a How-to guide when a feature
  is a task (`tools/howto/guides.py` + `tools/howto.gd`, regenerated with `tools/howto.sh`).

## Packages
`python3 tools/package/build.py app --target windows|linux` builds the app with its own Python
(`tools/package/runtime.json` pins it), `tools/package/check_runtime.py` runs the real setup with it. The GitHub
workflow `Package` does both, by hand only, and never publishes.

## Where things are
See the repository layout in `README.md`, and `docs/architecture/overview.md` for how the pieces talk.
