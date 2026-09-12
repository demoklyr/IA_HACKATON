from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess
import sys
import os
import json
import time
import threading
import itertools
import base64
import tempfile
from google import genai
import asyncio

try:
    import speech_recognition as sr
    HAS_SPEECH = True
except ImportError:
    HAS_SPEECH = False

try:
    from gtts import gTTS
    HAS_GTTS = True
except ImportError:
    HAS_GTTS = False

def speak(text):
    """Fonction TTS fluide utilisant Google Text-to-Speech."""
    def run_tts():
        if HAS_GTTS:
            try:
                tts = gTTS(text=text, lang='en')
                fd, path = tempfile.mkstemp(suffix=".mp3")
                os.close(fd)
                tts.save(path)
                os.system(f"afplay {path}")
                os.remove(path)
            except Exception as e:
                os.system(f"say '{text}'")
        else:
            os.system(f"say '{text}'")
            
    threading.Thread(target=run_tts, daemon=True).start()

# Global state for voice trigger
voice_trigger = False

def listen_for_done():
    """Écoute en permanence le mot 'terminé' en arrière-plan."""
    global voice_trigger
    r = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source)
            while True:
                try:
                    audio = r.listen(source, timeout=2, phrase_time_limit=3)
                    text = r.recognize_google(audio, language="en-US").lower()
                    print("🎤 You said :", text)
                    if any(phrase in text for phrase in ["done", "i'm done", "finished", "i am done", "next"]):
                        voice_trigger = True
                except:
                    continue
    except Exception as e:
        print("Microphone Error:", e)

if HAS_SPEECH:
    threading.Thread(target=listen_for_done, daemon=True).start()
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

def enhance_recipe_with_gemini(recipe: dict) -> dict:
    key = os.getenv("GEMINI_API_KEY_1")
    if not key:
        print("No Gemini API key found, skipping enhancement.")
        return recipe
        
    try:
        client = genai.Client(api_key=key)
        prompt = f"""
        Here is a recipe in JSON format:
        {json.dumps(recipe, ensure_ascii=False)}
        
        For each step in the `steps` array, add a `required_objects` list containing ONLY the physical food ingredients and kitchen utensils needed for that step. 
        Keep the exact same JSON structure, just add this field to each step.
        Return ONLY valid JSON. Do not include markdown blocks.
        """
        
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt
        )
        
        text = response.text.strip()
        if text.startswith("```json"): text = text[7:]
        if text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        
        enhanced = json.loads(text.strip())
        
        # If Gemini returned a list of recipes instead of a single recipe object, take the first one
        if isinstance(enhanced, list) and len(enhanced) > 0:
            enhanced = enhanced[0]
        
        with open("current_recipe.json", "w", encoding="utf-8") as f:
            json.dump(enhanced, f, ensure_ascii=False, indent=2)
            
        return enhanced
    except Exception as e:
        print(f"Failed to enhance recipe with Gemini: {e}")
        with open("current_recipe.json", "w", encoding="utf-8") as f:
            json.dump(recipe, f, ensure_ascii=False, indent=2)
        return recipe


app = FastAPI(title="IA Thinker API")


# =========================
# CORS
# =========================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
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

class InitSessionRequest(BaseModel):
    recipe_id: str

class PauseSessionRequest(BaseModel):
    paused: bool


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
        
        # Enrich the recipe with Gemini to add required_objects and save it for cooking_agent
        enhanced_recipe = enhance_recipe_with_gemini(recipe)

        return enhanced_recipe

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


@app.post("/api/session/init")
def init_session(payload: InitSessionRequest):
    return {
        "session_id": "session-1234",
        "ws_url": "ws://127.0.0.1:8000/api/session/ws"
    }


@app.patch("/api/session/{session_id}")
def update_session(session_id: str, payload: PauseSessionRequest):
    return {"status": "ok"}


