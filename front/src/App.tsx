import { useCallback, useState } from "react";
import { InputBar } from "./components/InputBar";
import { ProcessingOverlay } from "./components/ProcessingOverlay";
import { RecipeSidebar } from "./components/RecipeSidebar";
import { CameraPanel } from "./components/CameraPanel";
import { api } from "./api/client";
import { useCameraSession } from "./hooks/useCameraSession";
import type { Recipe } from "./types";
import "./styles/app.css";

type AppPhase = "input" | "processing" | "ready";

export default function App() {
  const [phase, setPhase] = useState<AppPhase>("input");
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [error, setError] = useState<string | null>(null);

  const camera = useCameraSession();

  // create_recipe_from_instagram is a single blocking call — no job_id, no
  // progress events. We just await it while ProcessingOverlay shows a
  // cosmetic, time-based progress animation.
  const handleSubmitUrl = useCallback(async (url: string) => {
    setPhase("processing");
    try {
      const recipe = await api.createRecipeFromUrl(url);
      setRecipe(recipe);
      setPhase("ready");
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const handleSubmitAudio = useCallback(async (_blob: Blob) => {
    // Not covered by the shared backend file yet — wire this up once the
    // audio-to-recipe endpoint's contract is confirmed.
    setError("L'envoi vocal n'est pas encore branché côté backend.");
  }, []);

  const handleActivateCamera = useCallback(() => {
    if (recipe) camera.start(recipe.id);
  }, [camera, recipe]);

  if (error) {
    return (
      <div className="app app--error">
        <p>{error}</p>
        <button
          className="btn btn--primary"
          onClick={() => {
            setError(null);
            setPhase("input");
          }}
        >
          Réessayer
        </button>
      </div>
    );
  }

  if (phase === "input") {
    return (
      <div className="app app--centered">
        <h1 className="app__hero-title">
          Colle un reel, <span className="app__hero-accent">on cuisine.</span>
        </h1>
        <InputBar onSubmitUrl={handleSubmitUrl} onSubmitAudio={handleSubmitAudio} />
      </div>
    );
  }

  if (phase === "processing") {
    return (
      <div className="app app--centered">
        <ProcessingOverlay isRunning={phase === "processing"} />
      </div>
    );
  }

  return (
    <div className="app app--split">
      <RecipeSidebar
        recipe={recipe!}
        currentStepIndex={camera.currentStepIndex}
        cameraActive={camera.sessionState !== "idle"}
      />
      <main className="app__main">
        <CameraPanel
          videoRef={camera.videoRef}
          canvasRef={camera.canvasRef}
          sessionState={camera.sessionState}
          isAgentSpeaking={camera.isAgentSpeaking}
          lastInstruction={camera.lastInstruction}
          lastWarning={camera.lastWarning}
          detectedItems={camera.detectedItems}
          requiredObjects={camera.requiredObjects}
          onActivate={handleActivateCamera}
          onPause={camera.pause}
          onResume={camera.resume}
          onDisable={camera.stop}
        />
      </main>
    </div>
  );
}
