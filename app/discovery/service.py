import asyncio

from .models import CandidateVideo
from .query_planner import generate_queries, parse_intent
from .ranker import normalize_url, rank_candidates
from .social_search import MockSearchProvider, SocialSearchProvider


async def find_recipe_videos(user_query: str, limit: int = 3, provider: SocialSearchProvider | None = None) -> list[CandidateVideo]:
    if not user_query.strip():
        raise ValueError("user_query must not be empty")
    if limit < 1:
        return []
    intent = parse_intent(user_query)
    queries = generate_queries(user_query, intent)
    provider = provider or MockSearchProvider()
    batches = await asyncio.gather(*(provider.search(query, limit=10) for query in queries))
    unique: dict[str, CandidateVideo] = {}
    for batch in batches:
        for candidate in batch:
            unique.setdefault(normalize_url(candidate.url), candidate)
    return rank_candidates(list(unique.values()), user_query, intent)[:limit]