@app.websocket("/api/session/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    global voice_trigger
    
    recipe_path = "current_recipe.json"
    if not os.path.exists(recipe_path):
        await websocket.send_json({"type": "error", "text": "current_recipe.json n'existe pas."})
        return
        
    with open(recipe_path, "r", encoding="utf-8") as f:
        recipe = json.load(f)
    steps = recipe.get("steps", [])
    
    all_recipe_objects = set()
    for step in steps:
        for obj in step.get("required_objects", []):
            all_recipe_objects.add(obj.lower())
            
    current_step_idx = 0
    last_analysis_time = 0
    INTERVALLE_ANALYSE = 4.5
    last_error_time = 0
    is_analyzing = False
    
    API_KEYS = [os.getenv(f"GEMINI_API_KEY_{i}") for i in range(1, 4)]
    API_KEYS = [k for k in API_KEYS if k]
    if not API_KEYS:
        API_KEYS = [os.getenv("GEMINI_API_KEY")]
        
    clients = [genai.Client(api_key=key) for key in API_KEYS if key]
    if not clients:
        await websocket.send_json({"type": "error", "text": "Aucune clé API Gemini trouvée."})
        return
        
    client_cycle = itertools.cycle(clients)
    
    # Send first instruction
    if current_step_idx < len(steps):
        step = steps[current_step_idx]
        instruction = step.get("description", step.get("instruction", ""))
        required_objects = step.get("required_objects", [])
        speak(instruction)
        await websocket.send_json({"type": "instruction", "step_index": current_step_idx, "text": instruction, "required_objects": required_objects})
        
    def appel_gemini_vision(image_bytes):
        nonlocal last_error_time, is_analyzing
        try:
            client_actuel = next(client_cycle)
            response = client_actuel.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=[
                    genai.types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                    "Identify ONLY the specific food ingredients and specific kitchen utensils (e.g. fork, knife, pan, bowl) that the user is actively manipulating or holding. "
                    "Do NOT list background elements, furniture, large appliances (stove, oven), people, or body parts (hand, fingers). "
                    "Reply ONLY with a short comma-separated list of these exact items (e.g., apple, knife, tomato). "
                    "If there are no food ingredients or utensils actively being manipulated, reply EXACTLY with the word 'nothing'."
                ]
            )
            
            if response.text:
                texte_brut = response.text.strip().lower()
                asyncio.run(websocket.send_json({"type": "detected_items", "text": texte_brut}))
                
                if current_step_idx < len(steps):
                    allowed_objects = set()
                    for i in range(current_step_idx + 1):
                        for obj in steps[i].get("required_objects", []):
                            allowed_objects.add(obj.lower())
                    
                    objets_detectes = [x.strip() for x in texte_brut.split(',') if x.strip() and x.strip() not in ["nothing", "none", "n/a", "no", "rien"]]
                    
                    for obj in objets_detectes:
                        if obj not in allowed_objects:
                            is_in_recipe_somewhere = any(req in obj or obj in req for req in all_recipe_objects)
                            
                            if is_in_recipe_somewhere and (time.time() - last_error_time > 6.0):
                                last_error_time = time.time()
                                msg = f"This is not the time to use the {obj}, put it aside for now."
                                speak(msg)
                                asyncio.run(websocket.send_json({"type": "warning", "text": msg}))
                                break 
                                
                            elif not is_in_recipe_somewhere and (time.time() - last_error_time > 6.0):
                                last_error_time = time.time()
                                msg = f"You don't need the {obj} for this recipe."
                                speak(msg)
                                asyncio.run(websocket.send_json({"type": "warning", "text": msg}))
                                break
        except Exception as e:
            print(f"API Error: {e}")
        finally:
            is_analyzing = False
            
    try:
        while True:
            # Check if voice triggered a step advance
            if voice_trigger:
                voice_trigger = False
                speak("Great, moving on to the next step.")
                await websocket.send_json({"type": "step_complete", "step_index": current_step_idx})
                current_step_idx += 1
                
                if current_step_idx >= len(steps):
                    speak("Congratulations, the recipe is complete!")
                    await websocket.send_json({"type": "recipe_complete"})
                else:
                    step = steps[current_step_idx]
                    instruction = step.get("description", step.get("instruction", ""))
                    required_objects = step.get("required_objects", [])
                    speak(instruction)
                    await websocket.send_json({"type": "instruction", "step_index": current_step_idx, "text": instruction, "required_objects": required_objects})
            
            # Use a small timeout so we can continuously check voice_trigger
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.2)
                msg = json.loads(data)
                
                if msg.get("type") == "next_step_manual":
                    voice_trigger = True
                
                elif msg.get("type") == "frame":
                    current_time = time.time()
                    if not is_analyzing and (current_time - last_analysis_time > INTERVALLE_ANALYSE):
                        last_analysis_time = current_time
                        is_analyzing = True
                        image_bytes = base64.b64decode(msg["data"])
                        # Start Gemini call in a background thread to avoid blocking the websocket loop
                        thread = threading.Thread(target=appel_gemini_vision, args=(image_bytes,))
                        thread.daemon = True
                        thread.start()
            except asyncio.TimeoutError:
                continue
    except Exception as e:
        print("WebSocket Error or Closed:", e)
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
