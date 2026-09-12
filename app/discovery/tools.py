import asyncio

from .intent_agent import IntentParser
from .models import CandidateVideo, SearchIntent
from .query_planner import generate_queries
from .ranker import deduplicate_candidates, rank_candidates
from .social_search import SocialSearchProvider


class DiscoveryTools:
    def __init__(self, intent_parser: IntentParser, search_provider: SocialSearchProvider) -> None:
        self.intent_parser = intent_parser
        self.search_provider = search_provider

    async def parse_intent(self, user_query: str) -> SearchIntent:
        return await self.intent_parser.parse(user_query)

    def plan_queries(self, user_query: str, intent: SearchIntent) -> list[str]:
        return generate_queries(user_query, intent)

    async def search_videos(self, queries: list[str], limit: int = 10) -> list[CandidateVideo]:
        search_many = getattr(self.search_provider, "search_many", None)
        if callable(search_many):
            return await search_many(queries, limit=limit)

        batches = await asyncio.gather(
            *(self.search_provider.search(query, limit=limit) for query in queries)
        )
        return [candidate for batch in batches for candidate in batch]

    def deduplicate(self, candidates: list[CandidateVideo]) -> list[CandidateVideo]:
        return deduplicate_candidates(candidates)

    def rank(
        self,
        candidates: list[CandidateVideo],
        user_query: str,
        intent: SearchIntent,
    ) -> list[CandidateVideo]:
        return rank_candidates(candidates, user_query, intent)
