import type { SessionState } from "../types";

interface CameraPanelProps {
  videoRef: React.RefObject<HTMLVideoElement>;
  canvasRef: React.RefObject<HTMLCanvasElement>;
  sessionState: SessionState;
  isAgentSpeaking: boolean;
  lastInstruction: string | null;
  lastWarning: string | null;
  detectedItems: string | null;
  requiredObjects: string[] | null;
  onActivate: () => void;
  onPause: () => void;
  onResume: () => void;
  onDisable: () => void;
}

export function CameraPanel({
  videoRef,
  canvasRef,
  sessionState,
  isAgentSpeaking,
  lastInstruction,
  lastWarning,
  detectedItems,
  requiredObjects,
  onActivate,
  onPause,
  onResume,
  onDisable,
}: CameraPanelProps) {
  if (sessionState === "idle") {
    return (
      <div className="camera-panel camera-panel--prompt">
        <p className="camera-panel__prompt-text">
          Ta recette est prête. Active la caméra quand tu es prêt·e à cuisiner —
          je te guiderai étape par étape.
        </p>
        <button className="btn btn--primary btn--lg" onClick={onActivate}>
          Activer la caméra
        </button>
      </div>
    );
  }

  return (
    <div className="camera-panel">
      <div className="camera-panel__video-wrap">
        <video ref={videoRef} className="camera-panel__video" autoPlay muted playsInline />
        <canvas ref={canvasRef} style={{ display: "none" }} />

        <div className={`speaking-indicator ${isAgentSpeaking ? "speaking-indicator--on" : ""}`}>
          <span />
          <span />
          <span />
        </div>

        {sessionState === "paused" && <div className="camera-panel__paused-badge">En pause</div>}
        
        {detectedItems && (
          <div style={{ position: 'absolute', bottom: '16px', right: '16px', background: 'rgba(0,0,0,0.6)', padding: '6px 12px', borderRadius: '8px', color: '#0f0', fontSize: '14px', zIndex: 10 }}>
            Gemini voit: {detectedItems || "rien"}
          </div>
        )}
      </div>

      {lastWarning && <div className="camera-panel__warning">{lastWarning}</div>}

      <div className="camera-panel__instruction">
        {lastInstruction ?? "En attente de la première étape…"}
      </div>
      
      {requiredObjects && requiredObjects.length > 0 && (
        <div style={{ background: 'var(--slate-light)', padding: '12px', borderRadius: '8px', fontSize: '0.9rem', color: 'rgba(243, 239, 230, 0.8)' }}>
          <strong style={{ color: 'var(--carrot-dim)' }}>Requis pour cette étape :</strong> {requiredObjects.join(', ')}
        </div>
      )}

      <div className="camera-panel__controls">
        {sessionState === "paused" ? (
          <button className="btn btn--primary" onClick={onResume}>
            Reprendre
          </button>
        ) : (
          <button className="btn btn--ghost" onClick={onPause}>
            Mettre en pause
          </button>
        )}
        <button className="btn btn--danger-ghost" onClick={onDisable}>
          Désactiver la caméra
        </button>
      </div>
    </div>
  );
}
