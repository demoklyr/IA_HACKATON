import ast
import json
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import CandidateVideo, DiscoveryRun
from .social_search import SocialSearchProvider
from .tools import DiscoveryTools


SYSTEM_PROMPT_PATH = Path(__file__).with_name("prompts") / "system_prompt.md"


@dataclass
class AgentRuntime:
    search_provider: str


@dataclass
class ReActStep:
    thought: str
    action: str
    observation: str


@dataclass(frozen=True)
class ConversationTurn:
    """A compact turn kept as context for a later discovery request."""

    user_query: str
    assistant_summary: str


class ConversationMemory:
    """Bounded, in-process conversation history, isolated by conversation id."""

    def __init__(self, max_turns: int = 6) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be at least 1")
        self.max_turns = max_turns
        self._turns: dict[str, deque[ConversationTurn]] = {}

    def history(self, conversation_id: str = "default") -> list[ConversationTurn]:
        return list(self._turns.get(_normalize_conversation_id(conversation_id), ()))

    def messages(self, conversation_id: str = "default") -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for turn in self.history(conversation_id):
            messages.extend(
                (
                    {"role": "user", "content": turn.user_query},
                    {"role": "assistant", "content": turn.assistant_summary},
                )
            )
        return messages

    def remember(
        self,
        user_query: str,
        assistant_summary: str,
        conversation_id: str = "default",
    ) -> None:
        normalized_id = _normalize_conversation_id(conversation_id)
        turns = self._turns.setdefault(
            normalized_id,
            deque(maxlen=self.max_turns),
        )
        turns.append(
            ConversationTurn(
                user_query=user_query,
                assistant_summary=assistant_summary,
            )
        )

    def clear(self, conversation_id: str | None = None) -> None:
        if conversation_id is None:
            self._turns.clear()
        else:
            self._turns.pop(_normalize_conversation_id(conversation_id), None)


class RecipeDiscoveryAgent:
    """Small deterministic fallback using the same tools as the ReAct agent."""

    def __init__(
        self,
        tools: DiscoveryTools,
        memory: ConversationMemory | None = None,
    ) -> None:
        self.tools = tools
        self.memory = memory or ConversationMemory()
        self.trace: list[ReActStep] = []

    @property
    def runtime(self) -> AgentRuntime:
        return AgentRuntime(search_provider=type(self.tools.search_provider).__name__)

    async def run(
        self,
        user_query: str,
        limit: int = 3,
        *,
        conversation_id: str = "default",
    ) -> DiscoveryRun:
        query = user_query.strip()
        if not query:
            raise ValueError("user_query must not be empty")
        _normalize_conversation_id(conversation_id)

        self.trace = []
        self._record(
            thought="I should search for videos matching the user's request.",
            action="search_videos",
            observation="pending",
        )
        candidates = await self.tools.search_videos(query, limit=10)
        self.trace[-1].observation = f"found {len(candidates)} candidates"

        self._record(
            thought="I should rank the candidates against the original request.",
            action="rank_candidates",
            observation="pending",
        )
        results = self.tools.rank(candidates, query)[:max(limit, 0)]
        self.trace[-1].observation = f"selected {len(results)} top results"

        discovery = DiscoveryRun(
            queries=[query],
            raw_candidates=candidates,
            results=results,
        )
        self.memory.remember(
            query,
            _summarize_discovery(discovery),
            conversation_id,
        )
        return discovery

    def conversation_history(
        self,
        conversation_id: str = "default",
    ) -> list[ConversationTurn]:
        return self.memory.history(conversation_id)

    def clear_memory(self, conversation_id: str | None = None) -> None:
        """Forget one conversation, or every conversation when no id is given."""
        self.memory.clear(conversation_id)

    def _record(self, thought: str, action: str, observation: str) -> None:
        self.trace.append(ReActStep(thought=thought, action=action, observation=observation))


