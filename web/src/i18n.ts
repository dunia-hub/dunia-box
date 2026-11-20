import type { Language } from "./types";

const en = {
  tagline: "Speak. Get the document.",
  greeting:
    "What document do you need? An invoice, receipt, quotation, memo, letter, meeting minutes or sale agreement.",
  tapToSpeak: "Tap to speak",
  tapToStop: "Tap to stop",
  thinking: "Working on it...",
  typeInstead: "Or type here",
  send: "Send",
  yes: "Yes, create it",
  change: "Change something",
  skip: "Skip",
  newDocument: "New document",
  stillNeeded: "Still needed",
  preview: "Preview",
  review: "Review and edit",
  update: "Update",
  downloadPdf: "Download PDF",
  shareWhatsapp: "Share on WhatsApp",
  copyText: "Copy text",
  copied: "Copied",
  micError: "Microphone not available. Allow mic access, or type instead.",
  addItem: "Add item",
  remove: "Remove",
  documentId: "Document ID",
  forgetMe: "Forget my details",
};

type Strings = typeof en;

const sw: Strings = {
  tagline: "Ongea. Pata hati.",
  greeting:
    "Unahitaji hati gani? Ankara, risiti, nukuu ya bei, memo, barua, kumbukumbu za mkutano au mkataba wa mauzo.",
  tapToSpeak: "Gusa kuongea",
  tapToStop: "Gusa kusimamisha",
  thinking: "Inashughulikiwa...",
  typeInstead: "Au andika hapa",
  send: "Tuma",
  yes: "Ndio, itengeneze",
  change: "Badilisha kitu",
  skip: "Ruka",
  newDocument: "Hati mpya",
  stillNeeded: "Bado inahitajika",
  preview: "Hakiki",
  review: "Kagua na urekebishe",
  update: "Sasisha",
  downloadPdf: "Pakua PDF",
  shareWhatsapp: "Tuma WhatsApp",
  copyText: "Nakili maandishi",
  copied: "Imenakiliwa",
  micError: "Maikrofoni haipatikani. Ruhusu maikrofoni, au andika.",
  addItem: "Ongeza bidhaa",
  remove: "Ondoa",
  documentId: "Kitambulisho cha hati",
  forgetMe: "Sahau maelezo yangu",
};

export function strings(language: Language): Strings {
  return language === "sw" ? sw : en;
}

// Words sent when a quick-reply button is tapped (recognised by the agent).
export const QUICK_WORDS: Record<Language, { yes: string; change: string; skip: string }> = {
  sw: { yes: "Ndio", change: "Hapana", skip: "Ruka" },
  en: { yes: "Yes", change: "No", skip: "Skip" },
};
