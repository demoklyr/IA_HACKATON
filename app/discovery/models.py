from typing import Literal

from pydantic import BaseModel, Field


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


class SearchIntent(BaseModel):
    cuisine: str | None = None
    max_time_minutes: int | None = None
    high_protein: bool = False
    low_calorie: bool = False
    vegetarian: bool = False
    excluded_ingredients: list[str] = Field(default_factory=list)
    preferred_ingredients: list[str] = Field(default_factory=list)
    difficulty: str | None = None
    free_form_constraints: list[str] = Field(default_factory=list)
    raw_query: str = ""
