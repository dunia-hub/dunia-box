import { useCallback, useRef, useState } from "react";

interface Format {
  mime: string;
  ext: string;
}

const CANDIDATES: Format[] = [
  { mime: "audio/webm;codecs=opus", ext: "webm" },
  { mime: "audio/webm", ext: "webm" },
  { mime: "audio/mp4", ext: "m4a" },
  { mime: "audio/ogg;codecs=opus", ext: "ogg" },
];

function pickFormat(): Format {
  if (typeof MediaRecorder === "undefined") return { mime: "", ext: "webm" };
  return CANDIDATES.find((c) => MediaRecorder.isTypeSupported(c.mime)) ?? { mime: "", ext: "webm" };
}

export interface Recording {
  blob: Blob;
  filename: string;
}

export function useRecorder() {
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const format = useRef<Format>({ mime: "", ext: "webm" });

  const start = useCallback(async () => {
    setError(false);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      format.current = pickFormat();
      const r = new MediaRecorder(stream, format.current.mime ? { mimeType: format.current.mime } : undefined);
      chunks.current = [];
      r.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.current.push(e.data);
      };
      r.start();
      recorder.current = r;
      setRecording(true);
    } catch {
      setError(true);
    }
  }, []);

  const stop = useCallback(
    () =>
      new Promise<Recording | null>((resolve) => {
        const r = recorder.current;
        if (!r) {
          resolve(null);
          return;
        }
        r.onstop = () => {
          r.stream.getTracks().forEach((t) => t.stop());
          const blob = new Blob(chunks.current, { type: r.mimeType || format.current.mime || "audio/webm" });
          recorder.current = null;
          setRecording(false);
          resolve(blob.size > 0 ? { blob, filename: `voice.${format.current.ext}` } : null);
        };
        r.stop();
      }),
    [],
  );

  return { recording, error, start, stop };
}
