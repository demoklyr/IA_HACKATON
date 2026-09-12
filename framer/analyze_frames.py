#!/usr/bin/env python3
"""Analyze extracted cooking-video frames with the OpenAI Responses API."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


class VisibleFrameAnalysis(BaseModel):
    on_screen_text: Optional[str] = Field(
        description="Exact text visibly readable in the current frame, or null"
    )
    visible_action: str = Field(
        description="One concise phrase describing only the visibly shown action"
    )
    ingredients_or_tools_visible: list[str]
    is_new_step: bool = Field(
        description="Whether the current frame starts a distinct step versus the prior frame"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze frames listed in an extractor-generated frames.json file."
    )
    parser.add_argument("manifest", type=Path, help="Path to frames.json")
    parser.add_argument(
        "-o", "--output", type=Path,
        help="Output JSON path (default: frame_analysis.json beside the manifest)",
    )
    parser.add_argument("--model", default="gpt-5-nano", help="OpenAI model name")
    parser.add_argument(
        "--detail", choices=("low", "high", "auto"), default="high",
        help="Image detail level (default: high, useful for on-screen text)",
    )
    parser.add_argument(
        "--limit", type=int, help="Analyze only the first N frames (useful for testing)"
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Continue an existing output file, skipping frame IDs already analyzed",
    )
    return parser.parse_args()


def image_data_url(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def load_manifest(path: Path) -> tuple[Path, list[dict]]:
    manifest_path = path.expanduser().resolve()
    if not manifest_path.is_file():
        raise SystemExit(f"Manifest not found: {manifest_path}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames = data.get("frames")
    if not isinstance(frames, list) or not frames:
        raise SystemExit(f"Manifest contains no frames: {manifest_path}")
    return manifest_path, frames


def analyze_frame(
    client: OpenAI,
    model: str,
    detail: str,
    current: dict,
    current_path: Path,
    previous: dict | None,
    previous_path: Path | None,
) -> VisibleFrameAnalysis:
    content: list[dict] = [{
        "type": "input_text",
        "text": f"Analyze CURRENT frame {current['frame_id']} at {current['timestamp_s']} seconds.",
    }]
    if previous is not None and previous_path is not None:
        content.extend([
            {
                "type": "input_text",
                "text": (
                    f"PREVIOUS frame {previous['frame_id']} at "
                    f"{previous['timestamp_s']} seconds (context only):"
                ),
            },
            {
                "type": "input_image",
                "image_url": image_data_url(previous_path),
                "detail": detail,
            },
        ])
    content.extend([
        {"type": "input_text", "text": "CURRENT frame (analyze this one):"},
        {
            "type": "input_image",
            "image_url": image_data_url(current_path),
            "detail": detail,
        },
    ])

    response = client.responses.parse(
        model=model,
        instructions=(
            "You analyze sequential frames from a short-form cooking video in timestamp "
            "order. Describe only what is visibly shown. Do not infer hidden ingredients, "
            "intent, recipe quantities, or actions that are not visible. Transcribe visible "
            "caption text exactly; return null when none is readable. Keep visible_action to "
            "one concise phrase. Set is_new_step true only when the CURRENT frame begins a "
            "distinct cooking step compared with the PREVIOUS frame. If there is no previous "
            "frame, set is_new_step true. A camera-angle change alone is not a new step."
        ),
        input=[{"role": "user", "content": content}],
        text_format=VisibleFrameAnalysis,
    )
    if response.output_parsed is None:
        raise RuntimeError(f"No parsed result returned for frame {current['frame_id']}")
    return response.output_parsed


def save_output(path: Path, model: str, manifest: Path, analyses: list[dict]) -> None:
    result = {
        "source_manifest": str(manifest),
        "model": model,
        "frames": analyses,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    manifest_path, frames = load_manifest(args.manifest)
    output_path = (
        args.output.expanduser().resolve()
        if args.output else manifest_path.parent / "frame_analysis.json"
    )
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be at least 1")
        frames = frames[: args.limit]

    analyses: list[dict] = []
    if args.resume and output_path.is_file():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        analyses = existing.get("frames", [])
    elif output_path.exists():
        raise SystemExit(f"Output already exists: {output_path}. Use --resume or choose -o.")

    completed_ids = {item["frame_id"] for item in analyses}
    client = OpenAI()
    previous_frame: dict | None = None
    previous_path: Path | None = None

    for frame in frames:
        frame_path = manifest_path.parent / frame["file"]
        if not frame_path.is_file():
            raise SystemExit(f"Frame image not found: {frame_path}")
        if frame["frame_id"] in completed_ids:
            previous_frame = frame
            previous_path = frame_path
            continue

        print(f"Analyzing frame {frame['frame_id']} at {frame['timestamp_s']:.3f}s...", flush=True)
        visible = analyze_frame(
            client, args.model, args.detail, frame, frame_path,
            previous_frame, previous_path,
        )
        analyses.append({
            "frame_id": frame["frame_id"],
            "timestamp_s": frame["timestamp_s"],
            **visible.model_dump(),
        })
        analyses.sort(key=lambda item: item["frame_id"])
        save_output(output_path, args.model, manifest_path, analyses)
        previous_frame = frame
        previous_path = frame_path

    print(f"Saved {len(analyses)} frame analyses to {output_path}")


if __name__ == "__main__":
    main()
