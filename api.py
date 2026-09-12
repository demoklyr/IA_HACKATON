import asyncio
import re
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.discovery.agent import ConversationMemory, create_langchain_react_agent
from app.instagram_recipe_tool import (
    _run_instagram_recipe_workflow,
    _validated_instagram_url,
    InstagramRecipeWorkflowError,
)


app = FastAPI(title="IA Thinker API")


# =========================
# CORS
# =========================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# Models
# =========================

class InstagramRecipeRequest(BaseModel):
    instagram_url: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=3, ge=1, le=6)


class ChatResponse(BaseModel):
    type: Literal["message", "recipe"]
    message: str
    results: list[dict] = Field(default_factory=list)
    instagram_post: dict | None = None
    recipe: dict | None = None
    source_url: str | None = None


_chat_agent = None
_chat_lock = asyncio.Lock()


def _agent_message(discovery) -> str:
    if discovery.assistant_message:
        return discovery.assistant_message
    if discovery.instagram_post is not None:
        return discovery.instagram_post.get("description") or "Voici ce post Instagram."
    if discovery.results:
        return "J'ai trouvé ces recettes. Laquelle veux-tu cuisiner ?"
    return "Je n'ai pas encore trouvé de résultat. Peux-tu préciser ce que tu veux cuisiner ?"


def _bare_instagram_recipe_request(message: str) -> tuple[str, str | None]:
    """Keep the old paste-a-URL feature while routing it through the agent tool."""
    stripped = message.strip()
    if not re.fullmatch(r"https://\S+", stripped):
        return stripped, None
    try:
        normalized_url, _ = _validated_instagram_url(stripped)
    except ValueError:
        return stripped, None
    return (
        f"Crée la recette complète à partir de cette vidéo Instagram : {normalized_url}",
        normalized_url,
    )


# =========================
# Routes
# =========================

@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "IA Thinker API",
    }


@app.post("/api/recipe/from-url")
def create_recipe_from_url(payload: InstagramRecipeRequest):
    try:
        recipe = _run_instagram_recipe_workflow(
            payload.instagram_url
        )

        return recipe

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except InstagramRecipeWorkflowError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {error}",
        )


@app.post("/api/chat", response_model=ChatResponse)
async def chat_with_agent(payload: ChatRequest):
    """Run one conversational turn and expose only UI-safe structured output."""
    global _chat_agent

    agent_query, pasted_source_url = _bare_instagram_recipe_request(payload.message)
    try:
        # The LangChain agent stores per-run tool state on the instance, so
        # serialize turns to prevent concurrent conversations from mixing it.
        async with _chat_lock:
            if _chat_agent is None:
                _chat_agent = create_langchain_react_agent(
                    memory=ConversationMemory(max_turns=6),
                )
            discovery = await _chat_agent.run(
                agent_query,
                limit=payload.limit,
                conversation_id=payload.conversation_id,
            )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))

    if discovery.recipe is not None:
        source_url = (
            discovery.recipe_source_url
            or discovery.recipe.get("source_url")
            or pasted_source_url
        )
        return ChatResponse(
            type="recipe",
            message="La recette est prête.",
            recipe=discovery.recipe,
            source_url=source_url,
        )

    return ChatResponse(
        type="message",
        message=_agent_message(discovery),
        results=[candidate.model_dump() for candidate in discovery.results],
        instagram_post=discovery.instagram_post,
    )
