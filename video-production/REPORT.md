# Production report — the showcase film (2026-11-13)

Asked by the owner on 2026-11-13 (« ce qui est surtout nice, c'est le vidéo avec la voice, la musique »), then
« travaille-moi le vidéo, c'est le vidéo qui va débloquer tout ». Plan: `docs/plans/plan-site-film.md`, FILM-I,
FILM-K and FILM-N. Made by Claude Code in the second-brain-gd session, branch `site-film`.

## What it shows (the real app, filmed)

| Scene | In the film | In the app |
|---|---|---|
| The Brain | the graph of a Brain, a place per ring, beside the Archivist's panel | the graph, Zones view |
| Capture | a thought typed in the capture bar; a PDF dropped on the window | the capture bar, files dropped |
| The Archivist | each one filed, with a receipt that says what and where, and Undo | the archivist, receipts |
| The zoom | from the places to a PDF inside the graph, to its page | semantic zoom, the document viewer |
| Views and time | Timeline, Focus, Meaning map, the play at 4×, Layers (3D) with a flight | the graph's views, the Time bar |
| Ask | a question, its answer with the item it comes from; a path between two ideas | the Archivist's chat, paths |
| An AI tool | a proposal over MCP waits, is approved, is filed, is shown | AI tools › who may read your Brain |
| Themes | the seven themes | the theme switch |

## How it was filmed

- Godot's movie mode (thirty PNG frames a second, the app's own sound beside them) of the real app, on a private
  Xvfb display, at 1920×1080: `tools/film.sh`, the steps of `tools/film.gd`. No window was opened; nothing of the
  owner's own Brain was filmed: the English showcase Brain, in a temporary home.
- The interface is drawn 1.4 times larger than on a screen (the layout of a 1371×771 window), so its text is
  readable in a film watched small. Each scene frames the whole Brain by computing it from the graph's rectangle.
- Each step leaves « mark <name> <frame> » lines; the cut (`scripts/compose.py`) takes its shots from them.
- The camera moves towards a receipt or an answer are computed on a frame enlarged four times.

## What is real, what is a stand-in, what is left out

- **The real archivist** (a model call, the owner's OpenAI key through dotenvx, never printed) in the scenes where
  it works: `capture`, `ask`, `tool`. Its receipts, its summary of the PDF and its answer are the model's own
  words. The other scenes (`open`, `zoom`, `views`, `themes`) run without a key.
- **A stand-in:** in the tool scene, the tool's three calls (overview, search, propose_item) are made by the film
  script through the Brain's real MCP endpoint, with a key of its own, under the name « Claude Code ». The
  approval is the app's own Approve button, pressed by the script as a user would; the filing is the Archivist's.
- **Left out:** a page sent from the browser (it needs a real browser on the desktop) and the voice (a virtual
  display has no microphone). The narration says « say it »; the film does not show it.
- **Faster than life:** the movie mode runs slower than real time, so an answer of the engine that takes a few
  seconds seems to come at once. The play of the Brain growing is at the app's own 4× speed.
- **Drawn, not filmed:** the titles and the closing card.
- **A question changed:** « What did I decide for the countertops? » got an honest « I don't see a recorded
  countertop decision »; the scene was filmed again with a question the demonstration Brain can answer.

## What the film found in the app

- Two lines a tool's proposal leaves in the item (« Proposé par… », « Lieu suggéré… ») and the automatic restore
  point's name were in French whatever the interface's language. Fixed on this branch (`engine/mcp/proposals.py`,
  `engine/brain/timeline.py`), with a test; the scene was filmed again.
- A theme switch writes about two hundred font errors in the log (`_font_get_ascent: Parameter "fd" is null`),
  with or without the film's larger interface; nothing shows in the picture. Written in BACKLOG.md.
- With eleven lanes (one per place) the timeline does not fit a window of this height: the film uses the lanes by
  type. Already in BACKLOG.md.

## Sound and other sources

| Asset | Source | Licence / terms |
|---|---|---|
| Narration (9 lines) | ElevenLabs text to speech, voice « Eric » (the one of Agent Manager's film), `eleven_multilingual_v2`, the owner's account | ElevenLabs' terms for the owner's plan (see limits) |
| Music (`assets/audio/music.mp3`, 64 s) | ElevenLabs Music, from `assets/audio/music-prompt.txt`, instrumental | same |
| Effects | the app's own (`assets/audio/sfx`), generated with ElevenLabs when the app was made | same |
| Titles | Ubuntu Bold and Light (the system's fonts, `/usr/share/fonts/truetype/ubuntu`) | Ubuntu Font Licence 1.0 |
| Logo | `public/assets/logo.svg`, the project's own | MIT, with the project |
| Footage | the app itself | MIT, with the project |

The app's sound recorded with the frames (its theme's music, its effects) is not in the final mix: two musics would
play at once. The effects are placed where the app plays them.

## Checks

- Master: 62.5 s, H.264 High 1920×1080 30 fps, AAC stereo 48 kHz; −13.4 LUFS integrated, peak −1.2 dBTP.
- Picture: a frame every 2.6 s reviewed, and the retouched shots one by one.
- No secret on screen: a demonstration Brain; the tool's key is never displayed.
- Tests after the engine's change: see the plan's « Done » notes.

## Limits

- **The agent cannot listen.** The pronunciation of « G.D. », the voice's tone, the music and the mix are for the
  owner's ear. The music follows a prompt with timed sections; whether its last hit lands on the card was checked
  on its loudness curve only.
- **The rights on the ElevenLabs audio are not verified**: they depend on the plan of the owner's account. To
  confirm before anything is published.
- The cost of the real calls was not measured (the key cannot read the account's usage): about ten runs of scenes
  with the real archivist, nine voice takes, one piece of music.
