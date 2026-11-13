#!/usr/bin/env bash
# From the master to what the website serves: a lighter H.264 for the page and a poster picture.
#   video-production/scripts/render.sh <master.mp4> <poster frame.png>
#   → video-production/output/showcase-web.mp4, public/assets/video/showcase.mp4 and showcase-poster.webp
# Two passes at VBR (default 560k) for the picture and ABR (default 64k) for the sound: about 4 MB a minute.
# After agent-manager-gd's video-production/scripts/render.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
FF="${FFMPEG:-$HOME/.local/opt/ffmpeg-n8.1.3-35/bin/ffmpeg}"
MASTER="$(realpath "$1")"; POSTER="$(realpath "$2")"
VBR="${VBR:-560k}"; ABR="${ABR:-64k}"
mkdir -p work output ../public/assets/video
(cd work && "$FF" -hide_banner -loglevel error -y -i "$MASTER" -c:v libx264 -preset veryslow -b:v "$VBR" -tune stillimage \
  -pass 1 -passlogfile x264 -an -f mp4 /dev/null)
(cd work && "$FF" -hide_banner -loglevel error -y -i "$MASTER" -c:v libx264 -preset veryslow -b:v "$VBR" -maxrate 2500k -bufsize 5000k \
  -tune stillimage -pass 2 -passlogfile x264 -profile:v high -level 4.1 -pix_fmt yuv420p -c:a aac -b:a "$ABR" -movflags +faststart ../output/showcase-web.mp4)
cp output/showcase-web.mp4 ../public/assets/video/showcase.mp4
"$FF" -hide_banner -loglevel error -y -i "$POSTER" -c:v libwebp -quality 82 ../public/assets/video/showcase-poster.webp
ls -la output/showcase-web.mp4 ../public/assets/video/ | awk '{print $5, $9}'
