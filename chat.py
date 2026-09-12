import asyncio

from app.discovery.agent import ConversationMemory, create_langchain_react_agent


def _print_discovery(discovery) -> None:
    if discovery.assistant_message:
        print(f"\nAgent: {discovery.assistant_message}")
        return

    if discovery.instagram_post is not None:
        description = discovery.instagram_post.get("description")
        if isinstance(description, str) and description.strip():
            normalized = " ".join(description.split())
            message = normalized[:397] + "..." if len(normalized) > 400 else normalized
        else:
            message = "Je n'ai pas trouvé de description pour cette publication."
        print(f"\nAgent: {message}")
        return

    if discovery.recipe is not None:
        name = discovery.recipe.get("name") or "Cette recette"
        ingredients = discovery.recipe.get("ingredients", [])
        ingredient_names = [
            ingredient.get("name", "")
            for ingredient in ingredients
            if isinstance(ingredient, dict) and ingredient.get("name")
        ]
        details = ", ".join(ingredient_names[:5])
        message = f"{name} utilise principalement {details}." if details else str(name)
        print(f"\nAgent: {message}")
        return

    if not discovery.results:
        print("\nAgent: Je n'ai pas trouvé de vidéo pertinente pour cette recherche.")
        return

    print("\nAgent: Voici mes suggestions :")
    for index, video in enumerate(discovery.results, 1):
        print(f"{index}. {video.caption or 'Une recette à découvrir'}")


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
