# The showcase film

The film of the website's home page ([plan](../docs/plans/plan-site-film.md), FILM-I to FILM-N). Everything in it
is the real app, filmed on a private virtual display (Xvfb, never a window on the desktop) with the English
showcase Brain in a temporary home: never the user's own Brain. Only the titles, the closing card, the narration
and the music bed are added. The tools follow agent-manager-gd's (`video-production/` there).

## Film a scene

Needs: Godot 4.7, Xvfb (`tools/vdisplay.sh`), ffmpeg (the pinned build in `~/.local/opt/ffmpeg-n8.1.3-35`, or
another path with `FFMPEG=`).

```bash
tools/film.sh --list        # the steps: the film_* functions of tools/film.gd
tools/film.sh open          # films one step (about a minute and a half)
video-production/scripts/clip.sh open graph 10 video-production/output/open.mp4   # ten seconds from the mark « graph »
```

- **The first run installs the app once**, without filming, in a base home (`~/.cache/sbgd-film/home-base`); each
  step then films a fresh copy of it. `FILM_FRESH=1` installs it again (after a change of the app or of the
  showcase Brain).
- **A step leaves**, in `~/.cache/sbgd-film/captures/<step>/` (outside the repository: a step is hundreds of
  megabytes): `frame%08d.png` at 1920×1080, thirty a second; `frame.wav`, the app's own sound (its music, its
  effects); `marks.txt`, « mark <name> <frame> » lines. The cut is made from the marks, so it follows the app when
  a screen moves.
- **The archivist is scripted by default** (the showcase stand-in: no key, no cost). The real one:
  `FILM_REAL=1 dotenvx run -q -f .env -- tools/film.sh <step>` (a model call each time it files; the key is never
  printed).
- Godot's movie mode films at the project's window size: `tools/film.sh` writes a passing `override.cfg` and
  removes it. It runs slower than real time, so what happens outside Godot (the engine's answers) looks faster in
  the film than it is.

## Make the film again

```bash
tools/film.sh open zoom views themes                                   # four scenes, no key (about 25 min)
cd <the folder that holds your .env> && FILM_REAL=1 dotenvx run -q -f .env -- <repo>/tools/film.sh capture ask tool   # the real archivist
python3 video-production/scripts/compose.py                            # the cut: output/second-brain-showcase.mp4 (about 2 min)
video-production/scripts/render.sh video-production/output/second-brain-showcase.mp4 <a frame.png>   # the website's file and its poster
```

`FILM_STILLS=1 tools/film.sh <step>` first, to see a scene's framing without filming it. The film as cut is in
`storyboard.md`; what is real and what is not, the sources and the limits, in `REPORT.md`. The shots, the titles
and the mix are at the top of `scripts/compose.py`.

## Voice, music, effects

`scripts/elevenlabs.py` (the key from the environment, through dotenvx, never printed):

```bash
dotenvx run -q -f .env -- python3 -I video-production/scripts/elevenlabs.py say <voice id> <line.txt> video-production/assets/audio/vo-<id>.mp3
dotenvx run -q -f .env -- python3 -I video-production/scripts/elevenlabs.py music <prompt.txt> <milliseconds> video-production/assets/audio/music.mp3
dotenvx run -q -f .env -- python3 -I video-production/scripts/elevenlabs.py sfx "<description>" <seconds> video-production/assets/audio/sfx-<name>.mp3
```

The takes used by the film are kept in `assets/audio/`, so a new cut does not pay for them again.

## Files

| Path | What |
|---|---|
| `../tools/film.sh`, `../tools/film.gd` | filming: one step per scene, with its marks |
| `scripts/clip.sh` | a piece of a step as an MP4 with the app's sound |
| `scripts/compose.py` | the cut: shots, camera moves, titles, the closing card, the mix |
| `scripts/render.sh` | the website's file and its poster |
| `scripts/logo_png.gd` | the logo as a picture for the closing card |
| `scripts/elevenlabs.py` | voice, music, effects |
| `storyboard.md`, `narration.txt`, `REPORT.md` | the film as cut, its words, how it was made |
| `assets/audio/` | the exact takes used: `vo-v01` to `vo-v09`, `music.mp3` and its prompt |
| `work/`, `output/` | made by the scripts, not in git |
