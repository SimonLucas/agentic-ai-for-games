#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
./build.sh

# README preview: selected pages from the rebuilt tutorial PDF.
# Update these page numbers if slides are inserted before the examples.
pages=(8 22 27 29 31)
titles=(
  "LLM + Tools through MCP"
  "Griddle search as a tool"
  "Maze evolution in action"
  "One-shot LLM maze generation"
  "Agentic maze generation"
)
crops=(
  "900:420:22:55"
  "900:430:22:60"
  "900:320:22:170"
  "900:420:22:65"
  "900:420:22:65"
)
hold_seconds=2.6
mkdir -p build/preview ../../media

manifest="build/preview-frames.txt"
: > "$manifest"
font_option="font=Sans"
if [[ -f /System/Library/Fonts/Supplemental/Arial.ttf ]]; then
  font_option="fontfile=/System/Library/Fonts/Supplemental/Arial.ttf"
fi
for i in "${!pages[@]}"; do
  page="${pages[$i]}"
  slide="build/preview/slide-$(printf '%02d' "$page")"
  card="build/preview/card-$(printf '%02d' "$i")"
  pdftoppm -f "$page" -l "$page" -png -r 150 -singlefile tutorial.pdf "$slide"
  ffmpeg -hide_banner -loglevel error -y -i "$slide.png" \
    -vf "crop=${crops[$i]},scale=900:390:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2+30:white,drawbox=x=0:y=0:w=iw:h=74:color=0x18344B:t=fill,drawtext=${font_option}:text='${titles[$i]}':fontcolor=white:fontsize=32:x=34:y=18" \
    -frames:v 1 "$card.png"
  printf "file 'preview/card-%02d.png'\nduration %s\n" "$i" "$hold_seconds" >> "$manifest"
done
# The concat demuxer needs the final image twice to retain its duration.
last=$((${#pages[@]} - 1))
printf "file 'preview/card-%02d.png'\n" "$last" >> "$manifest"

palette="build/preview/palette.png"
output="../../media/tutorial_preview.gif"
ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$manifest" \
  -vf "palettegen=max_colors=128" \
  -frames:v 1 "$palette"
ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$manifest" -i "$palette" \
  -filter_complex "[0:v][1:v]paletteuse=dither=bayer:bayer_scale=5" \
  -fps_mode vfr -loop 0 "$output"
printf 'Built %s\n' "$output"
