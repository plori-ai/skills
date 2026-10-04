#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 INPUT OUTPUT.mp4" >&2
  exit 2
fi

input=$1
output=$2

command -v ffmpeg >/dev/null
command -v ffprobe >/dev/null
[[ -f "$input" ]] || { echo "input not found: $input" >&2; exit 1; }

has_audio=$(ffprobe -v error -select_streams a:0 -show_entries stream=index -of csv=p=0 "$input" | head -n 1)

args=(-y -i "$input" -map 0:v:0 -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" -movflags +faststart)
if [[ -n "$has_audio" ]]; then
  args+=(-map 0:a:0 -c:a aac -b:a 192k)
else
  args+=(-an)
fi
args+=("$output")

ffmpeg "${args[@]}"
ffprobe -v error -show_entries stream=codec_name,codec_type,width,height,r_frame_rate -show_entries format=duration,size -of json "$output"
