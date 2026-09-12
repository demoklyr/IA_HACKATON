import pytest
from types import SimpleNamespace

from app.discovery.query_planner import generate_queries, parse_intent
from app.discovery.ranker import deduplicate_candidates, normalize_url, rank_candidates

from app.discovery.intent_agent import RuleBasedIntentParser
from app.discovery.agent import LangChainReActDiscoveryAgent, _coerce_queries, create_discovery_agent
from app.discovery.service import default_search_provider, run_discovery
from app.discovery.models import CandidateVideo
from app.discovery.social_search import MockSearchProvider, SerperSearchProvider
from app.discovery.tools import DiscoveryTools


def test_query_generation():
    intent = parse_intent("high-protein creamy chicken pasta under 30 minutes")
    queries = generate_queries(intent.raw_query, intent)
    assert 3 <= len(queries) <= 5
    assert any("protein" in query for query in queries)
    assert intent.max_time_minutes == 30


def test_query_generation_uses_structured_constraints():
    intent = parse_intent("recette végétarienne sans avocat en moins de 20 minutes")
    intent = intent.model_copy(update={"cuisine": "Mexican", "difficulty": "easy"})
    queries = generate_queries(intent.raw_query, intent)
    combined = " ".join(queries).lower()
    assert "mexican" in combined
    assert "without avocat" in combined
    assert "creamy" not in combined


def test_url_normalization():
    assert normalize_url("HTTPS://WWW.Instagram.com/reel/demo/?utm_source=x") == "https://instagram.com/reel/demo"


def test_deduplication_ignores_query_parameters():
    candidates = [
        CandidateVideo(platform="instagram", url="https://instagram.com/reel/demo"),
        CandidateVideo(platform="instagram", url="https://www.instagram.com/reel/demo/?utm_source=x"),
    ]
    assert len(deduplicate_candidates(candidates)) == 1


def test_ranking_prefers_relevant_candidate():
    intent = parse_intent("high protein chicken pasta under 30 minutes")
    candidates = [CandidateVideo(platform="tiktok", url="https://tiktok.com/a", caption="Viral cake", views=9_000_000), CandidateVideo(platform="instagram", url="https://instagram.com/b", caption="30 minute high protein chicken pasta", duration_seconds=1500)]
    assert rank_candidates(candidates, intent.raw_query, intent)[0].url.endswith("/b")


@pytest.mark.asyncio
async def test_end_to_end_mocked_discovery():
    discovery = await run_discovery(
        "high-protein creamy chicken pasta under 30 minutes",
        provider=MockSearchProvider(),
        intent_parser=RuleBasedIntentParser(),
    )
    results = discovery.results
    assert len(results) == 3
    assert results[0].platform in {"instagram", "tiktok"}
    assert results[0].score_explanation


@pytest.mark.asyncio
async def test_agent_runs_with_injected_tools():
    agent = create_discovery_agent(
        intent_parser=RuleBasedIntentParser(),
        search_provider=MockSearchProvider(),
    )

    discovery = await agent.run("easy vegetarian recipe", limit=2)

    assert agent.runtime.intent_parser == "RuleBasedIntentParser"
    assert agent.runtime.search_provider == "MockSearchProvider"
    assert [step.action for step in agent.trace] == [
        "parse_intent",
        "plan_queries",
        "search_videos",
        "deduplicate",
        "rank",
    ]
    assert len(discovery.queries) >= 3
    assert len(discovery.results) == 2


def test_langchain_react_agent_requires_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    tools = DiscoveryTools(
        intent_parser=RuleBasedIntentParser(),
        search_provider=MockSearchProvider(),
    )

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        LangChainReActDiscoveryAgent(tools, model="openai:gpt-4.1-mini")


def test_langchain_react_query_coercion_handles_bad_json():
    assert _coerce_queries('["query one", "query two"]') == ["query one", "query two"]
    assert _coerce_queries('["query one\nquery two"]') == []


@pytest.mark.asyncio
async def test_serper_provider_uses_web_search_tool():
    calls = []

    async def fake_ainvoke(arguments):
        calls.append(arguments)
        return {
            "organic": [
                {
                    "title": "Fast pasta recipe",
                    "link": "https://www.instagram.com/reel/PASTA123/",
                },
                {
                    "title": "Not a video",
                    "link": "https://example.com/pasta",
                },
            ],
            "videos": [
                {
                    "title": "Quick pasta",
                    "link": "https://www.tiktok.com/@chef/video/123456",
                    "channel": "Chef",
                }
            ],
        }

    provider = SerperSearchProvider(search_tool=SimpleNamespace(ainvoke=fake_ainvoke))

    candidates = await provider.search("quick pasta recipe videos", limit=5)

    assert calls == [{"query": "quick pasta recipe videos", "limit": 5}]
    assert [candidate.platform for candidate in candidates] == ["instagram", "tiktok"]
    assert candidates[0].caption == "Fast pasta recipe"
    assert candidates[1].creator == "Chef"


def test_default_provider_uses_serper_when_key_is_configured(monkeypatch):
    monkeypatch.setenv("DISCOVERY_SEARCH_PROVIDER", "auto")
    monkeypatch.setenv("SERPER_API_KEY", "test-key")

    assert isinstance(default_search_provider(), SerperSearchProvider)


def test_default_provider_can_force_mock(monkeypatch):
    monkeypatch.setenv("DISCOVERY_SEARCH_PROVIDER", "mock")
    monkeypatch.setenv("SERPER_API_KEY", "test-key")

    assert isinstance(default_search_provider(), MockSearchProvider)
