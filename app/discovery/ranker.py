import re

from .models import CandidateVideo


def rank_candidates(candidates: list[CandidateVideo], user_query: str) -> list[CandidateVideo]:
    requested = set(re.findall(r"[a-z0-9]+", user_query.lower()))
    for candidate in candidates:
        caption_words = set(re.findall(r"[a-z0-9]+", (candidate.caption or "").lower()))
        overlap = len(requested & caption_words) / max(len(requested), 1)
        score = overlap * 70
        reasons = [f"text overlap {overlap:.0%}"]
        popularity = min(((candidate.views or 0) / 1_000_000) * 5 + ((candidate.likes or 0) / 100_000) * 5, 10)
        score += popularity
        if popularity:
            reasons.append("some popularity bonus")
        candidate.score = round(score, 2)
        candidate.score_explanation = "; ".join(reasons)
    return sorted(candidates, key=lambda item: item.score, reverse=True)
