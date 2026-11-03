#!/usr/bin/env bash
# Adapted from real-estate-simulator/tools/sounds.sh (same owner); prompts are this project's own.
# Generate Second Brain GD audio through the ElevenLabs API, from
# tools/audio-prompts.txt, into assets/audio/<path>.mp3. Existing files are
# kept (the generations are not deterministic): --force regenerates, a name
# regenerates that one only.
#
#   tools/audio.sh                # the missing ones
#   tools/audio.sh --force        # everything again
#   tools/audio.sh click theme    # these only (forced)
#
# The key comes from the encrypted .env through dotenvx (ELEVENLABS_API_KEY).
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
DOTENVX="${DOTENVX:-$HOME/.local/bin/dotenvx}"
OUT="assets/audio"
mkdir -p "$OUT"
FORCE=0; ONLY=()
for a in "$@"; do
  case "$a" in
    --force) FORCE=1 ;;
    *) ONLY+=("$a") ;;
  esac
done
if [[ -z "${ELEVENLABS_API_KEY:-}" ]]; then
  # (32) FORCE is "0" or "1", never empty: pass --force only when asked — the first version
  # re-sent --force on the re-exec and regenerated every existing track.
  if [[ "$FORCE" == 1 ]]; then exec "$DOTENVX" run -q -- "$0" --force "${ONLY[@]}"; fi
  exec "$DOTENVX" run -q -- "$0" "${ONLY[@]}"
fi
if [[ -z "${ELEVENLABS_API_KEY:-}" ]]; then
  echo "audio.sh: ELEVENLABS_API_KEY is not set (dotenvx set ELEVENLABS_API_KEY …)" >&2
  exit 1
fi
made=0; kept=0; failed=0
while IFS='|' read -r kind name seconds prompt; do
  [[ -z "$kind" || "$kind" == \#* ]] && continue
  file="$OUT/$name.mp3"; mkdir -p "$(dirname "$file")"
  if [[ ${#ONLY[@]} -gt 0 ]]; then
    hit=0; for o in "${ONLY[@]}"; do [[ "$o" == "$name" ]] && hit=1; done
    [[ "$hit" == 1 ]] || continue
  elif [[ -f "$file" && "$FORCE" == 0 ]]; then
    kept=$((kept + 1)); continue
  fi
  tmp="$file.tmp"
  case "$kind" in
    sfx|amb)
      loop="false"; [[ "$kind" == "amb" ]] && loop="true"
      body=$(python3 -I -c 'import json,sys; print(json.dumps({"text": sys.argv[1], "duration_seconds": float(sys.argv[2]), "prompt_influence": 0.35, "loop": sys.argv[3] == "true"}))' "$prompt" "$seconds" "$loop")
      code=$(curl -s -o "$tmp" -w "%{http_code}" -H "xi-api-key: $ELEVENLABS_API_KEY" -H "Content-Type: application/json" -d "$body" https://api.elevenlabs.io/v1/sound-generation)
      ;;
    music)
      body=$(python3 -I -c 'import json,sys; print(json.dumps({"prompt": sys.argv[1], "music_length_ms": int(float(sys.argv[2]) * 1000)}))' "$prompt" "$seconds")
      code=$(curl -s -o "$tmp" -w "%{http_code}" -H "xi-api-key: $ELEVENLABS_API_KEY" -H "Content-Type: application/json" -d "$body" https://api.elevenlabs.io/v1/music)
      ;;
    *) echo "audio.sh: unknown kind '$kind' for $name" >&2; continue ;;
  esac
  if [[ "$code" == "200" ]] && head -c 3 "$tmp" | grep -q -a -E 'ID3|^\xff' ; then
    mv "$tmp" "$file"
    echo "audio.sh: $kind $name ${seconds}s -> $file ($(stat -c %s "$file") bytes)"
    made=$((made + 1))
  else
    echo "audio.sh: FAILED $kind $name (HTTP $code): $(head -c 200 "$tmp" 2>/dev/null)" >&2
    rm -f "$tmp"; failed=$((failed + 1))
  fi
done < tools/audio-prompts.txt
echo "audio.sh: $made generated, $kept kept, $failed failed"
[[ "$failed" == 0 ]]
