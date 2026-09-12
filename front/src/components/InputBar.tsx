import { useMemo, useState } from "react";
import { useAudioRecorder } from "../hooks/useAudioRecorder";
import { validateInstagramUrl } from "../api/client";

interface InputBarProps {
  onSubmitUrl: (url: string) => void;
  onSubmitAudio: (blob: Blob) => void;
  disabled?: boolean;
}

export function InputBar({ onSubmitUrl, onSubmitAudio, disabled }: InputBarProps) {
  const [url, setUrl] = useState("");
  const [touched, setTouched] = useState(false);
  const recorder = useAudioRecorder();

  const validation = useMemo(() => (url.trim() ? validateInstagramUrl(url) : null), [url]);
  const showError = touched && url.trim().length > 0 && validation && !validation.valid;

  const handleSubmitUrl = () => {
    setTouched(true);
    if (!validation?.valid) return;
    onSubmitUrl(url.trim());
  };

  const handleMicClick = () => {
    if (recorder.state === "idle") recorder.start();
    else if (recorder.state === "recording") recorder.stop();
  };

  return (
    <div className="input-bar">
      {recorder.state === "reviewing" && recorder.audioBlob ? (
        <div className="voice-review">
          <span className="voice-review__label">Note vocale enregistrée</span>
          <div className="voice-review__actions">
            <button className="btn btn--ghost" onClick={recorder.discard}>
              Supprimer
            </button>
            <button
              className="btn btn--primary"
              onClick={() => onSubmitAudio(recorder.audioBlob!)}
              disabled={disabled}
            >
              Envoyer
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="input-bar__row">
            <input
              className="input-bar__field"
              type="text"
              placeholder="Colle le lien du reel Instagram…"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onBlur={() => setTouched(true)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmitUrl()}
              disabled={disabled || recorder.state === "recording"}
            />
            {url.trim() ? (
              <button className="btn btn--primary" onClick={handleSubmitUrl} disabled={disabled}>
                Générer
              </button>
            ) : (
              <button
                className={`mic-btn ${recorder.state === "recording" ? "mic-btn--active" : ""}`}
                onClick={handleMicClick}
                disabled={disabled}
                aria-label={recorder.state === "recording" ? "Arrêter l'enregistrement" : "Parler"}
              >
                <MicIcon />
                {recorder.state === "recording" && <span className="mic-btn__pulse" />}
              </button>
            )}
          </div>
          {showError && <p className="input-bar__error">{validation!.error}</p>}
        </>
      )}
    </div>
  );
}

function MicIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path
        d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Z"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path
        d="M19 11a7 7 0 0 1-14 0M12 18v3"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}
