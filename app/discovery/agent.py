import json
import os
import ast
from dataclasses import dataclass
from typing import Any

from .intent_agent import IntentParser, RuleBasedIntentParser, default_intent_parser
from .models import CandidateVideo, DiscoveryRun, SearchIntent
from .social_search import SocialSearchProvider
from .tools import DiscoveryTools


@dataclass
class AgentRuntime:
    intent_parser: str
    search_provider: str


@dataclass
class ReActStep:
    thought: str
    action: str
    observation: str


class RecipeDiscoveryAgent:
    def __init__(self, tools: DiscoveryTools) -> None:
        self.tools = tools
        self.trace: list[ReActStep] = []

    @property
    def runtime(self) -> AgentRuntime:
        return AgentRuntime(
            intent_parser=type(self.tools.intent_parser).__name__,
            search_provider=type(self.tools.search_provider).__name__,
        )

    async def run(self, user_query: str, limit: int = 3) -> DiscoveryRun:
        if not user_query.strip():
            raise ValueError("user_query must not be empty")

        self.trace = []

        self._record(
            thought="I need to understand the user's recipe constraints before searching.",
            action="parse_intent",
            observation="pending",
        )

        intent = await self.tools.parse_intent(user_query)
        self.trace[-1].observation = (
            f"vegetarian={intent.vegetarian}, max_time={intent.max_time_minutes}, "
            f"excluded={intent.excluded_ingredients}"
        )

        self._record(
            thought="I need search phrases that preserve the parsed constraints.",
            action="plan_queries",
            observation="pending",
        )
        queries = self.tools.plan_queries(user_query, intent)

        self.trace[-1].observation = f"planned {len(queries)} queries"

        self._record(
            thought="I should search for candidate social video URLs with the configured provider.",
            action="search_videos",
            observation="pending",
        )
        candidates = await self.tools.search_videos(queries, limit=10)

        self.trace[-1].observation = f"found {len(candidates)} candidates"

        self._record(
            thought="I should remove repeated URLs before ranking.",
            action="deduplicate",
            observation="pending",
        )
        raw_candidates = self.tools.deduplicate(candidates)

        self.trace[-1].observation = f"kept {len(raw_candidates)} unique candidates"

        self._record(
            thought="I should rank candidates against the original request and parsed intent.",
            action="rank",
            observation="pending",
        )
        results = self.tools.rank(raw_candidates, user_query, intent)[:max(limit, 0)]

        self.trace[-1].observation = f"selected {len(results)} top results"
        return DiscoveryRun(
            intent=intent,
            queries=queries,
            raw_candidates=raw_candidates,
            results=results,
        )

    def _record(self, thought: str, action: str, observation: str) -> None:
        self.trace.append(ReActStep(thought=thought, action=action, observation=observation))


