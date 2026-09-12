"""LangChain tool for the complete Instagram-to-recipe workflow."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from dotenv import load_dotenv
from langchain.tools import tool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD_SCRIPT = PROJECT_ROOT / "insta_scraper" / "download-instagram.mjs"
TRANSCRIBE_SCRIPT = PROJECT_ROOT / "transciber" / "transcribe_audio.py"
FRAME_SCRIPT = PROJECT_ROOT / "framer" / "framer.py"
FRAME_ANALYSIS_SCRIPT = PROJECT_ROOT / "framer" / "analyze_frames.py"
RECIPE_SCRIPT = PROJECT_ROOT / "recipe_extractor" / "extract_recipe.py"

load_dotenv(PROJECT_ROOT / ".env")


class InstagramRecipeWorkflowError(RuntimeError):
    """Raised when one stage of the Instagram recipe workflow fails."""


def _validated_instagram_url(value: str) -> tuple[str, str]:
    parts = urlsplit(value.strip())
    hostname = (parts.hostname or "").lower()
    is_instagram = hostname == "instagram.com" or hostname.endswith(".instagram.com")
    match = re.fullmatch(r"/(p|reel|reels|tv)/([A-Za-z0-9_-]+)/?", parts.path)

    if parts.scheme != "https" or not is_instagram or match is None:
        raise ValueError("Expected a public HTTPS Instagram post or Reel URL")

    post_type, shortcode = match.groups()
    normalized_url = f"https://www.instagram.com/{post_type}/{shortcode}/"
    return normalized_url, shortcode


def _require_executable(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise InstagramRecipeWorkflowError(f"Required executable not found: {name}")
    return executable


def _run_stage(
    name: str,
    command: list[str],
    timeout_seconds: int,
) -> None:
    try:
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise InstagramRecipeWorkflowError(
            f"{name} timed out after {timeout_seconds} seconds"
        ) from error
    except OSError as error:
        raise InstagramRecipeWorkflowError(f"Could not start {name}: {error}") from error

    if result.returncode != 0:
        detail = (
            result.stderr.strip() or result.stdout.strip() or "No error output"
        )[-4000:]
        raise InstagramRecipeWorkflowError(f"{name} failed:\n{detail}")


def _require_file(path: Path, stage: str) -> Path:
    if not path.is_file():
        raise InstagramRecipeWorkflowError(
            f"{stage} did not create its expected file: {path.name}"
        )
    return path


def _run_instagram_recipe_workflow(instagram_url: str) -> dict[str, Any]:
    normalized_url, shortcode = _validated_instagram_url(instagram_url)
    if not os.getenv("OPENAI_API_KEY"):
        raise InstagramRecipeWorkflowError(
            "OPENAI_API_KEY is missing from the environment or project .env file"
        )

    node = _require_executable("node")
    _require_executable("ffmpeg")

    with tempfile.TemporaryDirectory(
        prefix=f"instagram-recipe-{shortcode}-"
    ) as temp_name:
        post_dir = Path(temp_name)
        frames_dir = post_dir / "frames"
        transcript_path = post_dir / "transcript.txt"
        frame_analysis_path = frames_dir / "frame_analysis.json"
        recipe_path = post_dir / "recipe.json"

        _run_stage(
            "Instagram download",
            [node, str(DOWNLOAD_SCRIPT), normalized_url, "--out", str(post_dir)],
            timeout_seconds=180,
        )

        caption_path = _require_file(post_dir / "caption.txt", "Instagram download")
        video_path = post_dir / "video.mp4"
        if not video_path.is_file():
            video_path = _require_file(post_dir / "video-only.mp4", "Instagram download")

        audio_path = post_dir / "audio-only.m4a"
        if not audio_path.is_file():
            audio_path = video_path

        _run_stage(
            "Audio transcription",
            [
                sys.executable,
                str(TRANSCRIBE_SCRIPT),
                str(audio_path),
                "--output",
                str(transcript_path),
            ],
            timeout_seconds=300,
        )
        _require_file(transcript_path, "Audio transcription")

        _run_stage(
            "Frame extraction",
            [
                sys.executable,
                str(FRAME_SCRIPT),
                str(video_path),
                "--output-dir",
                str(frames_dir),
                "--overwrite",
            ],
            timeout_seconds=300,
        )
        frames_manifest = _require_file(frames_dir / "frames.json", "Frame extraction")

        _run_stage(
            "Frame analysis",
            [
                sys.executable,
                str(FRAME_ANALYSIS_SCRIPT),
                str(frames_manifest),
                "--output",
                str(frame_analysis_path),
            ],
            timeout_seconds=1800,
        )
        _require_file(frame_analysis_path, "Frame analysis")

        _run_stage(
            "Recipe extraction",
            [
                sys.executable,
                str(RECIPE_SCRIPT),
                str(caption_path),
                str(transcript_path),
                str(frame_analysis_path),
                "--output",
                str(recipe_path),
            ],
            timeout_seconds=300,
        )
        _require_file(recipe_path, "Recipe extraction")

        try:
            recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise InstagramRecipeWorkflowError(
                "Recipe extraction produced unreadable JSON"
            ) from error

        if not isinstance(recipe, dict) or not {"steps", "ingredients"} <= recipe.keys():
            raise InstagramRecipeWorkflowError(
                "Recipe extraction output is missing steps or ingredients"
            )
        return recipe


@tool(
    "create_recipe_from_instagram", return_direct=True
)
def create_recipe_from_instagram(instagram_url: str) -> dict[str, Any]:
    """Create a structured cooking recipe from a public Instagram post or Reel URL.

    Downloads the post, transcribes its audio, analyzes representative video frames,
    and combines that evidence with the caption. Returns `steps` and `ingredients`.

    Args:
        instagram_url: Full HTTPS URL of a public Instagram post or Reel.
    """
    return _run_instagram_recipe_workflow(instagram_url)
