import asyncio
import os

from dotenv import load_dotenv

from .intent_agent import IntentParser, default_intent_parser
from .models import CandidateVideo, DiscoveryRun
from .query_planner import generate_queries
from .ranker import deduplicate_candidates, rank_candidates
from .social_search import GoogleInstagramSearchProvider, InstagramUrlScrapeProvider, MockSearchProvider, SocialSearchProvider, WebSearchProvider


def default_search_provider() -> SocialSearchProvider:
    load_dotenv()
    configured = os.getenv("DISCOVERY_SEARCH_PROVIDER")
    provider_name = configured.lower() if configured else ("web" if os.getenv("OPENAI_API_KEY") else "mock")
    if provider_name == "mock":
        return MockSearchProvider()
    if provider_name == "instagram":
        return InstagramUrlScrapeProvider()
    if provider_name == "google":
        return GoogleInstagramSearchProvider()
    if provider_name == "web":
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required when DISCOVERY_SEARCH_PROVIDER=web")
        return WebSearchProvider()
    raise ValueError("DISCOVERY_SEARCH_PROVIDER must be 'web', 'google', 'instagram', or 'mock'")


async def run_discovery(
    user_query: str,
    limit: int = 3,
    provider: SocialSearchProvider | None = None,
    intent_parser: IntentParser | None = None,
) -> DiscoveryRun:
    if not user_query.strip():
        raise ValueError("user_query must not be empty")
    intent = await (intent_parser or default_intent_parser()).parse(user_query)
    queries = generate_queries(user_query, intent)
    provider = provider or default_search_provider()
    search_many = getattr(provider, "search_many", None)
    if callable(search_many):
        candidates = await search_many(queries, limit=10)
    else:
        batches = await asyncio.gather(*(provider.search(query, limit=10) for query in queries))
        candidates = [candidate for batch in batches for candidate in batch]
    raw_candidates = deduplicate_candidates(candidates)
    results = rank_candidates(raw_candidates, user_query, intent)[:max(limit, 0)]
    return DiscoveryRun(intent=intent, queries=queries, raw_candidates=raw_candidates, results=results)


async def find_recipe_videos(user_query: str, limit: int = 3) -> list[CandidateVideo]:
    return (await run_discovery(user_query, limit)).results
