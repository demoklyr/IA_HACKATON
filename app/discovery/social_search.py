import asyncio
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.web_search_tool import web_search

from .models import CandidateVideo


class SocialSearchProvider(Protocol):
    """Boundary for social video search providers."""

    async def search(self, query: str, limit: int = 10) -> list[CandidateVideo]: ...


class MockSearchProvider:
    """Offline demo provider used for local development and tests."""

    def __init__(self) -> None:
        self.results = [
            CandidateVideo(
                platform="instagram",
                url="https://instagram.com/reel/creamy-chicken-1",
                caption="High protein creamy chicken pasta in 25 minutes",
                creator="@fitbites",
                duration_seconds=1500,
                views=120_000,
                likes=9_000,
            ),
            CandidateVideo(
                platform="tiktok",
                url="https://www.tiktok.com/@quickchef/video/100",
                caption="Viral chocolate cake recipe",
                creator="@quickchef",
                duration_seconds=1800,
                views=8_000_000,
                likes=900_000,
            ),
            CandidateVideo(
                platform="instagram",
                url="https://instagram.com/reel/veggie-pasta",
                caption="Creamy vegetarian spinach pasta",
                creator="@greenplate",
                duration_seconds=1200,
                views=400_000,
                likes=30_000,
            ),
            CandidateVideo(
                platform="tiktok",
                url="https://tiktok.com/@slowcook/video/200",
                caption="Creamy chicken pasta Sunday dinner",
                creator="@slowcook",
                duration_seconds=5400,
                views=250_000,
                likes=18_000,
            ),
            CandidateVideo(
                platform="instagram",
                url="https://instagram.com/reel/low-cal-chicken",
                caption="Low calorie lemon chicken with vegetables",
                creator="@lightplate",
                duration_seconds=1500,
                views=90_000,
                likes=7_000,
            ),
            CandidateVideo(
                platform="tiktok",
                url="https://tiktok.com/@protein/video/300",
                caption="30 minute high protein chicken pasta meal prep",
                creator="@proteinchef",
                duration_seconds=1680,
                views=80_000,
                likes=6_000,
            ),
        ]

    async def search(self, query: str, limit: int = 10) -> list[CandidateVideo]:
        terms = set(query.lower().split())
        ranked = sorted(
            self.results,
            key=lambda item: len(terms & set((item.caption or "").lower().split())),
            reverse=True,
        )
        return [item.model_copy(deep=True) for item in ranked[:limit]]


class SerperSearchProvider:
    """Find indexed Instagram Reels with the Serper search tool."""

    def __init__(self, search_tool: Any | None = None) -> None:
        self._search_tool = search_tool or web_search

    async def search(self, query: str, limit: int = 10) -> list[CandidateVideo]:
        serper_query = query.strip()
        if "site:instagram.com" not in serper_query.lower():
            serper_query = f"site:instagram.com/reel {serper_query}"
        response = await self._search_tool.ainvoke(
            {"query": serper_query, "limit": limit}
        )
        return _candidates_from_serper_response(response, limit)

    async def search_many(
        self,
        queries: list[str],
        limit: int = 10,
    ) -> list[CandidateVideo]:
        batches = await asyncio.gather(
            *(self.search(query, limit=limit) for query in queries)
        )
        candidates: list[CandidateVideo] = []
        seen: set[str] = set()
        for batch in batches:
            for candidate in batch:
                if candidate.url in seen:
                    continue
                seen.add(candidate.url)
                candidates.append(candidate)
                if len(candidates) >= limit:
                    return candidates
        return candidates


def _candidates_from_serper_response(
    response: dict[str, Any],
    limit: int,
) -> list[CandidateVideo]:
    candidates: list[CandidateVideo] = []
    seen: set[str] = set()

    for group_name in ("organic", "videos"):
        results = response.get(group_name, [])
        if not isinstance(results, list):
            continue
        for result in results:
            if not isinstance(result, dict):
                continue
            url = result.get("link")
            if not isinstance(url, str) or url in seen:
                continue
            platform = _social_video_platform(url)
            if platform is None:
                continue
            seen.add(url)
            candidates.append(
                CandidateVideo(
                    platform=platform,
                    url=url,
                    caption=result.get("title") or result.get("snippet"),
                    creator=result.get("channel") or result.get("source"),
                )
            )
            if len(candidates) >= limit:
                return candidates
    return candidates


def _social_video_platform(url: str) -> str | None:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    path = parts.path.lower()
    if (host == "instagram.com" or host.endswith(".instagram.com")) and (
        "/reel/" in path or "/reels/" in path
    ):
        return "instagram"
    return None
