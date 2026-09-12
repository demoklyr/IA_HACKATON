import asyncio

from .intent_agent import IntentParser, default_intent_parser
from .models import CandidateVideo, DiscoveryRun
from .query_planner import generate_queries
from .ranker import deduplicate_candidates, rank_candidates
from .social_search import MockSearchProvider, SocialSearchProvider


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
    provider = provider or MockSearchProvider()
    batches = await asyncio.gather(*(provider.search(query, limit=10) for query in queries))
    raw_candidates = deduplicate_candidates([candidate for batch in batches for candidate in batch])
    results = rank_candidates(raw_candidates, user_query, intent)[:max(limit, 0)]
    return DiscoveryRun(intent=intent, queries=queries, raw_candidates=raw_candidates, results=results)


async def find_recipe_videos(user_query: str, limit: int = 3) -> list[CandidateVideo]:
    return (await run_discovery(user_query, limit)).results
