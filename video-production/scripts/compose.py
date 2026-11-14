#!/usr/bin/env python3
"""Cuts the filmed steps into the showcase film, then adds the titles, the closing card, the narration, the music
and the app's own sound effects. After agent-manager-gd's video-production/scripts/compose.py.

Input:  $FILM_OUT/<step>/frame%08d.png and marks.txt (tools/film.sh: 1920x1080, thirty frames a second)
        video-production/assets/audio/vo-v0N.mp3 (the narration's takes), music.mp3 (the bed)
        assets/audio/sfx/*.mp3 (the app's own effects)
        video-production/work/logo.png (scripts/logo_png.gd)
Output: video-production/output/second-brain-showcase.mp4 (the master) and work/timeline.json (the film as cut).

Every shot is a piece of a filmed step of the real app: nothing is drawn here but the titles and the closing card.
A shot is `seconds` long from `after` seconds past a mark; cuts fall on the music's beats (120 a minute: 0.5 s).
The camera moves (towards a receipt) are computed on a frame enlarged four times, so they glide without wobbling."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VP = os.path.dirname(HERE)
REPO = os.path.dirname(VP)
CAP = os.environ.get("FILM_OUT") or os.path.join(os.environ.get("FILM_CACHE") or os.path.expanduser("~/.cache/sbgd-film"), "captures")
WORK = os.path.join(VP, "work")
OUT = os.path.join(VP, "output")
AUDIO = os.path.join(VP, "assets", "audio")
SFX = os.path.join(REPO, "assets", "audio", "sfx")
FFMPEG = os.environ.get("FFMPEG", os.path.expanduser("~/.local/opt/ffmpeg-n8.1.3-35/bin/ffmpeg"))
FONT = os.environ.get("FILM_FONT", "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf")
FONT_LIGHT = os.environ.get("FILM_FONT_LIGHT", "/usr/share/fonts/truetype/ubuntu/Ubuntu-L.ttf")
FPS = 30
W, H = 1920, 1080
BG = "0x2b3c54"       # the website's ground
MINT = "0xa9d4ff"
WARM = "0xffd2a1"
MUTED = "0xb5c6da"

# The film as cut: scene, shot name, step, mark, seconds after the mark, length, and (for some) a camera move:
# (x, y, w, h) on the 1920x1080 frame to glide towards, and how close.
SHOTS = [
    ("1", "brain",      "open",    "graph",        0.2, 5.0, None),
    ("2", "typed",      "capture", "start",        1.0, 3.5, None),
    ("3", "filed",      "capture", "sent",         0.0, 2.5, ((100, 560, 660, 300), 1.35)),
    ("2", "dropped",    "capture", "dropped",     -0.2, 1.5, None),
    ("3", "filed-pdf",  "capture", "receipt-pdf", -0.3, 3.5, ((100, 440, 660, 380), 1.3)),
    ("4", "zoom",       "zoom",    "far",         -0.5, 4.0, None),
    ("4", "read",       "zoom",    "cards",        1.0, 2.0, None),
    ("4", "page",       "zoom",    "read",         0.6, 1.5, None),
    ("5", "timeline",   "views",   "timeline",    -2.4, 2.0, None),
    ("5", "focus",      "views",   "focus",       -1.6, 1.5, None),
    ("5", "meaning",    "views",   "meaning",     -2.2, 2.0, None),
    ("5", "play",       "views",   "play",         0.8, 2.5, None),
    ("5", "layers",     "views",   "layers",       0.5, 1.5, None),
    ("5", "layers-fly", "views",   "layers-fly",   0.4, 2.0, None),
    ("6", "question",   "ask",     "start",        0.1, 2.0, None),
    ("6", "answer",     "ask",     "answer",      -0.4, 3.5, ((100, 590, 660, 230), 1.3)),
    ("6", "path",       "ask",     "path",         0.1, 3.0, None),
    ("7", "proposed",   "tool",    "proposed",    -0.5, 1.5, None),
    ("7", "waiting",    "tool",    "waiting",     -1.5, 2.5, None),
    ("7", "approved",   "tool",    "approved",    -0.2, 1.5, None),
    ("7", "tool-filed", "tool",    "filed",       -1.2, 1.5, None),
    ("7", "item",       "tool",    "item",         0.2, 2.5, None),
    ("8", "morning",    "themes",  "morning",      0.2, 0.5, None),
    ("8", "focus-t",    "themes",  "focus",        0.2, 0.5, None),
    ("8", "evening",    "themes",  "evening",      0.2, 0.5, None),
    ("8", "forest",     "themes",  "forest",       0.2, 0.5, None),
    ("8", "terminal",   "themes",  "terminal",     0.2, 0.5, None),
    ("8", "paper",      "themes",  "paper",        0.2, 0.5, None),
    ("8", "neon",       "themes",  "neon",         0.2, 1.0, None),
]
CARD = 5.5
TITLES = {  # scene: the words at the bottom of the picture
    "1": "A SECOND BRAIN, ON YOUR COMPUTER", "2": "CAPTURE ANYTHING", "3": "THE ARCHIVIST KEEPS THE DOOR",
    "4": "A GRAPH WITH NO BOTTOM", "5": "FIVE VIEWS · TIME YOU CAN PLAY", "6": "ASK · WITH ITS SOURCES",
    "7": "EVERY AI TOOL · YOUR RULES", "8": "SEVEN THEMES",
}
VOICE = {"1": ("v01", 0.6), "2": ("v02", 0.3), "3": ("v03", 0.2), "4": ("v04", 0.3), "5": ("v05", 0.3), "6": ("v06", 0.3),
         "7": ("v07", 0.3), "8": ("v08", 0.2), "card": ("v09", 1.0)}   # the take, and seconds after its scene starts


def run(args: list) -> None:
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y"] + args, check=True)


def marks(step: str) -> dict:
    out = {}
    for line in open(os.path.join(CAP, step, "marks.txt"), encoding="utf-8"):
        p = line.split()
        if len(p) >= 3 and p[0] == "mark":
            out[p[1]] = int(p[2])
    return out


def shot(n: int, name: str, step: str, start: int, seconds: float, move) -> str:
    frames = int(round(seconds * FPS))
    out = os.path.join(WORK, f"shot-{n:02d}-{name}.mp4")
    src = os.path.join(CAP, step, "frame%08d.png")
    if move:
        (x, y, w, h), zoom = move
        cx, cy, k = x + w / 2, y + h / 2, 4
        p = f"(clip(on/{frames},0,1))"
        e = f"({p}*{p}*(3-2*{p}))"                      # eased 0..1 over the shot
        z = f"(1+({zoom}-1)*{e})"
        vx = f"clip({cx * k}-iw/{z}/2,0,iw-iw/{z})"
        vy = f"clip({cy * k}-ih/{z}/2,0,ih-ih/{z})"
        vf = f"scale={W * k}:{H * k}:flags=bicubic,zoompan=z='{z}':x='{vx}':y='{vy}':d=1:s={W}x{H}:fps={FPS},format=yuv420p"
    else:
        vf = "format=yuv420p"
    run(["-framerate", str(FPS), "-start_number", str(start), "-i", src, "-frames:v", str(frames), "-vf", vf,
         "-c:v", "libx264", "-crf", "12", "-preset", "fast", out])
    return out


def card() -> str:
    """The closing card: the logo on the website's ground (its words are titles, added with the others)."""
    out = os.path.join(WORK, "shot-card.mp4")
    logo = os.path.join(WORK, "logo.png")
    vf = (f"[1:v]format=rgba,fade=t=in:st=0.35:d=0.5:alpha=1[logo];[0:v][logo]overlay=x='(W-w)/2':y='190-(1-min(1,max(0,(t-0.35)/0.5)))*24':format=auto,"
          f"format=yuv420p[v]")
    run(["-f", "lavfi", "-i", f"color=c={BG}:s={W}x{H}:r={FPS}:d={CARD}", "-loop", "1", "-framerate", str(FPS), "-t", str(CARD), "-i", logo,
         "-filter_complex", vf, "-map", "[v]", "-frames:v", str(int(CARD * FPS)), "-c:v", "libx264", "-crf", "12", "-preset", "fast", out])
    return out


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%").replace(",", "\\,")