def create_discovery_agent(
    intent_parser: IntentParser | None = None,
    search_provider: SocialSearchProvider | None = None,
) -> RecipeDiscoveryAgent:
    from .service import default_search_provider

    tools = DiscoveryTools(
        intent_parser=intent_parser or default_intent_parser(),
        search_provider=search_provider or default_search_provider(),
    )
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
        async def parse_intent(user_query: str) -> str:
            """Parse a natural-language recipe video request into structured constraints."""
            intent = await self.tools.parse_intent(user_query)
            self._state["intent"] = intent
            self._record(
                "I need to understand the user's recipe constraints before searching.",
                "parse_intent",
                f"vegetarian={intent.vegetarian}, max_time={intent.max_time_minutes}, excluded={intent.excluded_ingredients}",
            )
            return intent.model_dump_json()

        @tool
        async def plan_queries(user_query: str, intent_json: str) -> str:
            """Create search queries from the user request and parsed intent JSON."""
            intent = _coerce_intent(intent_json) or self._state.get("intent")
            if not isinstance(intent, SearchIntent):
                raise ValueError("plan_queries requires a parsed intent")
            queries = self.tools.plan_queries(user_query, intent)
            self._state["queries"] = queries
            self._record(
                "I need search phrases that preserve the parsed constraints.",
                "plan_queries",
                f"planned {len(queries)} queries",
            )
            return json.dumps(queries)

        @tool
        async def search_videos(queries_json: str, limit: int = 10) -> str:
            """Search for candidate recipe video URLs from a JSON list of query strings."""
            queries = _coerce_queries(queries_json) or self._state.get("queries")
            if not isinstance(queries, list):
                raise ValueError("search_videos requires planned queries")
            candidates = await self.tools.search_videos(queries, limit=limit)
            self._state["candidates"] = candidates
            self._record(
                "I should search for candidate social video URLs with the configured provider.",
                "search_videos",
                f"found {len(candidates)} candidates",
            )
            return json.dumps([candidate.model_dump() for candidate in candidates])

        @tool
        def deduplicate_candidates(candidates_json: str) -> str:
            """Deduplicate candidate video URLs from candidate JSON."""
            candidates = _coerce_candidates(candidates_json) or self._state.get("candidates")
            if not isinstance(candidates, list):
                raise ValueError("deduplicate_candidates requires candidates")
            unique_candidates = self.tools.deduplicate(candidates)
            self._state["raw_candidates"] = unique_candidates
            self._record(
                "I should remove repeated URLs before ranking.",
                "deduplicate_candidates",
                f"kept {len(unique_candidates)} unique candidates",
            )
            return json.dumps([candidate.model_dump() for candidate in unique_candidates])

        @tool
        def rank_candidates(candidates_json: str, user_query: str, intent_json: str, limit: int = 3) -> str:
            """Rank candidate videos against the user request and parsed intent JSON."""
            candidates = _coerce_candidates(candidates_json) or self._state.get("raw_candidates")
            intent = _coerce_intent(intent_json) or self._state.get("intent")
            if not isinstance(candidates, list) or not isinstance(intent, SearchIntent):
                raise ValueError("rank_candidates requires candidates and parsed intent")
            ranked = self.tools.rank(candidates, user_query, intent)[:max(limit, 0)]
            self._state["results"] = ranked
            self._record(
                "I should rank candidates against the original request and parsed intent.",
                "rank_candidates",
                f"selected {len(ranked)} top results",
            )
            return json.dumps([candidate.model_dump() for candidate in ranked])

        self._agent = create_agent(
            model=model,
            tools=[
                parse_intent,
                plan_queries,
                search_videos,
                deduplicate_candidates,
                rank_candidates,
            ],
            system_prompt=(
                "You are a minimal ReAct recipe video discovery agent. "
                "Use the tools in this exact order: parse_intent, plan_queries, "
                "search_videos, deduplicate_candidates, rank_candidates. "
                "Do not invent URLs. After ranking, give a concise final answer."
            ),
        )

    async def run(self, user_query: str, limit: int = 3) -> DiscoveryRun:
        if not user_query.strip():
            raise ValueError("user_query must not be empty")

        self.trace = []
        self._state = {}
        await self._agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Find recipe videos for: {user_query}\n"
                            f"Return at most {limit} ranked results."
                        ),
                    }
                ]
            }
        )

        intent = self._state.get("intent")
        queries = self._state.get("queries", [])
        raw_candidates = self._state.get("raw_candidates", [])
        results = self._state.get("results", [])
        if not isinstance(intent, SearchIntent):
            raise RuntimeError("LangChain ReAct agent did not call parse_intent")
        return DiscoveryRun(
            intent=intent,
            queries=queries if isinstance(queries, list) else [],
            raw_candidates=raw_candidates if isinstance(raw_candidates, list) else [],
            results=results if isinstance(results, list) else [],
        )


def create_langchain_react_agent(
    intent_parser: IntentParser | None = None,
    search_provider: SocialSearchProvider | None = None,
    model: str | None = None,
) -> LangChainReActDiscoveryAgent:
    from .service import default_search_provider

    tools = DiscoveryTools(
        intent_parser=intent_parser or RuleBasedIntentParser(),
        search_provider=search_provider or default_search_provider(),
    )
    return LangChainReActDiscoveryAgent(
        tools=tools,
        model=model or os.getenv("DISCOVERY_REACT_MODEL", os.getenv("DISCOVERY_MODEL", "openai:gpt-4.1-mini")),
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


def _coerce_queries(value: Any) -> list[str]:
    parsed = _loads_loose(value)
    if isinstance(parsed, list):
        return [str(item) for item in parsed if str(item).strip()]
    return []


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


def _coerce_intent(value: Any) -> SearchIntent | None:
    if isinstance(value, SearchIntent):
        return value
    if isinstance(value, str):
        try:
            return SearchIntent.model_validate_json(value)
        except ValueError:
            pass
    parsed = _loads_loose(value)
    if isinstance(parsed, dict):
        return SearchIntent.model_validate(parsed)
    return None
