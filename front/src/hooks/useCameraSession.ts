import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { ServerSessionMessage, SessionState } from "../types";

const FRAME_INTERVAL_MS = 1000; // send a frame to the CV agent once per second

interface UseCameraSessionResult {
  videoRef: React.RefObject<HTMLVideoElement>;
  canvasRef: React.RefObject<HTMLCanvasElement>;
  sessionState: SessionState;
  currentStepIndex: number;
  isAgentSpeaking: boolean;
  lastInstruction: string | null;
  lastWarning: string | null;
  detectedItems: string | null;
  requiredObjects: string[] | null;
  start: (recipeId: string) => Promise<void>;
  pause: () => void;
  resume: () => void;
  stop: () => void;
  requestNextStep: () => void;
}

export function useCameraSession(): UseCameraSessionResult {
  const videoRef = useRef<HTMLVideoElement>(null!);
  const canvasRef = useRef<HTMLCanvasElement>(null!);
  const wsRef = useRef<WebSocket | null>(null);
  const frameTimerRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  const [sessionState, setSessionState] = useState<SessionState>("idle");
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false);
  const [lastInstruction, setLastInstruction] = useState<string | null>(null);
  const [lastWarning, setLastWarning] = useState<string | null>(null);
  const [detectedItems, setDetectedItems] = useState<string | null>(null);
  const [requiredObjects, setRequiredObjects] = useState<string[] | null>(null);

  const sendFrame = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    const ws = wsRef.current;
    if (!video || !canvas || !ws || ws.readyState !== WebSocket.OPEN) return;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const data = canvas.toDataURL("image/jpeg", 0.6).split(",")[1];

    ws.send(
      JSON.stringify({ type: "frame", timestamp: Date.now(), data })
    );
  }, []);

  const handleServerMessage = useCallback((raw: MessageEvent) => {
    const msg = JSON.parse(raw.data) as ServerSessionMessage;
    switch (msg.type) {
      case "instruction":
        setCurrentStepIndex(msg.step_index);
        setLastInstruction(msg.text);
        setRequiredObjects(msg.required_objects || null);
        break;
      case "speaking_start":
        setIsAgentSpeaking(true);
        break;
      case "speaking_end":
        setIsAgentSpeaking(false);
        break;
      case "step_complete":
        setCurrentStepIndex(msg.step_index + 1);
        break;
      case "recipe_complete":
        setSessionState("complete");
        break;
      case "warning":
        setLastWarning(msg.text);
        break;
      case "error":
        console.error("CV session error:", msg.text);
        break;
      case "detected_items":
        setDetectedItems(msg.text);
        break;
    }
  }, []);

  const start = useCallback(
    async (recipeId: string) => {
      setSessionState("active"); // On passe en active de suite pour forcer l'affichage de <video>
      
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        streamRef.current = stream;
        
        // La balise <video> a eu largement le temps d'apparaître pendant l'attente de getUserMedia
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch(console.error);
        }
      } catch (err) {
        console.error("Camera access error:", err);
      }
      
      const { session_id, ws_url } = await api.initCameraSession(recipeId);
      sessionIdRef.current = session_id;

      const ws = new WebSocket(ws_url);
      ws.onmessage = handleServerMessage;
      ws.onopen = () => {
        setSessionState("active");
        frameTimerRef.current = window.setInterval(sendFrame, FRAME_INTERVAL_MS);
      };
      ws.onclose = () => {
        if (frameTimerRef.current) window.clearInterval(frameTimerRef.current);
      };
      wsRef.current = ws;
    },
    [handleServerMessage, sendFrame]
  );

  const pause = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ type: "pause" }));
    if (frameTimerRef.current) window.clearInterval(frameTimerRef.current);
    setSessionState("paused");
    if (sessionIdRef.current) api.setSessionPaused(sessionIdRef.current, true);
  }, []);

  const resume = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ type: "resume" }));
    frameTimerRef.current = window.setInterval(sendFrame, FRAME_INTERVAL_MS);
    setSessionState("active");
    if (sessionIdRef.current) api.setSessionPaused(sessionIdRef.current, false);
  }, [sendFrame]);

  const requestNextStep = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ type: "next_step_manual" }));
  }, []);

  const stop = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ type: "end" }));
    wsRef.current?.close();
    if (frameTimerRef.current) window.clearInterval(frameTimerRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    setSessionState("idle");
  }, []);

  useEffect(() => stop, [stop]);

  return {
    videoRef,
    canvasRef,
    sessionState,
    currentStepIndex,
    isAgentSpeaking,
    lastInstruction,
    lastWarning,
    detectedItems,
    requiredObjects,
    start,
    pause,
    resume,
    stop,
    requestNextStep,
  };
}
