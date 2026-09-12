"""LangChain tool for reading lightweight metadata from an Instagram post."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from langchain.tools import tool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSPECT_SCRIPT = PROJECT_ROOT / "insta_scraper" / "inspect-instagram.mjs"


class InstagramPostInspectionError(RuntimeError):
    """Raised when Instagram metadata cannot be inspected."""


def _validated_instagram_url(value: str) -> tuple[str, str]:
    parts = urlsplit(value.strip())
    hostname = (parts.hostname or "").lower()
    is_instagram = hostname == "instagram.com" or hostname.endswith(".instagram.com")
    match = re.fullmatch(r"/(p|reel|reels|tv)/([A-Za-z0-9_-]+)/?", parts.path)

    if parts.scheme != "https" or not is_instagram or match is None:
        raise ValueError("Expected a public HTTPS Instagram post or Reel URL")

    post_type, shortcode = match.groups()
    return f"https://www.instagram.com/{post_type}/{shortcode}/", shortcode


def _inspect_instagram_post(instagram_url: str) -> dict[str, Any]:
    normalized_url, shortcode = _validated_instagram_url(instagram_url)
    node = shutil.which("node")
    if node is None:
        raise InstagramPostInspectionError("Required executable not found: node")
    if not INSPECT_SCRIPT.is_file():
        raise InstagramPostInspectionError(
            f"Instagram inspection script not found: {INSPECT_SCRIPT}"
        )

    with tempfile.TemporaryDirectory(prefix=f"instagram-post-{shortcode}-") as temp_name:
        dom_path = Path(temp_name) / "instagram-dom.html"
        try:
            result = subprocess.run(
                [
                    node,
                    str(INSPECT_SCRIPT),
                    normalized_url,
                    "--out",
                    str(dom_path),
                ],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                check=False,
                timeout=90,
            )
        except subprocess.TimeoutExpired as error:
            raise InstagramPostInspectionError(
                "Instagram inspection timed out after 90 seconds"
            ) from error
        except OSError as error:
            raise InstagramPostInspectionError(
                f"Could not start Instagram inspection: {error}"
            ) from error

    if result.returncode != 0:
        detail = (
            result.stderr.strip() or result.stdout.strip() or "No error output"
        )[-4000:]
        raise InstagramPostInspectionError(
            f"Instagram inspection failed:\n{detail}"
        )

    try:
        metadata = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise InstagramPostInspectionError(
            "Instagram inspection returned unreadable JSON"
        ) from error

    if not isinstance(metadata, dict):
        raise InstagramPostInspectionError(
            "Instagram inspection returned an unexpected result"
        )

    description = metadata.get("description")
    thumbnail_url = metadata.get("thumbnailUrl")
    if not description and not thumbnail_url:
        raise InstagramPostInspectionError(
            "No description or thumbnail was found; the post may be private or unavailable"
        )

    return {
        "source_url": normalized_url,
        "shortcode": shortcode,
        "description": description,
        "thumbnail_url": thumbnail_url,
    }


@tool("get_instagram_post_details")
def get_instagram_post_details(instagram_url: str) -> dict[str, Any]:
    """Get the description and thumbnail URL for a public Instagram post or Reel.

    This inspects post metadata only and does not download or analyze the video.
    Its structured result is context for the assistant, not a user-facing answer.

    Args:
        instagram_url: Full HTTPS URL of a public Instagram post or Reel.
    """
    return _inspect_instagram_post(instagram_url)
