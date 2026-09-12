from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.instagram_recipe_tool import (
    _run_instagram_recipe_workflow,
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