#!/usr/bin/env bash
# A piece of one filmed step as an MP4, with the app's own sound: to look at a scene, or for a rough cut.
#   video-production/scripts/clip.sh <step> <mark> <seconds> <out.mp4> [seconds after the mark, default 0]
# Reads $FILM_OUT/<step>/ (tools/film.sh): frame%08d.png, frame.wav, marks.txt. The film is thirty frames a
# second from the engine's first frame, so frame N is N/30 seconds into frame.wav.
set -euo pipefail
FF="${FFMPEG:-$HOME/.local/opt/ffmpeg-n8.1.3-35/bin/ffmpeg}"
OUT="${FILM_OUT:-${FILM_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/sbgd-film}/captures}"
STEP="$1"; MARK="$2"; SECONDS_="$3"; FILE="$4"; AFTER="${5:-0}"
DIR="$OUT/$STEP"
FPS="${FILM_FPS:-30}"
F=$(awk -v m="$MARK" '$1=="mark" && $2==m {print $3; exit}' "$DIR/marks.txt")
[[ -n "$F" ]] || { echo "no mark « $MARK » in $DIR/marks.txt: $(awk '{print $2}' "$DIR/marks.txt" | tr '\n' ' ')" >&2; exit 2; }
FRAMES=("$DIR"/frame*.png); FIRST="$(basename "${FRAMES[0]}" .png)"; FIRST=$((10#${FIRST#frame}))
START=$(python3 -c "print(int($F + $AFTER * $FPS))")
AT=$(python3 -c "print(($START - $FIRST) / $FPS)")
mkdir -p "$(dirname "$FILE")"
"$FF" -hide_banner -loglevel error -y -framerate "$FPS" -start_number "$START" -i "$DIR/frame%08d.png" \
  -ss "$AT" -i "$DIR/frame.wav" -t "$SECONDS_" -map 0:v -map 1:a \
  -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -c:a aac -b:a 160k -movflags +faststart "$FILE"
ls -la "$FILE" | awk '{print $5, $9}'
