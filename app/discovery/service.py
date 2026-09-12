import os

from dotenv import load_dotenv

from .agent import create_discovery_agent
from .intent_agent import IntentParser, default_intent_parser
from .models import CandidateVideo, DiscoveryRun
from .social_search import MockSearchProvider, SerperSearchProvider, SocialSearchProvider


def default_search_provider() -> SocialSearchProvider:
    load_dotenv()
    provider_name = os.getenv("DISCOVERY_SEARCH_PROVIDER", "auto").strip().lower()
    if provider_name == "auto":
        provider_name = "serper" if os.getenv("SERPER_API_KEY") else "mock"
    if provider_name == "mock":
        return MockSearchProvider()
    if provider_name == "serper":
        return SerperSearchProvider()
    raise ValueError("DISCOVERY_SEARCH_PROVIDER must be 'auto', 'mock', or 'serper'")


async def run_discovery(
    user_query: str,
    limit: int = 3,
    provider: SocialSearchProvider | None = None,
    intent_parser: IntentParser | None = None,
) -> DiscoveryRun:
    agent = create_discovery_agent(
        intent_parser=intent_parser or default_intent_parser(),
        search_provider=provider or default_search_provider(),
    )
    return await agent.run(user_query, limit)


async def find_recipe_videos(user_query: str, limit: int = 3) -> list[CandidateVideo]:
    return (await run_discovery(user_query, limit)).results
