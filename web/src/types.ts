export type Language = "sw" | "en";

export type DocumentType =
  | "invoice"
  | "receipt"
  | "quotation"
  | "memo"
  | "letter"
  | "minutes"
  | "sale_agreement";

export interface Party {
  name: string;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  wallet?: string | null;
}

export type Json = string | number | boolean | null | Json[] | { [key: string]: Json };
export type JsonObject = { [key: string]: Json };

export interface AgentState {
  language: Language;
  document_type: DocumentType | null;
  draft: JsonObject;
  missing_fields: string[];
  asked_optional: string[];
  pending_optional: string[];
  awaiting_confirmation: boolean;
  last_question: string | null;
  turns: number;
}

export interface FieldError {
  field: string;
  message: string;
}

export interface TurnResponse {
  state: AgentState;
  reply_text: string;
  reply_audio: string | null;
  complete: boolean;
  document: JsonObject | null;
  preview: JsonObject | null;
  document_id: string | null;
  whatsapp_text: string | null;
  errors: FieldError[];
  transcript?: string;
}

export interface ChatMessage {
  role: "user" | "agent";
  text: string;
}

export function emptyState(language: Language): AgentState {
  return {
    language,
    document_type: null,
    draft: {},
    missing_fields: [],
    asked_optional: [],
    pending_optional: [],
    awaiting_confirmation: false,
    last_question: null,
    turns: 0,
  };
}
