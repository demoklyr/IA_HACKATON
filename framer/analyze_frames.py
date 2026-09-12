#!/usr/bin/env python3
"""Analyze extracted cooking-video frames with the OpenAI Responses API."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import mimetypes
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

BATCH_SIZE = 4
MAX_CONCURRENT_CALLS = 5


class VisibleFrameAnalysis(BaseModel):
    frame_id: int = Field(description="The frame_id supplied with the frame")
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


class VisibleFrameAnalysisBatch(BaseModel):
    frames: list[VisibleFrameAnalysis] = Field(
        description="One analysis for each CURRENT frame, in the supplied order"
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


async def analyze_frame_batch(
    client: AsyncOpenAI,
    model: str,
    detail: str,
    current_frames: list[tuple[dict, Path]],
    previous: dict | None,
    previous_path: Path | None,
) -> list[VisibleFrameAnalysis]:
    content: list[dict] = []
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
    for current, current_path in current_frames:
        content.extend([
            {
                "type": "input_text",
                "text": (
                    f"CURRENT frame {current['frame_id']} at "
                    f"{current['timestamp_s']} seconds (analyze this one):"
                ),
            },
            {
                "type": "input_image",
                "image_url": image_data_url(current_path),
                "detail": detail,
            },
        ])

    response = await client.responses.parse(
        model=model,
        instructions=(
            "You analyze sequential frames from a short-form cooking video in timestamp "
            "order. Return exactly one analysis for every CURRENT frame, in the same order, "
            "and copy each supplied frame_id exactly. The PREVIOUS frame, when present, is "
            "context for the first CURRENT frame only and must not be returned. Describe only "
            "what is visibly shown. Do not infer hidden ingredients, "
            "intent, recipe quantities, or actions that are not visible. Transcribe visible "
            "caption text exactly; return null when none is readable. Keep visible_action to "
            "one concise phrase. For each CURRENT frame, set is_new_step true only when it "
            "begins a distinct cooking step compared with the immediately preceding image. "
            "For the first image, use the PREVIOUS context frame when supplied; otherwise set "
            "is_new_step true. A camera-angle change alone is not a new step."
        ),
        input=[{"role": "user", "content": content}],
        text_format=VisibleFrameAnalysisBatch,
    )
    if response.output_parsed is None:
        frame_ids = [frame["frame_id"] for frame, _ in current_frames]
        raise RuntimeError(f"No parsed result returned for frames {frame_ids}")

    parsed = response.output_parsed.frames
    expected_ids = [frame["frame_id"] for frame, _ in current_frames]
    actual_ids = [frame.frame_id for frame in parsed]
    if actual_ids != expected_ids:
        raise RuntimeError(
            f"Unexpected frame IDs in response: expected {expected_ids}, got {actual_ids}"
        )
    return parsed


def save_output(path: Path, model: str, manifest: Path, analyses: list[dict]) -> None:
    result = {
        "source_manifest": str(manifest),
        "model": model,
        "frames": analyses,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def pending_batches(
    frames: list[dict], manifest_dir: Path, completed_ids: set[int]
) -> list[tuple[list[tuple[dict, Path]], dict | None, Path | None]]:
    """Build batches without crossing gaps left by resumed analyses."""
    batches: list[tuple[list[tuple[dict, Path]], dict | None, Path | None]] = []
    index = 0
    while index < len(frames):
        if frames[index]["frame_id"] in completed_ids:
            index += 1
            continue

        start = index
        current_frames: list[tuple[dict, Path]] = []
        while (
            index < len(frames)
            and len(current_frames) < BATCH_SIZE
            and frames[index]["frame_id"] not in completed_ids
        ):
            frame = frames[index]
            frame_path = manifest_dir / frame["file"]
            if not frame_path.is_file():
                raise SystemExit(f"Frame image not found: {frame_path}")
            current_frames.append((frame, frame_path))
            index += 1

        previous = frames[start - 1] if start else None
        previous_path = manifest_dir / previous["file"] if previous is not None else None
        if previous_path is not None and not previous_path.is_file():
            raise SystemExit(f"Frame image not found: {previous_path}")
        batches.append((current_frames, previous, previous_path))

    return batches


async def run_analysis(args: argparse.Namespace) -> None:
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
    batches = pending_batches(frames, manifest_path.parent, completed_ids)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CALLS)

    async def analyze_one_batch(client: AsyncOpenAI, batch):
        current_frames, previous, previous_path = batch
        frame_ids = [frame["frame_id"] for frame, _ in current_frames]
        print(f"Analyzing frames {frame_ids}...", flush=True)
        async with semaphore:
            visible = await analyze_frame_batch(
                client, args.model, args.detail, current_frames, previous, previous_path
            )
        return current_frames, visible

    if batches:
        async with AsyncOpenAI() as client:
            tasks = [
                asyncio.create_task(analyze_one_batch(client, batch))
                for batch in batches
            ]
            try:
                for task in asyncio.as_completed(tasks):
                    current_frames, visible_frames = await task
                    timestamps = {
                        frame["frame_id"]: frame["timestamp_s"]
                        for frame, _ in current_frames
                    }
                    analyses.extend({
                        **visible.model_dump(),
                        "timestamp_s": timestamps[visible.frame_id],
                    } for visible in visible_frames)
                    analyses.sort(key=lambda item: item["frame_id"])
                    save_output(output_path, args.model, manifest_path, analyses)
            except BaseException:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise

    print(f"Saved {len(analyses)} frame analyses to {output_path}")


def main() -> None:
    asyncio.run(run_analysis(parse_args()))


if __name__ == "__main__":
    main()