def create_discovery_agent(
    search_provider: SocialSearchProvider | None = None,
    *,
    memory: ConversationMemory | None = None,
) -> RecipeDiscoveryAgent:
    from .service import default_search_provider

    tools = DiscoveryTools(search_provider=search_provider or default_search_provider())
    return RecipeDiscoveryAgent(tools, memory=memory)


class LangChainReActDiscoveryAgent(RecipeDiscoveryAgent):
    def __init__(
        self,
        tools: DiscoveryTools,
        model: str,
        memory: ConversationMemory | None = None,
        system_prompt: str | None = None,
    ) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for --langchain-react")
        super().__init__(tools, memory=memory)

        from langchain.agents import create_agent
        from langchain.tools import tool

        from app.instagram_recipe_tool import create_recipe_from_instagram

        self._state: dict[str, object] = {}

        @tool
        async def search_videos(query: str, limit: int = 10) -> str:
            """Search recipe videos using one precise query and return candidate JSON."""
            normalized_query = query.strip()
            if not normalized_query:
                raise ValueError("query must not be empty")

            candidates = await self.tools.search_videos(normalized_query, limit=limit)
            queries = self._state.setdefault("queries", [])
            stored_candidates = self._state.setdefault("candidates", [])
            if isinstance(queries, list):
                queries.append(normalized_query)
            if isinstance(stored_candidates, list):
                stored_candidates.extend(candidates)

            self._record(
                "I should search for videos matching the user's request.",
                "search_videos",
                f"found {len(candidates)} candidates",
            )
            return json.dumps([candidate.model_dump() for candidate in candidates])

        @tool
        def rank_candidates(
            user_query: str,
            candidates_json: str = "",
            limit: int = 3,
        ) -> str:
            """Rank candidate video JSON; omit candidates_json to rank prior search results."""
            candidates = _coerce_candidates(candidates_json)
            if not candidates:
                stored_candidates = self._state.get("candidates", [])
                if isinstance(stored_candidates, list):
                    candidates = stored_candidates

            ranked = self.tools.rank(candidates, user_query)[:max(limit, 0)]
            self._state["results"] = ranked
            self._state["ranked"] = True
            self._record(
                "I should rank the candidates against the original request.",
                "rank_candidates",
                f"selected {len(ranked)} top results",
            )
            return json.dumps([candidate.model_dump() for candidate in ranked])

        self._agent = create_agent(
            model=model,
            tools=[search_videos, rank_candidates, create_recipe_from_instagram],
            system_prompt=system_prompt or load_system_prompt(),
        )

    async def run(
        self,
        user_query: str,
        limit: int = 3,
        *,
        conversation_id: str = "default",
    ) -> DiscoveryRun:
        query = user_query.strip()
        if not query:
            raise ValueError("user_query must not be empty")
        normalized_conversation_id = _normalize_conversation_id(conversation_id)

        self.trace = []
        self._state = {}
        messages = self.memory.messages(normalized_conversation_id)
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Find recipe videos for: {query}\n"
                    f"Return at most {limit} ranked results."
                ),
            }
        )
        agent_result = await self._agent.ainvoke({"messages": messages})

        recipe = _extract_instagram_recipe(agent_result)
        if recipe is not None:
            self._record(
                "The user asked to turn an Instagram video into a recipe.",
                "create_recipe_from_instagram",
                "created a structured recipe",
            )
            queries = self._state.get("queries", [])
            raw_candidates = self._state.get("candidates", [])
            results = self._state.get("results", [])
            discovery = DiscoveryRun(
                queries=queries if isinstance(queries, list) else [],
                raw_candidates=(
                    raw_candidates if isinstance(raw_candidates, list) else []
                ),
                results=results if isinstance(results, list) else [],
                recipe=recipe,
            )
            self.memory.remember(
                query,
                _summarize_discovery(discovery),
                normalized_conversation_id,
            )
            return discovery

        queries = self._state.get("queries", [])
        raw_candidates = self._state.get("candidates", [])
        completed_search = isinstance(queries, list) and bool(queries)
        if not completed_search:
            raw_candidates = await self.tools.search_videos(query, limit=10)
            queries = [query]
            self._state["queries"] = queries
            self._state["candidates"] = raw_candidates
            self._record(
                "The model skipped search, so I should complete the required step.",
                "search_videos",
                f"found {len(raw_candidates)} candidates (deterministic fallback)",
            )

        if not isinstance(raw_candidates, list):
            raw_candidates = []

        if not completed_search or not self._state.get("ranked"):
            results = self.tools.rank(raw_candidates, query)[:max(limit, 0)]
            self._state["results"] = results
            self._state["ranked"] = True
            self._record(
                "The model skipped ranking, so I should complete the required step.",
                "rank_candidates",
                f"selected {len(results)} top results (deterministic fallback)",
            )
        else:
            results = self._state.get("results", [])

        discovery = DiscoveryRun(
            queries=queries if isinstance(queries, list) else [],
            raw_candidates=raw_candidates,
            results=results if isinstance(results, list) else [],
        )
        self.memory.remember(
            query,
            _summarize_discovery(discovery),
            normalized_conversation_id,
        )
        return discovery


