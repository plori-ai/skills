#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(message)


def atempo_chain(speed: float) -> str:
    factors: list[float] = []
    remaining = speed
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    factors.append(remaining)
    return ",".join(f"atempo={factor:.8g}" for factor in factors)


def main() -> None:
    if len(sys.argv) != 5:
        fail(f"usage: {sys.argv[0]} INPUT KEEP_SECONDS SPEED OUTPUT.mp4")

    input_path = Path(sys.argv[1]).expanduser()
    output_path = Path(sys.argv[4]).expanduser()
    try:
        keep_seconds = float(sys.argv[2])
        speed = float(sys.argv[3])
    except ValueError:
        fail("KEEP_SECONDS and SPEED must be numbers")

    if keep_seconds <= 0 or speed <= 0:
        fail("KEEP_SECONDS and SPEED must be positive")
    if not input_path.is_file():
        fail(f"input not found: {input_path}")
    if input_path.resolve() == output_path.resolve():
        fail("output must differ from input; preserve the original take")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        fail("ffmpeg and ffprobe are required")

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(input_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    streams = json.loads(probe.stdout).get("streams", [])
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)

    command = [
        "ffmpeg", "-y", "-t", f"{keep_seconds:g}", "-i", str(input_path),
        "-map", "0:v:0", "-vf", f"scale=trunc(iw/2)*2:trunc(ih/2)*2,setpts=PTS/{speed:g},fps=30",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
    ]
    if has_audio:
        command += ["-map", "0:a:0", "-af", atempo_chain(speed), "-c:a", "aac", "-b:a", "192k"]
    else:
        command += ["-an"]
    command.append(str(output_path))

    subprocess.run(command, check=True)
    subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,codec_type,width,height,r_frame_rate", "-show_entries", "format=duration,size", "-of", "json", str(output_path)],
        check=True,
    )


if __name__ == "__main__":
    main()
