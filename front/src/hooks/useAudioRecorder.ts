import { useCallback, useRef, useState } from "react";

export type RecorderState = "idle" | "recording" | "reviewing";

export function useAudioRecorder() {
  const [state, setState] = useState<RecorderState>("idle");
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const start = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;
    chunksRef.current = [];

    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      setAudioBlob(blob);
      setState("reviewing");
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };

    mediaRecorderRef.current = recorder;
    recorder.start();
    setState("recording");
  }, []);

  const stop = useCallback(() => {
    mediaRecorderRef.current?.stop();
  }, []);

  const discard = useCallback(() => {
    setAudioBlob(null);
    setState("idle");
  }, []);

  return { state, audioBlob, start, stop, discard };
}
