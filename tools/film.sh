#!/usr/bin/env bash
# Films the real app with Godot's movie mode, on a private virtual display (Xvfb): no window opens on the desktop.
# For the showcase film: see video-production/README.md.
#   tools/film.sh <step>…     one run per step (the steps are the film_* functions of tools/film.gd)
#   tools/film.sh --list      the steps
# For each step, in $FILM_OUT/<step>/ (default ~/.cache/sbgd-film/captures, outside the repository: a step is
# hundreds of megabytes): frame%08d.png at 1920x1080, thirty a second; frame.wav, the app's own sound; marks.txt,
# « mark <name> <frame> » lines the cut is made from.
# The app is installed once, without filming, in a base home (~/.cache/sbgd-film/home-base: the English showcase
# Brain, never the user's own); each step films a fresh copy of it. FILM_FRESH=1 installs it again.
# FILM_STILLS=1: no film, one picture per mark in <step>/shots/ (a quick look at the framing, in real time).
# A scripted archivist and no key by default. FILM_REAL=1: the real archivist, with the OpenAI key of the
# environment (run it under dotenvx: `dotenvx run -q -f .env -- tools/film.sh <step>`; the key is never printed).
set -euo pipefail
cd "$(dirname "$0")/.."
GODOT="${GODOT:-godot}"
SIZE="${FILM_SIZE:-1920x1080}"
CACHE="${FILM_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/sbgd-film}"
OUT="${FILM_OUT:-$CACHE/captures}"
BASE="$CACHE/home-base"
PORT="${SBGD_PORT:-18770}"

if [[ "${1:-}" == "--list" ]]; then
  grep -oE '^func film_[a-z_0-9]+' tools/film.gd | sed 's/func film_//; s/_/-/g'
  exit 0
fi
[[ $# -ge 1 ]] || { echo "usage: tools/film.sh <step>…   (tools/film.sh --list)" >&2; exit 2; }
# Godot's movie mode films at the project's window size, not at --resolution: a passing override.cfg sets it.
[[ -e override.cfg ]] && { echo "override.cfg exists: not mine to replace" >&2; exit 2; }
source tools/vdisplay.sh
vdisplay_start || { echo "no Xvfb available (see the-ticket-system tools/setup-xvfb.sh)" >&2; exit 2; }
TMP_HOME=""
trap 'vdisplay_stop; rm -f override.cfg; [[ -n "$TMP_HOME" ]] && rm -rf "$TMP_HOME"' EXIT
printf '[display]\nwindow/size/viewport_width=%s\nwindow/size/viewport_height=%s\nwindow/size/window_width_override=%s\nwindow/size/window_height_override=%s\n' \
  "${SIZE%x*}" "${SIZE#*x}" "${SIZE%x*}" "${SIZE#*x}" > override.cfg
"$GODOT" --headless --path . --import >/dev/null 2>&1 || true

# run <home> <step> <log> [movie options…]
run() {
  local home="$1" step="$2" log="$3"; shift 3
  local keys=(-u OPENAI_ADMIN_KEY -u ELEVENLABS_API_KEY)   # the app is given the one key it needs, or none
  [[ "${FILM_REAL:-}" == "1" ]] || keys+=(-u OPENAI_API_KEY)
  DISPLAY="$VDISPLAY" WAYLAND_DISPLAY="" SBGD_UI_LANG=en SBGD_HOME="$home" SBGD_PORT="$PORT" SBGD_SHOT_SIZE="$SIZE" \
    SBGD_CAPTURE_DIR="$OUT/$step/shots" SBGD_FILM_STEP="$step" SBGD_MARKS="$OUT/$step/marks.txt" \
    SBGD_KEYRING_SERVICE=SecondBrainGD-film env "${keys[@]}" \
    "$GODOT" --display-driver x11 --audio-driver Dummy --rendering-driver opengl3 --resolution "$SIZE" --path . "$@" \
    --script res://tools/film.gd > "$log" 2>&1 || true
}

if [[ -n "${FILM_FRESH:-}" || ! -f "$BASE/.film-ready" ]]; then
  echo "== installing the app once in $BASE (not filmed)"
  rm -rf "$BASE"; mkdir -p "$BASE" "$OUT/prepare"
  run "$BASE" prepare "$OUT/prepare/run.log"
  grep -q "^mark open " "$OUT/prepare/run.log" || { echo "the Brain never opened: $OUT/prepare/run.log" >&2; grep -E "ERROR|SCRIPT" "$OUT/prepare/run.log" | head -5 >&2; exit 1; }
  touch "$BASE/.film-ready"
fi

for step in "$@"; do
  echo "== filming $step"
  rm -rf "$OUT/$step"; mkdir -p "$OUT/$step"
  TMP_HOME="$(mktemp -d -t sbgd-film-XXXX)"
  cp -a "$BASE/." "$TMP_HOME/"
  [[ "${FILM_REAL:-}" == "1" && -z "${OPENAI_API_KEY:-}" ]] && { echo "FILM_REAL=1 without a key in the environment: run under dotenvx" >&2; exit 2; }
  if [[ "${FILM_STILLS:-}" == "1" ]]; then   # no film: one picture per mark in <step>/shots/, in real time
    FILM_REAL="${FILM_REAL:-}" FILM_STILLS=1 run "$TMP_HOME" "$step" "$OUT/$step/run.log"
  else
    FILM_REAL="${FILM_REAL:-}" run "$TMP_HOME" "$step" "$OUT/$step/run.log" --write-movie "$OUT/$step/frame.png" --fixed-fps "${FILM_FPS:-30}"
  fi
  rm -rf "$TMP_HOME"; TMP_HOME=""
  grep -E "^mark |ERROR|SCRIPT" "$OUT/$step/run.log" | head -40 || true
  echo "   $(find "$OUT/$step" -maxdepth 1 -name 'frame*.png' | wc -l) frames, sound: $(ls "$OUT/$step"/frame.wav 2>/dev/null || echo none)"
done
