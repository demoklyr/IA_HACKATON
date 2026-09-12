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
    constraints: list[str] = []
    if intent.cuisine:
        constraints.append(intent.cuisine)
    if intent.high_protein:
        constraints.append("high protein")
    if intent.low_calorie:
        constraints.append("low calorie")
    if intent.vegetarian:
        constraints.append("vegetarian")
    constraints.extend(intent.preferred_ingredients)
    if intent.difficulty:
        constraints.append(intent.difficulty)
    if intent.max_time_minutes:
        constraints.append(f"under {intent.max_time_minutes} minutes")
    constraints.extend(f"without {ingredient}" for ingredient in intent.excluded_ingredients)

    raw_query = user_query.strip()
    structured_query = " ".join(constraints) or raw_query
    queries = [
        f"{raw_query} Instagram Reel recette",
        f"{structured_query} recipe video",
        f"{structured_query} easy recipe Instagram Reel",
    ]
    return list(dict.fromkeys(queries))[:5]
