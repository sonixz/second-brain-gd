# Second Brain GD

**Your knowledge. Your system. Your control.**

Second Brain GD is an open-source, local-first second brain you can talk to. Give it anything (a thought,
a link, a PDF, a photo, your voice): an archivist files it with the CODE method and PARA, links it by meaning
to what you already know, and you explore it all in a living graph you can zoom into until the text is there.
Godot is the interface, a local Python engine runs the services, and everything stays in your user folder.

> Status: **Loop 15**, in active development. Intake and archivist, semantic zoom, originals and PDF viewer,
> zones, filters, paths, timeline, brain packs, push-to-talk and live conversation. See [STATUS.md](STATUS.md)
> and the journal on the landing page (`public/index.html`).

**Documentation:** open [`public/docs.html`](public/docs.html) — install, the archivist, the graph, voice
commands, and integration tutorials (browser bookmarklet, local HTTP API, brain packs, real AI costs).

The repository is **private** during development.

![The graph: one zone per place, the Inbox in the middle, the assistant answering on the left](docs/screenshots/showcase/01-graph-overview.png)

| Zoom in: items become cards | Your PDFs, page by page | How is X connected to Y? |
|---|---|---|
| ![Cards](docs/screenshots/showcase/04-graph-cards.png) | ![Document viewer](docs/screenshots/showcase/07-document-viewer.png) | ![Path](docs/screenshots/showcase/10-path.png) |

The screenshots come from a scripted example brain (`SBGD_SHOT_SIZE=1600x1000 ./tools/showcase.sh`):
no OpenAI calls, no personal data, rendered on a private virtual display.

## Quick start on Windows

### 1. Prerequisites

| Tool | Version | Where |
|---|---|---|
| Godot | 4.7 (standard build, not .NET) | https://godotengine.org/download/windows/ |
| Python | 3.12 or 3.13 | https://www.python.org/downloads/ |
| Git | any recent | https://git-scm.com/download/win |

When installing Python from python.org, tick **"Add python.exe to PATH"**. The Microsoft Store Python 3.12/3.13
also works (tested). Nothing needs administrator rights, and Docker is not used.

### 2. Clone and open

```powershell
git clone git@github.com:sonixz/second-brain-gd.git C:\git\second-brain-gd
```

Start Godot, choose **Import**, select `C:\git\second-brain-gd\project.godot`, then press **Run** (F5).

### 3. Press Setup

The app finds Python, creates a private virtual environment, installs the locked dependencies (internet access
to PyPI is needed the first time, about 30 MB), creates the SQLite database, starts the local API and verifies it.
Then the **System Console** opens.

On the next launch the welcome screen says **Installed** and **Start** takes a few seconds: completed steps are
verified and skipped.

### Where are my files?

| What | Location on Windows |
|---|---|
| Everything | `%LOCALAPPDATA%\SecondBrainGD` |
| Database | `...\data\second_brain.sqlite3` |
| Logs | `...\logs\bootstrap.log`, `...\logs\server.log` |
| Settings | `...\config.json` (for example `{"port": 8765}`) |

Linux uses `~/.local/share/second-brain-gd`, macOS `~/Library/Application Support/SecondBrainGD`.
Set `SBGD_HOME` to use another folder. Nothing is ever written inside the repository.

## Using it

- **Capture:** type in the bottom bar and press Enter (Ctrl+Space focuses it). `[[Another note]]` links,
  `#tag` groups.
- **Explore:** use the wheel to zoom, drag to pan, drag a node to move it. Click a note to edit it,
  a space to filter, a tag to search. Press `/` to search and Esc to close.
- **Ambiance:** the ♪ button at the bottom right sets the theme (Auto, Morning, Focus, Evening, Forest), music,
  effects and ambience.
- **Voice:** click the microphone (Ctrl+M), speak, click again. It needs your own OpenAI API key, asked once
  after setup or on first use. The key is stored in your system's credential store.
- **Assistant:** the left panel. She briefs you at the first opening of the day, answers from your notes
  (click a cited note to open it), and saves or moves notes when you ask. Everything she changes has an
  Undo. Toggle *Voice* to hear her, or use her mic to talk to her.
- **Engine room:** click "All systems operational" at the top right.

## Audio assets

Generated once and committed, so users never need an API key. To regenerate, edit `tools/audio-prompts.txt`,
then run:

```bash
./tools/audio.sh              # only missing files
./tools/audio.sh music/focus_2 # one file again
```

The ElevenLabs key comes from the encrypted `.env` via dotenvx (`dotenvx set ELEVENLABS_API_KEY ...`).
`.env.keys` is never committed.

## Voice benchmark (developers)

```bash
# once: add the key to the encrypted .env without showing it
read -rsp "OpenAI key: " K && echo && ~/.local/bin/dotenvx set OPENAI_API_KEY "$K" && unset K
./tools/voice-bench.sh --models gpt-realtime-whisper,gpt-live-transcribe
```

## Command line (optional)

The bootstrap runs without Godot too:

```powershell
python engine\bootstrap.py detect     # is this Python compatible?
python engine\bootstrap.py setup      # install / repair, then start the API
python engine\bootstrap.py status     # show install_state.json
python engine\bootstrap.py stop       # stop the API
```

With the Microsoft Store Python, create the data folder first (`mkdir %LOCALAPPDATA%\SecondBrainGD`);
see [troubleshooting](docs/troubleshooting.md#microsoft-store-python).

## Tests

```powershell
.\tools\test.ps1                                                  # Python tests
.\tools\test.ps1 -Godot C:\path\Godot_v4.7.2-stable_win64_console.exe   # + Godot end-to-end
```

On Linux or WSL: `./tools/test.sh` (set `GODOT=` if `godot` is not on PATH).
The Python tests create a real virtual environment and start the real API in a temporary folder.
The Godot test presses the real Setup button headless and checks the System Console values.

## Repository layout

```
scenes/        Godot screens (startup/, dashboard/) and UI components
scripts/       GDScript: core/ (app, theme, paths), setup/ (Python locator, bootstrap runner), monitoring/ (API client)
engine/        Python: bootstrap.py, installer/, database/ (+ migrations), api/, monitoring/
tests/         python/ (unittest), godot/ (headless end-to-end)
public/        landing page and docs (open public/index.html or public/docs.html, no build)
docs/          architecture/, troubleshooting, screenshots
tools/         test.sh, test.ps1, capture.sh / showcase.sh (screenshots on a private virtual display),
               web_images.gd (PNG → WebP for the site)
```

## Documentation

- [Architecture overview](docs/architecture/overview.md)
- [Event protocol (Python → Godot)](docs/architecture/events-protocol.md)
- [Process lifecycle](docs/architecture/process-lifecycle.md)
- [Knowledge model, Whisper and agents plan](docs/architecture/knowledge-model.md)
- [Troubleshooting](docs/troubleshooting.md)
- [STATUS](STATUS.md) · [BACKLOG](BACKLOG.md) · [DEVLOG](DEVLOG.md)
