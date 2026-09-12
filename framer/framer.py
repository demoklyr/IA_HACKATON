#!/usr/bin/env python3
"""Extract representative video frames with FFmpeg and create a manifest."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from PIL import Image


SHOWINFO_RE = re.compile(r"\bn:\s*\d+.*?\bpts_time:\s*([-+\d.eE]+)")
JPEG_FILTER = (
    "scale=1280:1280:force_original_aspect_ratio=decrease:force_divisible_by=2,"
    "format=yuvj420p"
)


@dataclass(frozen=True)
class Candidate:
    timestamp_s: float
    path: Path
    reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract regularly sampled and scene-change frames, remove near-duplicates, "
            "and write frames.json."
        )
    )
    parser.add_argument("video", type=Path, help="Input video file")
    parser.add_argument(
        "-o", "--output-dir", type=Path,
        help="Output directory (default: <video directory>/frames)",
    )
    parser.add_argument(
        "--interval", type=float, default=1.0,
        help="Seconds between regular samples (default: 1.0)",
    )
    parser.add_argument(
        "--scene-threshold", type=float, default=0.35,
        help="FFmpeg scene-change score from 0 to 1 (default: 0.35)",
    )
    parser.add_argument(
        "--duplicate-distance", type=int, default=6,
        help="Maximum 64-bit dHash distance considered a duplicate (default: 6)",
    )
    parser.add_argument(
        "--duplicate-color-distance", type=float, default=30.0,
        help="Maximum average RGB distance considered a duplicate (default: 30)",
    )
    parser.add_argument(
        "--max-frames", type=int, default=120,
        help="Maximum frames to keep after deduplication (default: 120)",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Replace frame files and frames.json previously created in the output directory",
    )
    return parser.parse_args()


def require_executable(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise SystemExit(
            f"{name} is not installed or is not on PATH. "
            "Install FFmpeg first (macOS: brew install ffmpeg)."
        )
    return executable


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Command failed:\n{' '.join(command)}\n\n{detail}")
    return result


def probe_video(ffprobe: str, video: Path) -> dict[str, float | int]:
    result = run([
        ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=avg_frame_rate,nb_frames,width,height:format=duration",
        "-of", "json", str(video),
    ])
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise SystemExit(f"No video stream found in {video}")

    stream = streams[0]
    duration = float(data.get("format", {}).get("duration") or 0)
    frame_rate = stream.get("avg_frame_rate", "0/1")
    fps = float(Fraction(frame_rate)) if frame_rate != "0/0" else 0.0
    return {
        "duration_s": duration,
        "fps": fps,
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "total_frames": int(stream["nb_frames"]) if stream.get("nb_frames", "").isdigit() else 0,
    }


def timestamps_from_showinfo(stderr: str) -> list[float]:
    return [float(match.group(1)) for match in SHOWINFO_RE.finditer(stderr)]


def extract_sequence(
    ffmpeg: str,
    video: Path,
    output_pattern: Path,
    video_filter: str,
) -> list[Candidate]:
    result = run([
        ffmpeg, "-hide_banner", "-loglevel", "info", "-i", str(video),
        "-vf", video_filter, "-fps_mode", "vfr", "-q:v", "2", str(output_pattern),
    ])
    timestamps = timestamps_from_showinfo(result.stderr)
    glob_pattern = output_pattern.name.replace("%06d", "*")
    files = sorted(output_pattern.parent.glob(glob_pattern))
    if len(files) != len(timestamps):
        raise RuntimeError(
            f"FFmpeg created {len(files)} frames but reported {len(timestamps)} timestamps."
        )
    reason = "scene_change" if output_pattern.name.startswith("scene_") else "regular_sample"
    return [Candidate(timestamp, path, reason) for timestamp, path in zip(timestamps, files)]


def extract_last_frame(
    ffmpeg: str, video: Path, destination: Path, duration_s: float
) -> Candidate:
    run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-sseof", "-1",
        "-i", str(video), "-frames:v", "1", "-vf",
        f"reverse,{JPEG_FILTER}",
        "-q:v", "2", str(destination),
    ])
    return Candidate(max(0.0, duration_s - 0.05), destination, "last_frame")


def image_signature(path: Path) -> tuple[int, tuple[int, int, int]]:
    with Image.open(path) as image:
        grayscale = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        pixels = list(grayscale.getdata())
        average_color = image.convert("RGB").resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    bits = 0
    for row in range(8):
        offset = row * 9
        for column in range(8):
            bits = (bits << 1) | int(
                pixels[offset + column] > pixels[offset + column + 1]
            )
    return bits, average_color


def hamming_distance(first: int, second: int) -> int:
    """Return differing bits, including on the project's Python 3.9 runtime."""
    return bin(first ^ second).count("1")


