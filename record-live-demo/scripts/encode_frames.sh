#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 FRAMES_DIR CAPTURE_FPS OUTPUT.mp4" >&2
  exit 2
fi

frames_dir=$1
capture_fps=$2
output=$3

command -v ffmpeg >/dev/null
command -v ffprobe >/dev/null
command -v file >/dev/null
[[ -d "$frames_dir" ]] || { echo "frames directory not found: $frames_dir" >&2; exit 1; }

first=$(find "$frames_dir" -maxdepth 1 \( -type f -o -type l \) \( -name 'frame-*.jpg' -o -name 'frame-*.jpeg' -o -name 'frame-*.png' \) | sort | head -n 1)
[[ -n "$first" ]] || { echo "no frame-NNNNNN.jpg or .png files found" >&2; exit 1; }

mime=$(file -L -b --mime-type "$first")
case "$mime" in
  image/jpeg) decoder=mjpeg ;;
  image/png) decoder=png ;;
  *) echo "unsupported frame format: $mime" >&2; exit 1 ;;
esac

case "$first" in
  *.jpg) pattern="$frames_dir/frame-%06d.jpg" ;;
  *.jpeg) pattern="$frames_dir/frame-%06d.jpeg" ;;
  *.png) pattern="$frames_dir/frame-%06d.png" ;;
esac

first_number=${first##*/frame-}
first_number=${first_number%.*}
[[ "$first_number" =~ ^[0-9]{6}$ ]] || { echo "frame names must be frame-NNNNNN.<ext>: $first" >&2; exit 1; }

ffmpeg -y -framerate "$capture_fps" -start_number "$((10#$first_number))" -c:v "$decoder" -i "$pattern" \
  -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=30" \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -movflags +faststart "$output"

ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate -show_entries format=duration,size -of json "$output"
