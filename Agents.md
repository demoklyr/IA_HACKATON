# Discovery module specification

This repository's first feature is limited to `app/discovery`. It accepts a natural-language cooking request and returns ranked social recipe-video URLs. It must not download videos, extract recipes, or implement cooking assistance.

## Contract

```python
async def find_recipe_videos(user_query: str, limit: int = 3) -> list[CandidateVideo]
```

`CandidateVideo` is the boundary object consumed later by `recipe_downloader`. Providers are replaceable; the first implementation uses deterministic mock data. The minimal agent searches with its query and ranks the returned URLs with transparent, text-based heuristics.

## Acceptance criteria

- Python 3.11+ and Pydantic models.
- The LangChain ReAct agent exposes only search and ranking tools. Do not add LangGraph yet.
- The model sends its query directly to the configured search provider.
- Search providers do not scrape Instagram or TikTok directly.
- The CLI prints search queries, raw candidates, and top results.
