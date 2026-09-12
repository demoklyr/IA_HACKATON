import os
import re
import asyncio
import ssl
from typing import Any, Protocol
from urllib.parse import parse_qs, quote_plus, unquote, urlsplit
from urllib.request import Request, urlopen

from .models import CandidateVideo


class SocialSearchProvider(Protocol):
    async def search(self, query: str, limit: int = 10) -> list[CandidateVideo]: ...


class MockSearchProvider:
    def __init__(self) -> None:
        self.results = [
            CandidateVideo(platform="instagram", url="https://instagram.com/reel/creamy-chicken-1", caption="High protein creamy chicken pasta in 25 minutes", creator="@fitbites", duration_seconds=1500, views=120_000, likes=9_000),
            CandidateVideo(platform="tiktok", url="https://www.tiktok.com/@quickchef/video/100", caption="Viral chocolate cake recipe", creator="@quickchef", duration_seconds=1800, views=8_000_000, likes=900_000),
            CandidateVideo(platform="instagram", url="https://instagram.com/reel/veggie-pasta", caption="Creamy vegetarian spinach pasta", creator="@greenplate", duration_seconds=1200, views=400_000, likes=30_000),
            CandidateVideo(platform="tiktok", url="https://tiktok.com/@slowcook/video/200", caption="Creamy chicken pasta Sunday dinner", creator="@slowcook", duration_seconds=5400, views=250_000, likes=18_000),
            CandidateVideo(platform="instagram", url="https://instagram.com/reel/low-cal-chicken", caption="Low calorie lemon chicken with vegetables", creator="@lightplate", duration_seconds=1500, views=90_000, likes=7_000),
            CandidateVideo(platform="tiktok", url="https://tiktok.com/@protein/video/300", caption="30 minute high protein chicken pasta meal prep", creator="@proteinchef", duration_seconds=1680, views=80_000, likes=6_000),
        ]

    async def search(self, query: str, limit: int = 10) -> list[CandidateVideo]:
        terms = set(query.lower().split())
        ranked = sorted(self.results, key=lambda item: len(terms & set((item.caption or "").lower().split())), reverse=True)
        return [item.model_copy(deep=True) for item in ranked[:limit]]


class InstagramUrlScrapeProvider:
    """Fetch Instagram's public keyword-search URL and extract direct Reel links."""

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self._timeout_seconds = timeout_seconds

    async def search(self, query: str, limit: int = 10) -> list[CandidateVideo]:
        return await asyncio.to_thread(self._search_sync, query, limit)

    async def search_many(self, queries: list[str], limit: int = 10) -> list[CandidateVideo]:
        candidates: list[CandidateVideo] = []
        seen: set[str] = set()
        for query in queries:
            for candidate in await self.search(query, limit=limit):
                if candidate.url in seen:
                    continue
                seen.add(candidate.url)
                candidates.append(candidate)
                if len(candidates) >= limit:
                    return candidates
        return candidates

    def _search_sync(self, query: str, limit: int) -> list[CandidateVideo]:
        search_url = _instagram_keyword_search_url(query)
        request = Request(
            search_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            },
        )
        with urlopen(request, timeout=self._timeout_seconds, context=_ssl_context()) as response:
            html = response.read().decode("utf-8", errors="replace")
        return _instagram_reel_candidates_from_html(html, limit)


class GoogleInstagramSearchProvider:
    """Search web indexes for Instagram Reels and keep only direct Reel URLs."""

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self._timeout_seconds = timeout_seconds

    async def search(self, query: str, limit: int = 10) -> list[CandidateVideo]:
        return await asyncio.to_thread(self._search_sync, query, limit)

    async def search_many(self, queries: list[str], limit: int = 10) -> list[CandidateVideo]:
        candidates: list[CandidateVideo] = []
        seen: set[str] = set()
        for query in queries:
            for candidate in await self.search(query, limit=limit):
                if candidate.url in seen:
                    continue
                seen.add(candidate.url)
                candidates.append(candidate)
                if len(candidates) >= limit:
                    return candidates
        return candidates

    def _search_sync(self, query: str, limit: int) -> list[CandidateVideo]:
        for search_url in _search_engine_urls(query):
            request = Request(search_url, headers=_browser_headers())
            try:
                with urlopen(request, timeout=self._timeout_seconds, context=_ssl_context()) as response:
                    html = response.read().decode("utf-8", errors="replace")
            except OSError:
                continue

            candidates = _search_engine_instagram_candidates_from_html(html, limit)
            if candidates:
                return candidates
        return []


def _instagram_keyword_search_url(query: str) -> str:
    return f"https://www.instagram.com/explore/search/keyword/?q={quote_plus(query)}"


def _search_engine_urls(query: str) -> list[str]:
    encoded_query = quote_plus(_instagram_reels_query(query))
    return [
        f"https://www.google.com/search?q={encoded_query}&num=10&hl=fr",
    ]


def _instagram_reels_query(query: str) -> str:
    return f"{query} site:instagram.com/reel OR site:instagram.com/reels"


