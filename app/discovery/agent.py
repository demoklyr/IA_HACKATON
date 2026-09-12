from dataclasses import dataclass

from .intent_agent import IntentParser, default_intent_parser
from .models import DiscoveryRun
from .social_search import SocialSearchProvider
from .tools import DiscoveryTools


@dataclass
class AgentRuntime:
    intent_parser: str
    search_provider: str


class RecipeDiscoveryAgent:
    def __init__(self, tools: DiscoveryTools) -> None:
        self.tools = tools

    @property
    def runtime(self) -> AgentRuntime:
        return AgentRuntime(
            intent_parser=type(self.tools.intent_parser).__name__,
            search_provider=type(self.tools.search_provider).__name__,
        )

    async def run(self, user_query: str, limit: int = 3) -> DiscoveryRun:
        if not user_query.strip():
            raise ValueError("user_query must not be empty")

        intent = await self.tools.parse_intent(user_query)
        queries = self.tools.plan_queries(user_query, intent)
        candidates = await self.tools.search_videos(queries, limit=10)
        raw_candidates = self.tools.deduplicate(candidates)
        results = self.tools.rank(raw_candidates, user_query, intent)[:max(limit, 0)]
        return DiscoveryRun(
            intent=intent,
            queries=queries,
            raw_candidates=raw_candidates,
            results=results,
        )


def create_discovery_agent(
    intent_parser: IntentParser | None = None,
    search_provider: SocialSearchProvider | None = None,
) -> RecipeDiscoveryAgent:
    from .service import default_search_provider

    tools = DiscoveryTools(
        intent_parser=intent_parser or default_intent_parser(),
        search_provider=search_provider or default_search_provider(),
    )
    return RecipeDiscoveryAgent(tools)
