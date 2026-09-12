import os

from dotenv import load_dotenv

from .agent import create_discovery_agent
from .intent_agent import IntentParser, default_intent_parser
from .models import CandidateVideo, DiscoveryRun
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
    agent = create_discovery_agent(
        intent_parser=intent_parser or default_intent_parser(),
        search_provider=provider or default_search_provider(),
    )
    return await agent.run(user_query, limit)


async def find_recipe_videos(user_query: str, limit: int = 3) -> list[CandidateVideo]:
    return (await run_discovery(user_query, limit)).results
