#!/usr/bin/env bash
# Runs tools/voice_bench.py with the engine's venv (needs websockets) and the
# OPENAI_API_KEY from the encrypted .env (dotenvx). Costs a few cents at most.
set -euo pipefail
cd "$(dirname "$0")/.."
HOME_DIR="${SBGD_HOME:-$HOME/.local/share/second-brain-gd}"
PY="${VENV_PY:-$HOME_DIR/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  echo "No engine venv at $PY. Run setup once (python3 engine/bootstrap.py setup --no-start) or set VENV_PY." >&2
  exit 2
fi
exec "${DOTENVX:-$HOME/.local/bin/dotenvx}" run -q -- "$PY" tools/voice_bench.py "$@"
