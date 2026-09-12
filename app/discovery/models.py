from typing import Any, Literal

from pydantic import BaseModel


class CandidateVideo(BaseModel):
    platform: Literal["instagram", "tiktok", "web"]
    url: str
    caption: str | None = None
    creator: str | None = None
    duration_seconds: int | None = None
    views: int | None = None
    likes: int | None = None
    score: float = 0.0
    score_explanation: str | None = None


class DiscoveryRun(BaseModel):
    queries: list[str]
    raw_candidates: list[CandidateVideo]
    results: list[CandidateVideo]
    recipe: dict[str, Any] | None = None
    assistant_message: str = ""
