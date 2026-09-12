import pytest

from app.discovery.query_planner import generate_queries, parse_intent
from app.discovery.ranker import deduplicate_candidates, normalize_url, rank_candidates
from types import SimpleNamespace

from app.discovery.intent_agent import RuleBasedIntentParser
from app.discovery.agent import create_discovery_agent
from app.discovery.service import run_discovery
from app.discovery.models import CandidateVideo
from app.discovery.social_search import MockSearchProvider, WebSearchProvider, _instagram_reel_candidates_from_html, _search_engine_instagram_candidates_from_html


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
    assert len(discovery.queries) >= 3
    assert len(discovery.results) == 2


@pytest.mark.asyncio
async def test_web_search_provider_returns_only_instagram_reels():
    instagram_url = "https://www.instagram.com/reel/ABC123/"
    tiktok_url = "https://www.tiktok.com/@chef/video/123456"
    youtube_url = "https://www.youtube.com/watch?v=abcdef"
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="web_search_call",
                action=SimpleNamespace(
                    type="search",
                    sources=[
                        SimpleNamespace(url=instagram_url),
                        SimpleNamespace(url=tiktok_url),
                        SimpleNamespace(url=youtube_url),
                        SimpleNamespace(url="https://www.instagram.com/explore/"),
                    ],
                ),
            ),
            SimpleNamespace(
                type="message",
                content=[
                    SimpleNamespace(
                        annotations=[
                            SimpleNamespace(
                                type="url_citation",
                                url=instagram_url,
                                title="Easy vegetarian tacos",
                            )
                        ]
                    )
                ],
            ),
        ]
    )

    class FakeResponses:
        def __init__(self):
            self.kwargs = None

        async def create(self, **kwargs):
            self.kwargs = kwargs
            return response

    fake_responses = FakeResponses()
    fake_client = SimpleNamespace(responses=fake_responses)
    provider = WebSearchProvider(model="gpt-4.1-mini", client=fake_client)

    candidates = await provider.search_many(
        ["vegetarian tacos", "easy meatless tacos"],
        limit=5,
    )

    assert [candidate.url for candidate in candidates] == [instagram_url]
    assert candidates[0].caption == "Easy vegetarian tacos"
    assert fake_responses.kwargs["tools"][0]["filters"]["allowed_domains"] == ["instagram.com"]
    assert "1. vegetarian tacos" in fake_responses.kwargs["input"]
    assert "2. easy meatless tacos" in fake_responses.kwargs["input"]


def test_instagram_html_extraction_returns_only_reels():
    html = """
    <a href=\"https://www.instagram.com/reel/ABC123/?utm_source=ig_web_copy_link\">Reel</a>
    <a href=\"https://www.instagram.com/p/NOTAREEL/\">Post</a>
    https:\\/\\/www.instagram.com\\/reel\\/DEF456\\/
    """

    candidates = _instagram_reel_candidates_from_html(html, limit=10)

    assert [candidate.url for candidate in candidates] == [
        "https://www.instagram.com/reel/ABC123/",
        "https://www.instagram.com/reel/DEF456/",
    ]


def test_search_engine_html_extraction_returns_only_instagram_reels():
    html = """
    <a href="/url?q=https://www.instagram.com/reels/ABC123/?igsh=demo&sa=U">Reel</a>
    <a href="/l/?kh=-1&uddg=https%3A%2F%2Fwww.instagram.com%2Freel%2FDUCK123%2F">Duck</a>
    <a href="/url?q=https://www.tiktok.com/@chef/video/123&sa=U">TikTok</a>
    <a href="https://www.instagram.com/p/NOTAREEL/">Post</a>
    <a href="https://www.instagram.com/reel/DEF456/">Another Reel</a>
    """

    candidates = _search_engine_instagram_candidates_from_html(html, limit=10)

    assert [candidate.url for candidate in candidates] == [
        "https://www.instagram.com/reel/ABC123/",
        "https://www.instagram.com/reel/DUCK123/",
        "https://www.instagram.com/reel/DEF456/",
    ]
