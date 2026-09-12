from typing import Any

import pytest

from app.discovery.agent import (
    ConversationMemory,
    LangChainReActDiscoveryAgent,
    RecipeDiscoveryAgent,
)
from app.discovery.models import CandidateVideo
from app.discovery.tools import DiscoveryTools


class StubSearchProvider:
    async def search(self, query: str, limit: int = 10) -> list[CandidateVideo]:
        return [
            CandidateVideo(
                platform="web",
                url=f"https://example.com/{len(query)}",
                caption=f"Recipe for {query}",
            )
        ][:limit]


class CapturingModelAgent:
    def __init__(self) -> None:
        self.invocations: list[dict[str, Any]] = []

    async def ainvoke(self, value: dict[str, Any]) -> dict[str, Any]:
        self.invocations.append(value)
        return {"messages": value["messages"]}


def test_memory_is_bounded_isolated_and_clearable() -> None:
    memory = ConversationMemory(max_turns=2)
    memory.remember("first", "one", "alice")
    memory.remember("second", "two", "alice")
    memory.remember("third", "three", "alice")
    memory.remember("separate", "conversation", "bob")

    assert [turn.user_query for turn in memory.history("alice")] == ["second", "third"]
    assert [turn.user_query for turn in memory.history("bob")] == ["separate"]

    memory.clear("alice")

    assert memory.history("alice") == []
    assert len(memory.history("bob")) == 1


@pytest.mark.asyncio
async def test_recipe_agent_remembers_completed_turns() -> None:
    agent = RecipeDiscoveryAgent(DiscoveryTools(StubSearchProvider()))

    await agent.run("quick tomato pasta", conversation_id="alice")

    history = agent.conversation_history("alice")
    assert len(history) == 1
    assert history[0].user_query == "quick tomato pasta"
    assert "Recipe for quick tomato pasta" in history[0].assistant_summary


@pytest.mark.asyncio
async def test_langchain_agent_receives_only_the_matching_conversation_history() -> None:
    # Bypass model construction so the memory integration can be tested offline.
    agent = object.__new__(LangChainReActDiscoveryAgent)
    RecipeDiscoveryAgent.__init__(agent, DiscoveryTools(StubSearchProvider()))
    agent._state = {}
    agent._agent = CapturingModelAgent()

    await agent.run("spicy noodles", conversation_id="alice")
    await agent.run("make them vegetarian", conversation_id="alice")
    await agent.run("chocolate cake", conversation_id="bob")

    alice_messages = agent._agent.invocations[1]["messages"]
    assert [message["role"] for message in alice_messages] == [
        "user",
        "assistant",
        "user",
    ]
    assert alice_messages[0]["content"] == "spicy noodles"
    assert "make them vegetarian" in alice_messages[-1]["content"]

    bob_messages = agent._agent.invocations[2]["messages"]
    assert len(bob_messages) == 1
    assert "chocolate cake" in bob_messages[0]["content"]