def create_langchain_react_agent(
    search_provider: SocialSearchProvider | None = None,
    model: str | None = None,
    *,
    memory: ConversationMemory | None = None,
    system_prompt: str | None = None,
) -> LangChainReActDiscoveryAgent:
    from .service import default_search_provider

    tools = DiscoveryTools(search_provider=search_provider or default_search_provider())
    return LangChainReActDiscoveryAgent(
        tools=tools,
        model=model
        or os.getenv(
            "DISCOVERY_REACT_MODEL",
            os.getenv("DISCOVERY_MODEL", "openai:gpt-4.1-mini"),
        ),
        memory=memory,
        system_prompt=system_prompt,
    )


def load_system_prompt() -> str:
    """Load the editable discovery-agent instructions from disk."""
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()


def _normalize_conversation_id(conversation_id: str) -> str:
    normalized = conversation_id.strip()
    if not normalized:
        raise ValueError("conversation_id must not be empty")
    return normalized


def _summarize_discovery(discovery: DiscoveryRun) -> str:
    """Keep useful context without retaining bulky tool-call transcripts."""
    if discovery.recipe is not None:
        ingredient_count = len(discovery.recipe.get("ingredients", []))
        step_count = len(discovery.recipe.get("steps", []))
        return (
            "I created a structured recipe from Instagram with "
            f"{ingredient_count} ingredients and {step_count} steps."
        )

    queries = ", ".join(discovery.queries) or "none"
    if not discovery.results:
        return f"I searched with: {queries}. No recipe videos were selected."

    selected = "; ".join(
        f"{candidate.caption or 'Untitled video'} ({candidate.url})"
        for candidate in discovery.results
    )
    return f"I searched with: {queries}. Selected recipe videos: {selected}"


def _loads_loose(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return None


def _coerce_candidates(value: Any) -> list[CandidateVideo]:
    parsed = _loads_loose(value)
    if not isinstance(parsed, list):
        return []
    candidates: list[CandidateVideo] = []
    for item in parsed:
        if isinstance(item, CandidateVideo):
            candidates.append(item)
        elif isinstance(item, dict):
            candidates.append(CandidateVideo.model_validate(item))
    return candidates


def _extract_instagram_recipe(agent_result: Any) -> dict[str, Any] | None:
    """Read the direct Instagram tool result from a LangChain agent response."""
    if not isinstance(agent_result, dict):
        return None
    messages = agent_result.get("messages")
    if not isinstance(messages, list):
        return None

    for message in reversed(messages):
        if isinstance(message, dict):
            name = message.get("name")
            content = message.get("content")
        else:
            name = getattr(message, "name", None)
            content = getattr(message, "content", None)

        if name != "create_recipe_from_instagram":
            continue
        recipe = _loads_loose(content)
        if isinstance(recipe, dict) and {"steps", "ingredients"} <= recipe.keys():
            return recipe
    return None
