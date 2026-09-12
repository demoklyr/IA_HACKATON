import ast
import json
import os
from dataclasses import dataclass
from typing import Any

from .models import CandidateVideo, DiscoveryRun
from .social_search import SocialSearchProvider
from .tools import DiscoveryTools


@dataclass
class AgentRuntime:
    search_provider: str


@dataclass
class ReActStep:
    thought: str
    action: str
    observation: str


class RecipeDiscoveryAgent:
    """Small deterministic fallback using the same tools as the ReAct agent."""

    def __init__(self, tools: DiscoveryTools) -> None:
        self.tools = tools
        self.trace: list[ReActStep] = []

    @property
    def runtime(self) -> AgentRuntime:
        return AgentRuntime(search_provider=type(self.tools.search_provider).__name__)

    async def run(self, user_query: str, limit: int = 3) -> DiscoveryRun:
        query = user_query.strip()
        if not query:
            raise ValueError("user_query must not be empty")

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

        return DiscoveryRun(
            queries=[query],
            raw_candidates=candidates,
            results=results,
        )

    def _record(self, thought: str, action: str, observation: str) -> None:
        self.trace.append(ReActStep(thought=thought, action=action, observation=observation))


def create_discovery_agent(
    search_provider: SocialSearchProvider | None = None,
) -> RecipeDiscoveryAgent:
    from .service import default_search_provider

    tools = DiscoveryTools(search_provider=search_provider or default_search_provider())
    return RecipeDiscoveryAgent(tools)


class LangChainReActDiscoveryAgent(RecipeDiscoveryAgent):
    def __init__(self, tools: DiscoveryTools, model: str) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for --langchain-react")
        super().__init__(tools)

        from langchain.agents import create_agent
        from langchain.tools import tool

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
            tools=[search_videos, rank_candidates],
            system_prompt=(
                "You are a minimal ReAct recipe-video discovery agent. "
                "Turn the user's request into a precise search query, call search_videos, "
                "then call rank_candidates. You may search again with a better query when useful. "
                "Never invent URLs. After ranking, give a concise final answer."
            ),
        )

    async def run(self, user_query: str, limit: int = 3) -> DiscoveryRun:
        query = user_query.strip()
        if not query:
            raise ValueError("user_query must not be empty")

        self.trace = []
        self._state = {}
        await self._agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Find recipe videos for: {query}\n"
                            f"Return at most {limit} ranked results."
                        ),
                    }
                ]
            }
        )

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

        return DiscoveryRun(
            queries=queries if isinstance(queries, list) else [],
            raw_candidates=raw_candidates,
            results=results if isinstance(results, list) else [],
        )


def create_langchain_react_agent(
    search_provider: SocialSearchProvider | None = None,
    model: str | None = None,
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
    )


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
