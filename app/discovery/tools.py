from .models import CandidateVideo
from .ranker import rank_candidates
from .social_search import SocialSearchProvider


class DiscoveryTools:
    def __init__(self, search_provider: SocialSearchProvider) -> None:
        self.search_provider = search_provider

    async def search_videos(self, query: str, limit: int = 10) -> list[CandidateVideo]:
        return await self.search_provider.search(query, limit=limit)

    def rank(
        self,
        candidates: list[CandidateVideo],
        user_query: str,
    ) -> list[CandidateVideo]:
        return rank_candidates(candidates, user_query)
