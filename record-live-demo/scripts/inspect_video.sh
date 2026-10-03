#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 INPUT [CONTACT_SHEET.png]" >&2
  exit 2
fi

input=$1
contact_sheet=${2:-}

command -v ffprobe >/dev/null
[[ -f "$input" ]] || { echo "input not found: $input" >&2; exit 1; }

ffprobe -v error -show_entries stream=codec_name,codec_type,width,height,r_frame_rate -show_entries format=duration,size -of json "$input"

if [[ -n "$contact_sheet" ]]; then
  command -v ffmpeg >/dev/null
  duration=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$input")
  interval=$(awk -v d="$duration" 'BEGIN { v=d/9; if (v < 0.2) v=0.2; printf "%.6f", v }')
  ffmpeg -loglevel error -y -i "$input" \
    -vf "fps=1/$interval,scale=480:-2,tile=3x3:padding=8:margin=8" \
    -frames:v 1 "$contact_sheet"
  echo "$contact_sheet"
fi
