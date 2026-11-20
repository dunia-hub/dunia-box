import type { AgentState, JsonObject, Party, TurnResponse } from "./types";

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function errorFrom(res: Response): Promise<ApiError> {
  let message = `Request failed (${res.status})`;
  try {
    const body = await res.json();
    if (typeof body.detail === "string") {
      message = body.detail;
    } else if (Array.isArray(body.detail)) {
      message = body.detail
        .map((d: { loc?: (string | number)[]; msg?: string }) =>
          `${(d.loc ?? []).filter((p) => p !== "body").join(".")}: ${d.msg ?? ""}`,
        )
        .join("; ");
    }
  } catch {
    // keep default message
  }
  return new ApiError(res.status, message);
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await errorFrom(res);
  return res.json() as Promise<T>;
}

export function textTurn(utterance: string, state: AgentState, profile: Party | null): Promise<TurnResponse> {
  return postJson<TurnResponse>("/agent/turn", { utterance, state, profile, speak: true });
}

export async function voiceTurn(
  audio: Blob,
  filename: string,
  state: AgentState,
  profile: Party | null,
): Promise<TurnResponse> {
  const form = new FormData();
  form.append("file", audio, filename);
  form.append("state", JSON.stringify(state));
  form.append("profile", profile ? JSON.stringify(profile) : "");
  form.append("speak", "true");

  const res = await fetch(`${BASE}/agent/voice-turn`, { method: "POST", body: form });
  if (!res.ok) throw await errorFrom(res);
  return res.json() as Promise<TurnResponse>;
}

export function validateDocument(doc: JsonObject): Promise<JsonObject> {
  return postJson<JsonObject>("/documents/validate", doc);
}

export async function renderPdf(doc: JsonObject): Promise<{ blob: Blob; documentId: string; filename: string }> {
  const res = await fetch(`${BASE}/render/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(doc),
  });
  if (!res.ok) throw await errorFrom(res);

  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="([^"]+)"/);
  return {
    blob: await res.blob(),
    documentId: res.headers.get("X-Document-Id") ?? "",
    filename: match?.[1] ?? "document.pdf",
  };
}

export function renderWhatsapp(doc: JsonObject): Promise<{ document_id: string; text: string }> {
  return postJson("/render/whatsapp", doc);
}

export function playBase64Mp3(audio: string | null): void {
  if (!audio) return;
  const player = new Audio(`data:audio/mpeg;base64,${audio}`);
  player.play().catch(() => {
    // autoplay can be blocked; the text reply is still shown
  });
}
