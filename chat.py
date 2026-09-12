import asyncio
import json

from app.discovery.agent import ConversationMemory, create_langchain_react_agent


def _print_discovery(discovery) -> None:
    if discovery.instagram_post is not None:
        print("\nINSTAGRAM POST")
        print(json.dumps(discovery.instagram_post, indent=2, ensure_ascii=False))
        return

    if discovery.recipe is not None:
        print("\nRECIPE")
        print(json.dumps(discovery.recipe, indent=2, ensure_ascii=False))
        return

    print("\nSEARCH QUERIES")
    for index, query in enumerate(discovery.queries, 1):
        print(f"{index}. {query}")

    print("\nRAW CANDIDATES")
    for video in discovery.raw_candidates:
        print(f"- [{video.platform}] {video.caption} -- {video.url}")

    print("\nTOP RESULTS")
    for index, video in enumerate(discovery.results, 1):
        print(f"{index}. {video.caption}")
        print(f"   url={video.url}")
        print(f"   score={video.score}")
        print(f"   reason={video.score_explanation}")


async def main() -> None:
    agent = create_langchain_react_agent(
        memory=ConversationMemory(max_turns=6),
    )
    conversation_id = "terminal-chat"

    print("Agent: Quelle recette cherches-tu sur Instagram ?")
    print("Type 'clear' to forget the conversation or 'quit' to exit.")

    while True:
        try:
            user_query = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_query:
            continue
        if user_query.lower() in {"quit", "exit"}:
            print("Goodbye!")
            break
        if user_query.lower() == "clear":
            agent.clear_memory(conversation_id)
            print("Conversation cleared.")
            continue

        try:
            discovery = await agent.run(
                user_query,
                limit=3,
                conversation_id=conversation_id,
            )
        except Exception as exc:
            print(f"Error: {exc}")
            continue

        _print_discovery(discovery)


if __name__ == "__main__":
    asyncio.run(main())
