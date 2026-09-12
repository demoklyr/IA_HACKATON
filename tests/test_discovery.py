import pytest

from app.discovery.query_planner import generate_queries, parse_intent
from app.discovery.ranker import deduplicate_candidates, normalize_url, rank_candidates
from app.discovery.service import find_recipe_videos
from app.discovery.models import CandidateVideo


def test_query_generation():
    intent = parse_intent("high-protein creamy chicken pasta under 30 minutes")
    queries = generate_queries(intent.raw_query, intent)
    assert 3 <= len(queries) <= 5
    assert any("protein" in query for query in queries)
    assert intent.max_time_minutes == 30


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
    results = await find_recipe_videos("high-protein creamy chicken pasta under 30 minutes")
    assert len(results) == 3
    assert results[0].platform in {"instagram", "tiktok"}
    assert results[0].score_explanation