def title(text: str, t0: float, t1: float, y: str, size: int, colour: str = "white", box: bool = True, fade: float = 0.3, font: str = FONT) -> str:
    a = f"if(lt(t\\,{t0}+{fade})\\,(t-{t0})/{fade}\\,if(gt(t\\,{t1}-{fade})\\,({t1}-t)/{fade}\\,1))"
    b = ":box=1:boxcolor=0x1b283c@0.82:boxborderw=16|28" if box else ""
    return (f"drawtext=fontfile='{font}':text='{esc(text)}':fontsize={size}:fontcolor={colour}:x=(w-tw)/2:y={y}"
            f":alpha='{a}':enable='between(t\\,{t0}\\,{t1})'{b}")


def main() -> None:
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    mk = {s: marks(s) for s in sorted({s[2] for s in SHOTS})}
    files, starts, scene_start, t = [], {}, {}, 0.0
    for n, (scene, name, step, mark, after, seconds, move) in enumerate(SHOTS, 1):
        if mark not in mk[step]:
            sys.exit(f"no mark « {mark} » in step {step}: film it again (tools/film.sh {step})")
        files.append(shot(n, name, step, mk[step][mark] + int(round(after * FPS)), seconds, move))
        starts[name] = t
        scene_start.setdefault(scene, t)
        t += seconds
    t_card = t
    files.append(card())
    total = t_card + CARD
    with open(os.path.join(WORK, "list.txt"), "w", encoding="utf-8") as f:
        f.writelines(f"file '{p}'\n" for p in files)
    silent = os.path.join(WORK, "picture.mp4")
    run(["-f", "concat", "-safe", "0", "-i", os.path.join(WORK, "list.txt"), "-c", "copy", silent])

    # the titles: one per scene at the bottom of the picture, then the card's words
    order = sorted(scene_start, key=lambda s: scene_start[s])
    ends = {s: (scene_start[order[i + 1]] if i + 1 < len(order) else t_card) for i, s in enumerate(order)}
    # scenes 2 and 3 interleave (typed, filed, dropped, filed): their titles follow their shots
    spans = [("2", starts["typed"], starts["filed"]), ("3", starts["filed"], starts["dropped"]),
             ("2", starts["dropped"], starts["filed-pdf"]), ("3", starts["filed-pdf"], scene_start["4"])]
    spans += [(s, scene_start[s], ends[s]) for s in order if s not in ("2", "3")]
    ts = [title(TITLES[s], a + 0.15, b - 0.05, "h-150", 44) for s, a, b in sorted(spans, key=lambda x: x[1])]
    ts += [
        title("SECOND BRAIN GD", t_card + 0.9, total, "560", 88, box=False, fade=0.4),
        title("Your second brain. Every AI agent. Your rules.", t_card + 1.3, total, "690", 46, colour=MINT, box=False, fade=0.4, font=FONT_LIGHT),
        title("OPEN SOURCE · MIT", t_card + 1.8, total, "790", 30, colour=WARM, box=False, fade=0.4),
        title("sonixz.github.io/gd-project/second-brain", t_card + 2.1, total, "850", 28, colour=MUTED, box=False, fade=0.4, font=FONT_LIGHT),
    ]
    vchain = "[0:v]" + ",".join(ts) + f",fade=t=in:st=0:d=0.6,fade=t=out:st={total - 0.7:.3f}:d=0.7[v]"

    # the sound: the bed under the voice (it steps back when the voice speaks), the nine takes on their scenes,
    # and the app's own effects where the app plays them (a filing, an approval, a theme's switch)
    vo = [(take, (t_card if scene == "card" else scene_start[scene]) + after) for scene, (take, after) in VOICE.items()]
    vo[2] = (vo[2][0], starts["filed"] + 0.2)   # scene 3's line starts on the first receipt
    fx = [("note_create", starts["filed"] + 1.15, 0.5), ("note_create", starts["filed-pdf"] + 0.3, 0.5), ("confirm", starts["approved"] + 0.2, 0.5),
          ("note_create", starts["tool-filed"] + 1.2, 0.5), ("whoosh", scene_start["4"], 0.3), ("whoosh", scene_start["5"], 0.3)]
    fx += [("theme_switch", starts[n], 0.22) for n in ("focus-t", "evening", "forest", "terminal", "paper", "neon")]
    ai = ["-i", os.path.join(AUDIO, "music.mp3")]
    parts = []
    for j, (take, at) in enumerate(vo):
        ai += ["-i", os.path.join(AUDIO, f"vo-{take}.mp3")]
        ms = int(at * 1000)
        parts.append(f"[{j + 2}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[v{j}]")
    for j, (name, at, vol) in enumerate(fx):
        ai += ["-i", os.path.join(SFX, f"{name}.mp3")]
        ms = int(max(0.0, at) * 1000)
        parts.append(f"[{j + 2 + len(vo)}:a]aresample=48000,aformat=channel_layouts=stereo,volume={vol},adelay={ms}|{ms}[f{j}]")
    vmix = "".join(f"[v{j}]" for j in range(len(vo)))
    fmix = "".join(f"[f{j}]" for j in range(len(fx)))
    shift = float(os.environ.get("MUSIC_SHIFT", "0"))   # seconds cut from the bed's start, to land its last hit on the card
    achain = ";".join(parts) + ";" + (
        f"{vmix}amix=inputs={len(vo)}:normalize=0,apad[voice];[voice]asplit=2[voice1][voice2];"
        f"[1:a]atrim=start={shift},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,volume=0.6,afade=t=in:st=0:d=0.4,afade=t=out:st={total - 1.8:.3f}:d=1.8[music];"
        f"[music][voice2]sidechaincompress=threshold=0.03:ratio=6:attack=15:release=350[bed];"
        f"{fmix}amix=inputs={len(fx)}:normalize=0[fx];"
        f"[bed][voice1][fx]amix=inputs=3:normalize=0:duration=first,atrim=0:{total:.3f},loudnorm=I=-14:TP=-1.5:LRA=9[a]")

    master = os.path.join(OUT, "second-brain-showcase.mp4")
    run(["-i", silent] + ai + ["-filter_complex", vchain + ";" + achain, "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
                                "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(FPS),
                                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", master])
    json.dump({"total": total, "card": t_card, "shots": starts, "scenes": scene_start, "voice": dict(vo),
               "effects": [[n, round(a, 2)] for n, a, _ in fx], "marks": mk}, open(os.path.join(WORK, "timeline.json"), "w"), indent=1)
    print(f"master: {master} ({total:.2f} s)")


if __name__ == "__main__":
    main()
