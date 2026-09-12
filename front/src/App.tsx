import { useCallback, useState } from "react";
import { ChatPanel, type ChatMessage } from "./components/ChatPanel";
import { RecipeSidebar } from "./components/RecipeSidebar";
import { CameraPanel } from "./components/CameraPanel";
import { api } from "./api/client";
import { useCameraSession } from "./hooks/useCameraSession";
import type { Recipe } from "./types";
import "./styles/app.css";

type AppPhase = "chat" | "ready";

const initialMessage: ChatMessage = {
  id: "welcome",
  role: "assistant",
  text: "Bonjour ! Qu'est-ce qui te ferait plaisir ? Je peux chercher une recette ou transformer un Reel en recette guidée.",
};

export default function App() {
  const [phase, setPhase] = useState<AppPhase>("chat");
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([initialMessage]);
  const [sending, setSending] = useState(false);
  const [conversationId] = useState(() =>
    globalThis.crypto?.randomUUID?.() ?? `conversation-${Date.now()}`,
  );

  const camera = useCameraSession();

  const handleSend = useCallback(async (message: string) => {
    setMessages((current) => [
      ...current,
      { id: `user-${Date.now()}`, role: "user", text: message },
    ]);
    setSending(true);
    setError(null);
    try {
      const response = await api.sendChat(message, conversationId);
      if (response.type === "recipe") {
        setRecipe(response.recipe);
        setPhase("ready");
        return;
      }
      setMessages((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          text: response.message,
          results: response.results,
          instagramPost: response.instagram_post,
        },
      ]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  }, [conversationId]);

  const handleActivateCamera = useCallback(() => {
    if (recipe) camera.start(recipe.id);
  }, [camera, recipe]);

  if (phase === "chat") {
    return (
      <div className="app app--chat">
        <ChatPanel messages={messages} sending={sending} error={error} onSend={handleSend} />
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
