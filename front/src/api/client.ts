import type {
  Recipe,
  RawRecipeResponse,
  RawRecipeStep,
  RawRecipeIngredient,
  ApiErrorResponse,
  StartFromAudioResponse,
  CVSessionInitResponse,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// URL validation — mirrors _validated_instagram_url() in the Python tool:
// https, host is instagram.com (or a subdomain), path is /p|reel|reels|tv/<shortcode>/
// Validating client-side gives instant feedback instead of waiting on a
// network round-trip for something the backend will reject anyway.
// ---------------------------------------------------------------------------
const INSTAGRAM_PATH_RE = /^\/(p|reel|reels|tv)\/([A-Za-z0-9_-]+)\/?$/;

export interface UrlValidationResult {
  valid: boolean;
  normalizedUrl?: string;
  error?: string;
}

export function validateInstagramUrl(value: string): UrlValidationResult {
  let parsed: URL;
  try {
    parsed = new URL(value.trim());
  } catch {
    return { valid: false, error: "Ce n'est pas une URL valide." };
  }

  const hostname = parsed.hostname.toLowerCase();
  const isInstagram = hostname === "instagram.com" || hostname.endsWith(".instagram.com");
  const match = parsed.pathname.match(INSTAGRAM_PATH_RE);

  if (parsed.protocol !== "https:" || !isInstagram || !match) {
    return {
      valid: false,
      error: "Attendu : un lien public Instagram (post ou reel), en https.",
    };
  }

  const [, postType, shortcode] = match;
  return { valid: true, normalizedUrl: `https://www.instagram.com/${postType}/${shortcode}/` };
}

async function readError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as ApiErrorResponse;
    if (body?.detail) return body.detail;
  } catch {
    // body wasn't JSON — fall through
  }
  return `Erreur ${res.status} : ${res.statusText}`;
}

function ensureRawText(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

/**
 * Adapts whatever recipe.json actually contains into the canonical shape the
 * UI renders. Defensive by design: the backend tool only guarantees "steps"
 * and "ingredients" keys exist, not their internal structure.
 */
export function normalizeRecipe(raw: RawRecipeResponse, sourceUrl: string): Recipe {
  const steps = (raw.steps ?? []).map((step: RawRecipeStep, i: number) => {
    const instruction =
      (typeof step === "string" ? step : step.instruction ?? step.text ?? step.description ?? step.step) ??
      `Étape ${i + 1}`;
    const durationRaw = typeof step === "object" ? step.duration_seconds ?? step.duration : undefined;
    return {
      id: `step-${i}`,
      order: i,
      instruction,
      duration_seconds: typeof durationRaw === "number" ? durationRaw : undefined,
    };
  });

  const ingredients = (raw.ingredients ?? []).map((ing: RawRecipeIngredient, i: number) => {
    const name =
      (typeof ing === "string" ? ing : ing.name ?? ing.item ?? ing.ingredient) ?? `Ingrédient ${i + 1}`;
    const quantityRaw = typeof ing === "object" ? ing.quantity ?? ing.amount : undefined;
    const unit = typeof ing === "object" ? ing.unit : undefined;
    const quantity =
      quantityRaw !== undefined ? `${quantityRaw}${unit ? ` ${unit}` : ""}` : undefined;
    return {
      id: `ing-${i}`,
      name,
      quantity,
      optional: typeof ing === "object" ? ing.optional : undefined,
    };
  });

  return {
    id: sourceUrl, // no recipe id is returned by the backend — the source URL doubles as a stable key
    title: ensureRawText(raw.name) ?? "Recette",
    source_url: sourceUrl,
    ingredients,
    steps,
  };
}

export const api = {
  /**
   * Calls create_recipe_from_instagram end-to-end. This is a BLOCKING call —
   * the promise only resolves once the full pipeline finishes (can take
   * several minutes) or rejects with the backend's error detail.
   */
  async createRecipeFromUrl(url: string): Promise<Recipe> {
    const validation = validateInstagramUrl(url);
    if (!validation.valid) throw new Error(validation.error);

    const res = await fetch(`${BASE_URL}/api/recipe/from-url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instagram_url: validation.normalizedUrl }),
    });

    if (!res.ok) throw new Error(await readError(res));

    const raw = (await res.json()) as RawRecipeResponse;
    return normalizeRecipe(raw, validation.normalizedUrl!);
  },

  /** Kick off recipe extraction from a recorded voice note. Contract unconfirmed — see types.ts note. */
  async startFromAudio(blob: Blob): Promise<StartFromAudioResponse> {
    const form = new FormData();
    form.append("audio", blob, "note.webm");
    const res = await fetch(`${BASE_URL}/api/recipe/from-audio`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error(await readError(res));
    return res.json();
  },

  async initCameraSession(recipeId: string): Promise<CVSessionInitResponse> {
    const res = await fetch(`${BASE_URL}/api/session/init`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recipe_id: recipeId }),
    });
    if (!res.ok) throw new Error(await readError(res));
    return res.json();
  },

  async setSessionPaused(sessionId: string, paused: boolean): Promise<void> {
    await fetch(`${BASE_URL}/api/session/${sessionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paused }),
    });
  },
};