def deduplicate(
    candidates: list[Candidate],
    duplicate_distance: int,
    duplicate_color_distance: float,
    max_frames: int,
) -> list[Candidate]:
    candidates = sorted(candidates, key=lambda item: (item.timestamp_s, item.reason))
    kept: list[Candidate] = []
    last_kept_signature: tuple[int, tuple[int, int, int]] | None = None

    for candidate in candidates:
        candidate_signature = image_signature(candidate.path)
        is_boundary = candidate.reason in {"first_frame", "last_frame"}
        hash_distance = (
            hamming_distance(candidate_signature[0], last_kept_signature[0])
            if last_kept_signature is not None else math.inf
        )
        color_distance = (
            math.dist(candidate_signature[1], last_kept_signature[1])
            if last_kept_signature is not None else math.inf
        )
        # Compare adjacent selections only. A similar-looking setup may legitimately
        # reappear later in the recipe and should not be removed globally.
        is_duplicate = (
            hash_distance <= duplicate_distance
            and color_distance <= duplicate_color_distance
        )
        if is_boundary or not is_duplicate:
            kept.append(candidate)
            last_kept_signature = candidate_signature

    if len(kept) <= max_frames:
        return kept

    boundaries = [item for item in kept if item.reason in {"first_frame", "last_frame"}]
    others = [item for item in kept if item not in boundaries]
    available = max(0, max_frames - len(boundaries))
    if available and others:
        indexes = {
            round(index * (len(others) - 1) / max(available - 1, 1))
            for index in range(available)
        }
        others = [item for index, item in enumerate(others) if index in indexes]
    else:
        others = []
    return sorted(boundaries + others, key=lambda item: item.timestamp_s)[:max_frames]


def prepare_output(output_dir: Path, overwrite: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = list(output_dir.glob("frame_*.jpg"))
    manifest = output_dir / "frames.json"
    if (existing or manifest.exists()) and not overwrite:
        raise SystemExit(
            f"Output already exists in {output_dir}. Use --overwrite to replace generated files."
        )
    if overwrite:
        for path in existing:
            path.unlink()
        manifest.unlink(missing_ok=True)


def main() -> None:
    args = parse_args()
    if args.interval <= 0:
        raise SystemExit("--interval must be greater than zero")
    if not 0 <= args.scene_threshold <= 1:
        raise SystemExit("--scene-threshold must be between 0 and 1")
    if not 0 <= args.duplicate_distance <= 64:
        raise SystemExit("--duplicate-distance must be between 0 and 64")
    if args.duplicate_color_distance < 0:
        raise SystemExit("--duplicate-color-distance cannot be negative")
    if args.max_frames < 2:
        raise SystemExit("--max-frames must be at least 2")

    video = args.video.expanduser().resolve()
    if not video.is_file():
        raise SystemExit(f"Video not found: {video}")
    output_dir = (
        args.output_dir.expanduser().resolve() if args.output_dir else video.parent / "frames"
    )
    prepare_output(output_dir, args.overwrite)

    ffmpeg = require_executable("ffmpeg")
    ffprobe = require_executable("ffprobe")
    metadata = probe_video(ffprobe, video)
    scale = JPEG_FILTER

    with tempfile.TemporaryDirectory(prefix="frame-extraction-") as temp_name:
        temp_dir = Path(temp_name)
        regular_filter = f"fps=1/{args.interval},mpdecimate,{scale},showinfo"
        scene_filter = f"select=gt(scene\\,{args.scene_threshold}),{scale},showinfo"
        candidates = extract_sequence(
            ffmpeg, video, temp_dir / "regular_%06d.jpg", regular_filter
        )
        candidates.extend(
            extract_sequence(ffmpeg, video, temp_dir / "scene_%06d.jpg", scene_filter)
        )
        if candidates:
            first = min(candidates, key=lambda item: item.timestamp_s)
            candidates.append(Candidate(first.timestamp_s, first.path, "first_frame"))
        candidates.append(
            extract_last_frame(ffmpeg, video, temp_dir / "last.jpg", float(metadata["duration_s"]))
        )

        selected = deduplicate(
            candidates,
            args.duplicate_distance,
            args.duplicate_color_distance,
            args.max_frames,
        )
        manifest_frames = []
        for frame_id, candidate in enumerate(selected):
            filename = f"frame_{frame_id:04d}.jpg"
            shutil.copy2(candidate.path, output_dir / filename)
            manifest_frames.append({
                "frame_id": frame_id,
                "timestamp_s": round(candidate.timestamp_s, 3),
                "file": filename,
                "selection_reason": candidate.reason,
            })

    manifest = {
        "source_video": str(video),
        **metadata,
        "settings": {
            "sample_interval_s": args.interval,
            "scene_threshold": args.scene_threshold,
            "duplicate_hash_distance": args.duplicate_distance,
            "duplicate_color_distance": args.duplicate_color_distance,
            "max_frames": args.max_frames,
        },
        "frames": manifest_frames,
    }
    manifest_path = output_dir / "frames.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(manifest_frames)} representative frames to {output_dir}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
