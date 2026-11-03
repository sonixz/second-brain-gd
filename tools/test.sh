#!/usr/bin/env bash
# Runs every automated test on Linux/macOS (or WSL):
#   1. Python unit + integration tests (real venv, real API process)
#   2. Godot headless: project loads, then the full UI flow end to end
# Needs network access to PyPI on the first run (pip cache afterwards).
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
GODOT="${GODOT:-godot}"

echo "== Python tests ($($PY --version))"
"$PY" -m unittest discover -s tests/python -t . -v 2>&1 | tail -n 25

if ! command -v "$GODOT" >/dev/null 2>&1; then
  echo "== Godot not found (set GODOT=/path/to/godot) — skipping Godot tests"
  exit 0
fi
echo "== Godot import / load check ($("$GODOT" --version))"
"$GODOT" --headless --path . --import >/dev/null 2>&1 || true
LOAD_LOG="$("$GODOT" --headless --path . --quit-after 30 2>&1 || true)"
# "resources still in use at exit" comes from --quit-after stopping the engine while
# the audio thread still holds the playing track (benign shutdown race); ignore only that.
if grep -E "SCRIPT ERROR|Parse Error|ERROR:" <<<"$LOAD_LOG" | grep -v "resources still in use at exit"; then
  echo "load check FAILED"; exit 1
fi
echo "project loads without script errors"

echo "== Godot end-to-end"
TMP_HOME="$(mktemp -d -t sbgd-godot-XXXX)"
trap 'rm -rf "$TMP_HOME"' EXIT
SBGD_HOME="$TMP_HOME" SBGD_PORT="${SBGD_TEST_PORT:-18765}" SBGD_PYTHON="${SBGD_PYTHON:-$PY}" \
  "$GODOT" --headless --path . --script res://tests/godot/test_runner.gd
