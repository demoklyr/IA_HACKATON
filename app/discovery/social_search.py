from typing import Protocol

from .models import CandidateVideo


class SocialSearchProvider(Protocol):
    """Boundary for social video search providers."""

    async def search(self, query: str, limit: int = 10) -> list[CandidateVideo]: ...


class MockSearchProvider:
    """Offline demo provider used for local development and tests."""

    def __init__(self) -> None:
        self.results = [
            CandidateVideo(
                platform="instagram",
                url="https://instagram.com/reel/creamy-chicken-1",
                caption="High protein creamy chicken pasta in 25 minutes",
                creator="@fitbites",
                duration_seconds=1500,
                views=120_000,
                likes=9_000,
            ),
            CandidateVideo(
                platform="tiktok",
                url="https://www.tiktok.com/@quickchef/video/100",
                caption="Viral chocolate cake recipe",
                creator="@quickchef",
                duration_seconds=1800,
                views=8_000_000,
                likes=900_000,
            ),
            CandidateVideo(
                platform="instagram",
                url="https://instagram.com/reel/veggie-pasta",
                caption="Creamy vegetarian spinach pasta",
                creator="@greenplate",
                duration_seconds=1200,
                views=400_000,
                likes=30_000,
            ),
            CandidateVideo(
                platform="tiktok",
                url="https://tiktok.com/@slowcook/video/200",
                caption="Creamy chicken pasta Sunday dinner",
                creator="@slowcook",
                duration_seconds=5400,
                views=250_000,
                likes=18_000,
            ),
            CandidateVideo(
                platform="instagram",
                url="https://instagram.com/reel/low-cal-chicken",
                caption="Low calorie lemon chicken with vegetables",
                creator="@lightplate",
                duration_seconds=1500,
                views=90_000,
                likes=7_000,
            ),
            CandidateVideo(
                platform="tiktok",
                url="https://tiktok.com/@protein/video/300",
                caption="30 minute high protein chicken pasta meal prep",
                creator="@proteinchef",
                duration_seconds=1680,
                views=80_000,
                likes=6_000,
            ),
        ]

    async def search(self, query: str, limit: int = 10) -> list[CandidateVideo]:
        terms = set(query.lower().split())
        ranked = sorted(
            self.results,
            key=lambda item: len(terms & set((item.caption or "").lower().split())),
            reverse=True,
        )
        return [item.model_copy(deep=True) for item in ranked[:limit]]
