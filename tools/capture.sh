#!/usr/bin/env bash
# Captures the Loop screens into docs/screenshots/<name>/ on a private virtual
# X display (Xvfb): no window opens on the desktop. Installs into a temp folder.
#   tools/capture.sh [name]
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="${1:-loop-1}"
OUT="$(pwd)/docs/screenshots/$NAME"
GODOT="${GODOT:-godot}"
source tools/vdisplay.sh
vdisplay_start || { echo "no Xvfb available (see the-ticket-system tools/setup-xvfb.sh)" >&2; exit 2; }
trap 'vdisplay_stop; rm -rf "$TMP_HOME"' EXIT
TMP_HOME="$(mktemp -d -t sbgd-capture-XXXX)"
"$GODOT" --headless --path . --import >/dev/null 2>&1 || true
DISPLAY="$VDISPLAY" WAYLAND_DISPLAY="" SBGD_HOME="$TMP_HOME" SBGD_PORT=18767 SBGD_CAPTURE_DIR="$OUT" \
  "$GODOT" --display-driver x11 --audio-driver Dummy --rendering-driver opengl3 --resolution 1280x800 \
  --path . --script res://tools/capture.gd 2>&1 | grep -E "captured|ERROR|SCRIPT" || true
ls -1 "$OUT"
