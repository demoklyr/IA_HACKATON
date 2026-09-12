import re
from urllib.parse import urlsplit, urlunsplit

from .models import CandidateVideo, SearchIntent


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower().removeprefix("www."), parts.path.rstrip("/"), "", ""))


def deduplicate_candidates(candidates: list[CandidateVideo]) -> list[CandidateVideo]:
    unique: dict[str, CandidateVideo] = {}
    for candidate in candidates:
        unique.setdefault(normalize_url(candidate.url), candidate)
    return list(unique.values())


def rank_candidates(candidates: list[CandidateVideo], user_query: str, intent: SearchIntent) -> list[CandidateVideo]:
    requested = set(re.findall(r"[a-z0-9]+", user_query.lower()))
    for candidate in candidates:
        caption_words = set(re.findall(r"[a-z0-9]+", (candidate.caption or "").lower()))
        overlap = len(requested & caption_words) / max(len(requested), 1)
        score = overlap * 70
        reasons = [f"text overlap {overlap:.0%}"]
        if intent.max_time_minutes and candidate.duration_seconds is not None:
            if candidate.duration_seconds <= intent.max_time_minutes * 60:
                score += 20
                reasons.append("within time limit")
            else:
                score -= 25
                reasons.append("over time limit")
        popularity = min(((candidate.views or 0) / 1_000_000) * 5 + ((candidate.likes or 0) / 100_000) * 5, 10)
        score += popularity
        if popularity:
            reasons.append("some popularity bonus")
        candidate.score = round(score, 2)
        candidate.score_explanation = "; ".join(reasons)
    return sorted(candidates, key=lambda item: item.score, reverse=True)
