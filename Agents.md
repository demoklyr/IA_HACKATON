# Discovery module specification

This repository's first feature is limited to `app/discovery`. It accepts a natural-language cooking request and returns ranked social recipe-video URLs. It must not download videos, extract recipes, or implement cooking assistance.

## Contract

```python
async def find_recipe_videos(user_query: str, limit: int = 3) -> list[CandidateVideo]
```

`CandidateVideo` is the boundary object consumed later by `recipe_downloader`. Providers are replaceable and search concurrently; the first implementation uses deterministic mock data and a web-search stub. URLs are deduplicated by normalized URL and ranked with transparent, text-based heuristics.

## Acceptance criteria

- Python 3.11+, Pydantic models, no LangChain/LangGraph.
- Query parsing and 3–5 query variants are deterministic.
- Search providers do not scrape Instagram or TikTok directly.
- The CLI prints intent, generated queries, raw candidates, and top results.
- Tests cover query generation, URL deduplication, ranking, and end-to-end mocked discovery.
