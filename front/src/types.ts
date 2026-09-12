// ---------------------------------------------------------------------------
// Recipe extraction contract — matches create_recipe_from_instagram (LangChain
// tool). That tool is SYNCHRONOUS: the backend endpoint calls it and blocks
// until the whole pipeline (download -> transcribe -> frame extraction ->
// frame analysis -> recipe extraction) finishes, then returns the recipe, or
// an HTTP error if any stage failed. There is no job_id, no progress events,
// no SSE — the frontend only sees "pending" or "done/error".
//
// The Python tool types the recipe as `dict[str, Any]`, only guaranteeing
// "steps" and "ingredients" keys exist — the shape of each item is NOT
// pinned down by a Pydantic schema. RawRecipeStep / RawRecipeIngredient below
// are intentionally loose; `normalizeRecipe()` in api/client.ts adapts
// whatever comes back into the canonical Recipe/RecipeStep/Ingredient shape
// the UI renders. Tighten these once extract_recipe.py's real output schema
// is confirmed.
// ---------------------------------------------------------------------------

export type RawRecipeStep =
  | string
  | {
      instruction?: string;
      text?: string;
      description?: string;
      step?: string;
      duration_seconds?: number;
      duration?: number;
      [key: string]: unknown;
    };

export type RawRecipeIngredient =
  | string
  | {
      name?: string;
      item?: string;
      ingredient?: string;
      quantity?: string | number;
      amount?: string | number;
      unit?: string;
      optional?: boolean;
      [key: string]: unknown;
    };

/** Raw shape returned by POST /api/recipe/from-url, mirroring recipe.json. */
export interface RawRecipeResponse {
  title?: string;
  steps: RawRecipeStep[];
  ingredients: RawRecipeIngredient[];
  [key: string]: unknown;
}

export interface Ingredient {
  id: string;
  name: string;
  quantity?: string;
  optional?: boolean;
}

export interface RecipeStep {
  id: string;
  order: number;
  instruction: string;
  duration_seconds?: number;
}

export interface Recipe {
  id: string;
  title: string;
  source_url: string;
  thumbnail_url?: string;
  ingredients: Ingredient[];
  steps: RecipeStep[];
}

export interface StartFromUrlRequest {
  instagram_url: string;
}

/** Error body the backend is expected to return (mirrors FastAPI's default `{"detail": "..."}`). */
export interface ApiErrorResponse {
  detail: string;
}

// multipart/form-data: { audio: Blob }
// NOTE: not covered by the shared backend file — this endpoint's contract
// is still assumed and needs confirming separately from create_recipe_from_instagram.
export interface StartFromAudioResponse {
  job_id: string;
  transcript?: string;
}

export interface StartJobResponse {
  job_id: string;
}

// ---- Live cooking / computer-vision session ----

export interface CVSessionInitRequest {
  recipe_id: string;
}

export interface CVSessionInitResponse {
  session_id: string;
  ws_url: string; // e.g. wss://.../ws/session/{session_id}
}

// Sent from client -> server over the WebSocket
export type ClientSessionMessage =
  | { type: "frame"; timestamp: number; data: string /* base64 jpeg */ }
  | { type: "pause" }
  | { type: "resume" }
  | { type: "next_step_manual" }
  | { type: "end" };

// Sent from server -> client over the WebSocket
export type ServerSessionMessage =
  | { type: "instruction"; step_index: number; text: string; audio_url?: string }
  | { type: "speaking_start" }
  | { type: "speaking_end" }
  | { type: "step_complete"; step_index: number }
  | { type: "recipe_complete" }
  | { type: "warning"; text: string } // e.g. "attention, ça brûle"
  | { type: "error"; text: string };

export type SessionState = "idle" | "paused" | "active" | "complete";
