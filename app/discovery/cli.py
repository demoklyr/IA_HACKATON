import argparse
import asyncio

from .service import run_discovery


async def run(user_query: str, limit: int = 3) -> None:
    discovery = await run_discovery(user_query, limit)
    print("USER REQUEST\n" + user_query)
    print("\nSEARCH QUERIES")
    for index, query in enumerate(discovery.queries, 1):
        print(f"{index}. {query}")
    print("\nRAW CANDIDATES")
    for candidate in discovery.raw_candidates:
        print(f"- [{candidate.platform}] {candidate.caption} — {candidate.url}")
    print("\nTOP RESULTS")
    for index, video in enumerate(discovery.results, 1):
        print(f"{index}. score={video.score}\n   platform={video.platform}\n   caption={video.caption}\n   url={video.url}\n   reason={video.score_explanation}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discover recipe videos")
    parser.add_argument("user_query")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    asyncio.run(run(args.user_query, args.limit))
