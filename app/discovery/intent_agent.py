import os
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv

from .models import SearchIntent
from .query_planner import parse_intent


class IntentParser(Protocol):
    async def parse(self, user_query: str) -> SearchIntent: ...


class RuleBasedIntentParser:
    async def parse(self, user_query: str) -> SearchIntent:
        return parse_intent(user_query)


class LangChainIntentParser:
    def __init__(self, model: str = "openai:gpt-4.1-mini") -> None:
        from langchain.agents import create_agent

        skill = Path(__file__).with_name("skills").joinpath("intent_parser.md").read_text()
        self._agent = create_agent(
            model=model,
            tools=[],
            system_prompt=skill,
            response_format=SearchIntent,
        )

    async def parse(self, user_query: str) -> SearchIntent:
        response = await self._agent.ainvoke(
            {"messages": [{"role": "user", "content": user_query}]}
        )
        intent = response["structured_response"]
        return intent.model_copy(update={"raw_query": user_query})


def default_intent_parser() -> IntentParser:
    load_dotenv()
    if os.getenv("OPENAI_API_KEY"):
        return LangChainIntentParser(os.getenv("DISCOVERY_MODEL", "openai:gpt-4.1-mini"))
    return RuleBasedIntentParser()
