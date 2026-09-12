# Discovery module specification

This repository's first feature is limited to `app/discovery`. It accepts a natural-language cooking request and returns ranked social recipe-video URLs. It must not download videos, extract recipes, or implement cooking assistance.

## Contract

```python
async def find_recipe_videos(user_query: str, limit: int = 3) -> list[CandidateVideo]
```

`CandidateVideo` is the boundary object consumed later by `recipe_downloader`. Providers are replaceable and search concurrently; the first implementation uses deterministic mock data and a web-search stub. URLs are deduplicated by normalized URL and ranked with transparent, text-based heuristics.

## Acceptance criteria

- Python 3.11+ and Pydantic models.
- LangChain is allowed only for intent understanding and structured output. Do not add LangGraph yet.
- The intent agent reads an editable Markdown skill and has a deterministic fallback when no API key is configured.
- Query generation produces 3–5 deterministic variants from the parsed intent.
- Search providers do not scrape Instagram or TikTok directly.
- The CLI prints intent, generated queries, raw candidates, and top results.
- Tests cover query generation, URL deduplication, ranking, and end-to-end mocked discovery.
