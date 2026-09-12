import argparse
import asyncio

from .query_planner import generate_queries, parse_intent
from .service import find_recipe_videos


async def run(user_query: str, limit: int = 3) -> None:
    intent = parse_intent(user_query)
    print("USER REQUEST\n" + user_query)
    print("\nPARSED INTENT\n" + intent.model_dump_json(indent=2))
    print("\nGENERATED QUERIES")
    for index, query in enumerate(generate_queries(user_query, intent), 1):
        print(f"{index}. {query}")
    results = await find_recipe_videos(user_query, limit)
    print("\nTOP RESULTS")
    for index, video in enumerate(results, 1):
        print(f"{index}. score={video.score}\n   platform={video.platform}\n   caption={video.caption}\n   url={video.url}\n   reason={video.score_explanation}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discover recipe videos")
    parser.add_argument("user_query")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    asyncio.run(run(args.user_query, args.limit))
