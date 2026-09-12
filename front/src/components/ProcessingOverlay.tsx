import { useEffect, useState } from "react";

// The backend call is a single blocking request with no progress events.
// These labels/weights are cosmetic — modeled on the pipeline's own stages
// (download, transcribe, frame extraction, frame analysis, recipe extraction)
// and their *typical* relative durations, so the loader still feels honest.
// Frame analysis dominates (it can run up to 30 min), so it gets by far the
// largest share of the simulated bar. None of this is a truth claim about
// backend state — it's purely a perceived-progress animation.
const STAGES: { label: string; weightSeconds: number }[] = [
  { label: "Récupération de la vidéo…", weightSeconds: 25 },
  { label: "Écoute de la recette…", weightSeconds: 40 },
  { label: "Analyse des images de la vidéo…", weightSeconds: 240 },
  { label: "Rédaction de la recette…", weightSeconds: 30 },
];

const TOTAL_WEIGHT = STAGES.reduce((sum, s) => sum + s.weightSeconds, 0);

interface ProcessingOverlayProps {
  /** True while the request is in flight; flip to false once resolved (success or error handled by parent). */
  isRunning: boolean;
}

export function ProcessingOverlay({ isRunning }: ProcessingOverlayProps) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    if (!isRunning) return;
    setElapsedSeconds(0);
    const interval = window.setInterval(() => setElapsedSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(interval);
  }, [isRunning]);

  // Figure out which cosmetic stage we're "in" based on elapsed time, capping
  // at the last stage so a slower-than-usual run doesn't look stuck at 100%.
  let cumulative = 0;
  let activeIndex = STAGES.length - 1;
  for (let i = 0; i < STAGES.length; i++) {
    cumulative += STAGES[i].weightSeconds;
    if (elapsedSeconds < cumulative) {
      activeIndex = i;
      break;
    }
  }
  const progressRatio = Math.min(elapsedSeconds / TOTAL_WEIGHT, 0.96);

  const minutes = Math.floor(elapsedSeconds / 60);
  const seconds = elapsedSeconds % 60;
  const elapsedLabel = `${minutes}:${seconds.toString().padStart(2, "0")}`;

  return (
    <div className="processing">
      <div className="processing__ring" aria-hidden />
      <p className="processing__label">{STAGES[activeIndex].label}</p>

      <div className="processing__bar-track" role="progressbar" aria-valuenow={Math.round(progressRatio * 100)}>
        <div className="processing__bar-fill" style={{ width: `${progressRatio * 100}%` }} />
      </div>

      <ol className="processing__stages">
        {STAGES.map((stage, i) => (
          <li
            key={stage.label}
            className={
              i < activeIndex
                ? "processing__stage processing__stage--done"
                : i === activeIndex
                ? "processing__stage processing__stage--active"
                : "processing__stage"
            }
          >
            {stage.label}
          </li>
        ))}
      </ol>

      <p className="processing__elapsed">
        {elapsedLabel} — ça peut prendre plusieurs minutes selon la longueur de la vidéo.
      </p>
    </div>
  );
}