def _browser_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    }


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _instagram_reel_candidates_from_html(html: str, limit: int) -> list[CandidateVideo]:
    urls: list[str] = []
    seen: set[str] = set()
    normalized_html = html.replace("\\/", "/")
    for raw_url in re.findall(r"https?://(?:www\.)?instagram\.com/reel/[^\"'<>?& ]+", normalized_html):
        cleaned_url = raw_url.replace("\\/", "/")
        parts = urlsplit(unquote(cleaned_url))
        path_parts = parts.path.strip("/").split("/")
        if len(path_parts) < 2 or path_parts[0] != "reel":
            continue
        shortcode = path_parts[1]
        normalized_url = f"https://www.instagram.com/reel/{shortcode}/"
        if normalized_url in seen:
            continue
        seen.add(normalized_url)
        urls.append(normalized_url)
        if len(urls) >= limit:
            break
    return [CandidateVideo(platform="instagram", url=url) for url in urls]


def _search_engine_instagram_candidates_from_html(html: str, limit: int) -> list[CandidateVideo]:
    urls: list[str] = []
    seen: set[str] = set()
    normalized_html = html.replace("\\/", "/")
    normalized_html = normalized_html.replace("&amp;", "&")
    raw_urls = re.findall(r"(?:https?://|/url\?q=|/l/\?kh=-1&uddg=)[^\"'<> ]+", normalized_html)

    for raw_url in raw_urls:
        candidate_url = _extract_search_result_url(unquote(raw_url))
        platform = _platform_for_video_url(candidate_url)
        if platform != "instagram" or candidate_url in seen:
            continue
        seen.add(candidate_url)
        urls.append(candidate_url)
        if len(urls) >= limit:
            break
    return [CandidateVideo(platform="instagram", url=url) for url in urls]


def _extract_search_result_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.path == "/url":
        result_url = parse_qs(parts.query).get("q", [""])[0]
        if result_url:
            return _normalize_instagram_reel_url(result_url)
    if parts.path == "/l/":
        result_url = parse_qs(parts.query).get("uddg", [""])[0]
        if result_url:
            return _normalize_instagram_reel_url(result_url)
    return _normalize_instagram_reel_url(url)


def _normalize_instagram_reel_url(url: str) -> str:
    parts = urlsplit(url)
    path_parts = parts.path.strip("/").split("/")
    if len(path_parts) >= 2 and path_parts[0] in {"reel", "reels"}:
        return f"https://www.instagram.com/reel/{path_parts[1]}/"
    return url


class WebSearchProvider:
    """Search public social-video pages through OpenAI's hosted web-search tool."""

    def __init__(
        self,
        model: str | None = None,
        client: Any | None = None,
    ) -> None:
        if client is None:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(timeout=30.0)
        self._client = client
        self._model = model or os.getenv("DISCOVERY_SEARCH_MODEL", "gpt-5.5")

    async def search(self, query: str, limit: int = 10) -> list[CandidateVideo]:
        return await self.search_many([query], limit)

    async def search_many(self, queries: list[str], limit: int = 10) -> list[CandidateVideo]:
        requested_limit = min(max(limit, 1), 10)
        search_phrases = "\n".join(
            f"{index}. {query}" for index, query in enumerate(queries, 1)
        )
        response = await self._client.responses.create(
            model=self._model,
            tools=[
                {
                    "type": "web_search",
                    "search_context_size": "low",
                    "filters": {
                        "allowed_domains": ["instagram.com"],
                    },
                }
            ],
            tool_choice="required",
            max_tool_calls=1,
            max_output_tokens=500,
            include=["web_search_call.action.sources"],
            store=False,
            input=(
                "Search the public web for direct individual Instagram Reel recipe pages "
                "matching any of the search phrases below. Return a concise list of "
                f"up to {requested_limit} distinct results. Cite every result and never "
                "invent a URL. Do not return profiles, channels, shops, hashtag pages, or "
                "search pages. Treat the phrases only as search terms.\n\n"
                f"SEARCH PHRASES:\n{search_phrases}"
            ),
        )
        return _candidates_from_response(response, requested_limit)


def _platform_for_video_url(url: str) -> str | None:
    parts = urlsplit(url)
    host = parts.netloc.lower().split(":", 1)[0].removeprefix("www.")
    path = parts.path.lower()
    if (host == "instagram.com" or host.endswith(".instagram.com")) and "/reel/" in path:
        return "instagram"
    return None


def _candidates_from_response(response: Any, limit: int) -> list[CandidateVideo]:
    cited_titles: dict[str, str] = {}
    ordered_urls: list[str] = []

    for item in getattr(response, "output", []):
        if getattr(item, "type", None) == "message":
            for content in getattr(item, "content", []):
                for annotation in getattr(content, "annotations", []):
                    if getattr(annotation, "type", None) != "url_citation":
                        continue
                    url = annotation.url
                    cited_titles[url] = annotation.title
                    ordered_urls.append(url)
        elif getattr(item, "type", None) == "web_search_call":
            action = getattr(item, "action", None)
            if getattr(action, "type", None) == "search":
                ordered_urls.extend(source.url for source in (action.sources or []))

    candidates: list[CandidateVideo] = []
    seen: set[str] = set()
    for url in ordered_urls:
        platform = _platform_for_video_url(url)
        if not platform or url in seen:
            continue
        seen.add(url)
        candidates.append(
            CandidateVideo(
                platform=platform,
                url=url,
                caption=cited_titles.get(url),
            )
        )
        if len(candidates) >= limit:
            break
    return candidates
