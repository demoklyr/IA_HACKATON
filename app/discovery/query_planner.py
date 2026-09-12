import re

from .models import SearchIntent


def parse_intent(user_query: str) -> SearchIntent:
    text = user_query.lower().replace("-", " ")
    minutes = None
    match = re.search(r"(?:under|less than|moins de|en moins de)\s*(\d+)\s*(?:minutes?|min)?", text)
    if match:
        minutes = int(match.group(1))
    preferred = [word for word in ("chicken", "pasta", "salmon", "rice", "beef", "tofu") if word in text]
    excluded = re.findall(r"(?:sans|without|no)\s+([a-zA-ZÀ-ÿ-]+)", text)
    difficulty = "easy" if any(word in text for word in ("easy", "quick", "simple", "facile")) else None
    return SearchIntent(
        max_time_minutes=minutes,
        high_protein=any(word in text for word in ("high protein", "protein-rich", "riche en protéines")),
        low_calorie=any(word in text for word in ("low calorie", "light", "healthy", "peu calorique")),
        vegetarian=any(word in text for word in ("vegetarian", "veggie", "végétarien")),
        excluded_ingredients=excluded,
        preferred_ingredients=preferred,
        difficulty=difficulty,
        free_form_constraints=[user_query.strip()],
        raw_query=user_query,
    )


def generate_queries(user_query: str, intent: SearchIntent | None = None) -> list[str]:
    intent = intent or parse_intent(user_query)
    base = " ".join(intent.preferred_ingredients) or user_query.strip()
    qualifiers = []
    if intent.high_protein:
        qualifiers.append("high protein")
    if intent.low_calorie:
        qualifiers.append("healthy")
    if intent.vegetarian:
        qualifiers.append("vegetarian")
    suffix = " ".join(qualifiers)
    queries = [f"{suffix} {base} recipe".strip(), f"healthy {base} recipe".strip(), f"easy {suffix} {base}".strip()]
    if intent.max_time_minutes:
        queries.append(f"{intent.max_time_minutes} minute {base} recipe")
    queries.append(f"creamy {base} recipe".strip())
    return list(dict.fromkeys(queries))[:5]
