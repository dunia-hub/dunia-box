import { useEffect, useRef, useState } from "react";
import { ApiError, playBase64Mp3, textTurn, voiceTurn } from "../api";
import { QUICK_WORDS, strings } from "../i18n";
import { emptyState } from "../types";
import type { AgentState, ChatMessage, JsonObject, Language, Party, TurnResponse } from "../types";
import { useRecorder } from "../useRecorder";

interface Props {
  language: Language;
  profile: Party | null;
  onComplete: (document: JsonObject) => void;
}

function previewAmount(doc: JsonObject): string | null {
  const value = doc.total ?? doc.balance ?? doc.price ?? null;
  if (value === null || value === undefined) return null;
  const currency = typeof doc.currency === "string" ? doc.currency : "KES";
  return `${currency} ${Number(value).toLocaleString("en-KE", { minimumFractionDigits: 2 })}`;
}

export default function Conversation({ language, profile, onComplete }: Props) {
  const s = strings(language);
  const quick = QUICK_WORDS[language];
  const [state, setState] = useState<AgentState>(() => emptyState(language));
  const [messages, setMessages] = useState<ChatMessage[]>([{ role: "agent", text: s.greeting }]);
  const [preview, setPreview] = useState<JsonObject | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const { recording, error: micError, start, stop } = useRecorder();
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy, preview]);

  const handle = (res: TurnResponse, userText?: string) => {
    setState(res.state);
    setPreview(res.preview);
    setMessages((m) => [
      ...m,
      ...(userText ? [{ role: "user" as const, text: userText }] : []),
      { role: "agent" as const, text: res.reply_text },
    ]);
    playBase64Mp3(res.reply_audio);
    if (res.complete && res.document) onComplete(res.document);
  };

  const run = async (task: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await task();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const sendText = (utterance: string) =>
    run(async () => handle(await textTurn(utterance, state, profile), utterance));

  const onMic = async () => {
    if (busy) return;
    if (!recording) {
      await start();
      return;
    }
    const rec = await stop();
    if (!rec) return;
    await run(async () => {
      const res = await voiceTurn(rec.blob, rec.filename, state, profile);
      handle(res, res.transcript);
    });
  };

  const onSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const utterance = text.trim();
    if (!utterance || busy) return;
    setText("");
    await sendText(utterance);
  };

  const amount = preview ? previewAmount(preview) : null;

  return (
    <div className="conversation">
      <div className="messages">
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.text}
          </div>
        ))}

        {preview && state.awaiting_confirmation && (
          <div className="card preview">
            <div className="summary-type">
              {s.preview}: {String(preview.type).replace(/_/g, " ")}
            </div>
            {amount && <div className="summary-total">{amount}</div>}
          </div>
        )}

        {busy && <div className="bubble agent thinking">{s.thinking}</div>}
        <div ref={bottom} />
      </div>

      {state.missing_fields.length > 0 && (
        <div className="missing">
          <span className="muted">{s.stillNeeded}:</span>
          {state.missing_fields.map((f) => (
            <span key={f} className="chip">
              {f.replace(/\.\d+\./g, ".").replace(/_/g, " ")}
            </span>
          ))}
        </div>
      )}

      {(error || micError) && <div className="error">{error ?? s.micError}</div>}

      {!busy && !recording && state.awaiting_confirmation && (
        <div className="quick">
          <button className="primary" onClick={() => sendText(quick.yes)}>{s.yes}</button>
          <button onClick={() => sendText(quick.change)}>{s.change}</button>
        </div>
      )}
      {!busy && !recording && state.pending_optional.length > 0 && !state.awaiting_confirmation && (
        <div className="quick">
          <button onClick={() => sendText(quick.skip)}>{s.skip}</button>
        </div>
      )}

      <div className="composer">
        <button
          type="button"
          className={`mic ${recording ? "recording" : ""}`}
          onClick={onMic}
          disabled={busy}
          aria-label={recording ? s.tapToStop : s.tapToSpeak}
        >
          <span className="mic-dot" />
        </button>
        <div className="mic-label">{recording ? s.tapToStop : s.tapToSpeak}</div>

        <form className="type-row" onSubmit={onSend}>
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={s.typeInstead}
            disabled={busy || recording}
          />
          <button type="submit" disabled={busy || recording || !text.trim()}>
            {s.send}
          </button>
        </form>
      </div>
    </div>
  );
}
