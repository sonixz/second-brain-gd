#!/usr/bin/env bash
# Captures the website screenshots (English showcase Brain) into docs/screenshots/<name>/ on a private virtual
# X display (Xvfb): no window opens on the desktop. Installs into a temp folder.
#   tools/showcase.sh [name]   (SBGD_SHOT_SIZE=1600x1000 for a larger frame; SBGD_UI_LANG=fr: the French interface;
#   SBGD_CAPTURE_SCRIPT=screens: first run, other views and the engine room, tools/screens.gd)
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="${1:-showcase}"
OUT="$(pwd)/docs/screenshots/$NAME"
GODOT="${GODOT:-godot}"
source tools/vdisplay.sh
vdisplay_start || { echo "no Xvfb available (see the-ticket-system tools/setup-xvfb.sh)" >&2; exit 2; }
trap 'vdisplay_stop; rm -rf "$TMP_HOME"' EXIT
TMP_HOME="$(mktemp -d -t sbgd-showcase-XXXX)"
"$GODOT" --headless --path . --import >/dev/null 2>&1 || true
DISPLAY="$VDISPLAY" WAYLAND_DISPLAY="" SBGD_UI_LANG="${SBGD_UI_LANG:-en}" SBGD_HOME="$TMP_HOME" SBGD_PORT="${SBGD_PORT:-18768}" SBGD_SHOT_SIZE="${SBGD_SHOT_SIZE:-}" SBGD_CAPTURE_DIR="$OUT" \
  env -u OPENAI_API_KEY -u OPENAI_ADMIN_KEY SBGD_KEYRING_SERVICE=SecondBrainGD-showcase "$GODOT" --display-driver x11 --audio-driver Dummy --rendering-driver opengl3 --resolution "${SBGD_SHOT_SIZE:-1280x800}" \
  --path . --script "res://tools/${SBGD_CAPTURE_SCRIPT:-showcase}.gd" 2>&1 | grep -E "captured|ERROR|SCRIPT" || true
ls -1 "$OUT"
