#!/usr/bin/env bash
# Captures the How-to guides (public/howto.html) from the real app, on a private virtual display (Xvfb, no window).
#   tools/howto.sh [--record] [guide ...]      (no guide: all of them)
# Guides marked "real" in tools/howto/guides.py use the real model's answers:
#   --record   the real model answers (OPENAI_API_KEY through dotenvx) and its answers are saved in
#              tools/howto/recordings/<guide>.json; a cost cap per guide is checked afterwards.
#   default    the recording is replayed: same answers, no network, no cost.
# The other guides use the scripted showcase model. Screenshots: docs/screenshots/howto/<guide>/, then WebP in
# public/assets/howto/<guide>/; finally the page is rebuilt (tools/howto/build_page.py).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
RECORD=0
GUIDES=()
for a in "$@"; do
  if [[ "$a" == "--record" ]]; then RECORD=1; else GUIDES+=("$a"); fi
done
[[ ${#GUIDES[@]} -eq 0 ]] && mapfile -t GUIDES < <(python3 tools/howto/guides.py --ids)
GODOT="${GODOT:-godot}"
SIZE="${SBGD_SHOT_SIZE:-1600x1000}"
source tools/vdisplay.sh
vdisplay_start || { echo "no Xvfb available" >&2; exit 2; }
TMP_HOME="$(mktemp -d -t sbgd-howto-XXXX)"
trap 'vdisplay_stop; rm -rf "$TMP_HOME"' EXIT
"$GODOT" --headless --path . --import >/dev/null 2>&1 || true
FAILED=0
for G in "${GUIDES[@]}"; do
  KIND="$(python3 tools/howto/guides.py --kind "$G")"
  OUT="$ROOT/docs/screenshots/howto/$G"
  REC="$ROOT/tools/howto/recordings/$G.json"
  rm -rf "$OUT" "$TMP_HOME/data" "$TMP_HOME/runtime/pages" "$TMP_HOME/showcase-settings.cfg"
  mkdir -p "$OUT"
  PROVIDER=showcase
  RUN=(env -u OPENAI_API_KEY -u OPENAI_ADMIN_KEY)
  if [[ "$KIND" == "real" ]]; then
    if [[ $RECORD -eq 1 ]]; then
      PROVIDER=record
      rm -f "$REC"
      RUN=("$HOME/.local/bin/dotenvx" run --quiet -- env -u OPENAI_ADMIN_KEY)
    else
      PROVIDER=replay
      [[ -f "$REC" ]] || { echo "$G: no recording yet (run tools/howto.sh --record $G)" >&2; FAILED=1; continue; }
    fi
  fi
  echo "== $G ($PROVIDER)"
  "${RUN[@]}" DISPLAY="$VDISPLAY" WAYLAND_DISPLAY="" SBGD_HOME="$TMP_HOME" SBGD_PORT=18769 SBGD_SHOT_SIZE="$SIZE" \
    SBGD_CAPTURE_DIR="$OUT" SBGD_GUIDE="$G" SBGD_ASSISTANT_PROVIDER="$PROVIDER" SBGD_RECORDING="$REC" \
    SBGD_HOWTO_FILES="$ROOT/tools/howto/files" SBGD_OCR=recorded SBGD_OCR_PAGES="$ROOT/tools/howto/files/insurance-renewal-scan.ocr.json" \
    SBGD_KEYRING_SERVICE=SecondBrainGD-howto SBGD_TEST_NO_SHELL=1 \
    "$GODOT" --display-driver x11 --audio-driver Dummy --rendering-driver opengl3 --resolution "$SIZE" \
    --path . --script res://tools/howto.gd 2>&1 | grep -E "captured|step|ERROR|SCRIPT|guide" || true
  python3 tools/howto/guides.py --check "$G" || FAILED=1
  if [[ "$PROVIDER" == "record" ]]; then python3 tools/howto/guides.py --cost "$G" || FAILED=1; fi
done
python3 tools/howto/build_page.py
exit $FAILED
