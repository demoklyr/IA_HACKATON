import argparse
import asyncio
import os

from dotenv import load_dotenv

from app.discovery.agent import create_discovery_agent, create_langchain_react_agent


def _key_state(name: str) -> str:
    return "set" if os.getenv(name) else "missing"


def _print_discovery(user_query: str, discovery) -> None:
    print("USER REQUEST\n" + user_query)

    print("\nSEARCH QUERIES")
    for index, query in enumerate(discovery.queries, 1):
        print(f"{index}. {query}")

    print("\nRAW CANDIDATES")
    for candidate in discovery.raw_candidates:
        print(f"- [{candidate.platform}] {candidate.caption} -- {candidate.url}")

    print("\nTOP RESULTS")
    for index, video in enumerate(discovery.results, 1):
        print(
            f"{index}. score={video.score}\n"
            f"   platform={video.platform}\n"
            f"   caption={video.caption}\n"
            f"   url={video.url}\n"
            f"   reason={video.score_explanation}"
        )


def _print_react_trace(agent) -> None:
    print("REACT TRACE")
    for index, step in enumerate(agent.trace, 1):
        print(f"{index}. Thought: {step.thought}")
        print(f"   Action: {step.action}")
        print(f"   Observation: {step.observation}")


async def run() -> None:
    parser = argparse.ArgumentParser(description="Run the recipe video discovery agent")
    parser.add_argument("user_query", nargs="+", help="Natural-language recipe video request")
    parser.add_argument("--limit", type=int, default=3, help="Number of ranked results to show")
    parser.add_argument(
        "--provider",
        choices=["auto", "mock", "serper"],
        help="Search provider override. Defaults to DISCOVERY_SEARCH_PROVIDER or app defaults.",
    )
    parser.add_argument(
        "--langchain-react",
        action="store_true",
        help="Run the minimal LangChain ReAct agent instead of the deterministic agent.",
    )
    args = parser.parse_args()

    load_dotenv()
    if args.provider:
        os.environ["DISCOVERY_SEARCH_PROVIDER"] = args.provider

    user_query = " ".join(args.user_query).strip()
    agent = create_langchain_react_agent() if args.langchain_react else create_discovery_agent()
    runtime = agent.runtime

    print("RUNTIME")
    print(f"agent={type(agent).__name__}")
    print(f"search_provider={runtime.search_provider}")
    print(f"discovery_search_provider={os.getenv('DISCOVERY_SEARCH_PROVIDER') or 'auto'}")
    print(f"openai_api_key={_key_state('OPENAI_API_KEY')}")
    print(f"serper_api_key={_key_state('SERPER_API_KEY')}")
    print()

    discovery = await agent.run(user_query, limit=args.limit)
    _print_react_trace(agent)
    print()
    _print_discovery(user_query, discovery)


if __name__ == "__main__":
    asyncio.run(run())
