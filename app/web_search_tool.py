"""LangChain tool for a general web search through the Serper API."""

from __future__ import annotations

import json
import os
import ssl
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi
from dotenv import load_dotenv
from langchain.tools import tool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERPER_SEARCH_URL = "https://google.serper.dev/search"

load_dotenv(PROJECT_ROOT / ".env")


class SerperSearchError(RuntimeError):
    """Raised when a Serper web search cannot be completed."""


def _run_serper_search(query: str, limit: int = 10) -> dict[str, Any]:
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("Search query must not be empty")
    if not 1 <= limit <= 100:
        raise ValueError("Search limit must be between 1 and 100")

    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        raise SerperSearchError(
            "SERPER_API_KEY is missing from the environment or project .env file"
        )

    body = json.dumps({"q": normalized_query, "num": limit}).encode("utf-8")
    request = Request(
        SERPER_SEARCH_URL,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-API-KEY": api_key,
        },
    )
    ssl_context = ssl.create_default_context(cafile=certifi.where())

    try:
        with urlopen(request, timeout=30.0, context=ssl_context) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as error:
        raise SerperSearchError(
            f"Serper search failed with HTTP status {error.code}"
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        reason = getattr(error, "reason", error)
        raise SerperSearchError(
            f"Could not reach the Serper search API: {reason}"
        ) from error

    try:
        result = json.loads(payload)
    except json.JSONDecodeError as error:
        raise SerperSearchError("Serper returned invalid JSON") from error

    if not isinstance(result, dict):
        raise SerperSearchError("Serper returned an unexpected response")
    return result


@tool("web_search", return_direct=True)
def web_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Search the public web with Google via Serper and return its JSON response.

    Args:
        query: Natural-language web search query.
        limit: Requested result count, from 1 to 100.
    """
    return _run_serper_search(query, limit)
