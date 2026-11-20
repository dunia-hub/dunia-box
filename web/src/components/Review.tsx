import { useState } from "react";
import { ApiError, renderPdf, renderWhatsapp, validateDocument } from "../api";
import { strings } from "../i18n";
import type { Json, JsonObject, Language } from "../types";

const COMPUTED = new Set(["amount", "subtotal", "tax", "total", "balance"]);
const HIDDEN = new Set(["type", "language"]);
const DATE_KEYS = new Set(["issue_date", "due_date", "valid_until", "paid_on", "handover_date", "next_meeting", "due"]);
const NUMBER_KEYS = new Set(["quantity", "unit_price", "price", "deposit", "tax_rate"]);
const LONG_TEXT = new Set(["body", "notes", "payment_terms"]);

const TEMPLATES: Record<string, JsonObject> = {
  items: { description: "", quantity: "1", unit: null, unit_price: "" },
  discussion: { topic: "", notes: "" },
  action_items: { task: "", owner: null, due: null },
  witnesses: { name: "" },
};

const LABELS: Record<Language, Record<string, string>> = {
  en: {
    tax_rate: "Tax rate (0.16 = 16%)", wallet: "Solana wallet", unit_price: "Unit price",
    issue_date: "Date", cc: "Cc", item_details: "Item details", action_items: "Action items",
  },
  sw: {
    issuer: "Mtoaji", client: "Mteja", payer: "Aliyelipa", sender: "Mtumaji", recipient: "Mpokeaji",
    seller: "Muuzaji", buyer: "Mnunuzi", name: "Jina", phone: "Simu", email: "Barua pepe",
    address: "Anwani", wallet: "Wallet ya Solana", items: "Bidhaa", description: "Maelezo",
    quantity: "Idadi", unit: "Kipimo", unit_price: "Bei kwa kimoja", issue_date: "Tarehe",
    due_date: "Tarehe ya kulipa", valid_until: "Halali hadi", paid_on: "Ililipwa tarehe",
    reference: "Nambari", currency: "Sarafu", tax_rate: "Kiwango cha kodi (0.16 = 16%)",
    notes: "Maelezo ya ziada", payment_method: "Njia ya malipo", payment_reference: "Nambari ya malipo",
    to: "Kwa", cc: "Nakala", subject: "Kuhusu", body: "Ujumbe", salutation: "Salamu",
    closing: "Hitimisho", title: "Kichwa", location: "Mahali", chair: "Mwenyekiti",
    attendees: "Waliohudhuria", apologies: "Udhuru", agenda: "Ajenda", discussion: "Majadiliano",
    topic: "Mada", decisions: "Maamuzi", action_items: "Hatua za kuchukua", task: "Kazi",
    owner: "Mhusika", due: "Tarehe", next_meeting: "Mkutano ujao", item: "Bidhaa",
    item_details: "Maelezo ya bidhaa", price: "Bei", deposit: "Malipo ya awali",
    payment_terms: "Masharti ya malipo", handover_date: "Tarehe ya kukabidhi",
    conditions: "Masharti", witnesses: "Mashahidi",
  },
};

function fieldLabel(key: string, lang: Language): string {
  return LABELS[lang][key] ?? key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

function setAt(obj: Json, path: (string | number)[], value: Json): Json {
  if (path.length === 0) return value;
  const [head, ...rest] = path;
  if (Array.isArray(obj)) {
    const copy = [...obj];
    copy[head as number] = setAt(copy[head as number] ?? null, rest, value);
    return copy;
  }
  const base = (obj && typeof obj === "object" ? obj : {}) as JsonObject;
  return { ...base, [head]: setAt(base[head as string] ?? null, rest, value) };
}

function clean(value: Json): Json {
  if (typeof value === "string") return value.trim() === "" ? null : value.trim();
  if (Array.isArray(value)) return value.map(clean).filter((v) => v !== null);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, clean(v)]));
  }
  return value;
}

function isStringList(key: string, value: Json[]): boolean {
  return !(key in TEMPLATES) && value.every((v) => typeof v === "string");
}

interface EditorProps {
  value: JsonObject;
  path: (string | number)[];
  lang: Language;
  removeLabel: string;
  addLabel: string;
  onChange: (path: (string | number)[], value: Json) => void;
}

function ObjectEditor({ value, path, lang, removeLabel, addLabel, onChange }: EditorProps) {
  return (
    <>
      {Object.entries(value)
        .filter(([k]) => !HIDDEN.has(k) && !COMPUTED.has(k))
        .map(([key, v]) => {
          const here = [...path, key];
          const label = fieldLabel(key, lang);

          if (Array.isArray(v) && isStringList(key, v)) {
            return (
              <label key={key}>
                {label}
                <textarea
                  rows={Math.max(2, v.length + 1)}
                  value={(v as string[]).join("\n")}
                  onChange={(e) => onChange(here, e.target.value.split("\n"))}
                />
              </label>
            );
          }

          if (Array.isArray(v)) {
            return (
              <fieldset key={key}>
                <legend>{label}</legend>
                {v.map((entry, i) => (
                  <div className="list-entry" key={i}>
                    <ObjectEditor
                      value={(entry ?? {}) as JsonObject}
                      path={[...here, i]}
                      lang={lang}
                      removeLabel={removeLabel}
                      addLabel={addLabel}
                      onChange={onChange}
                    />
                    <button type="button" className="link" onClick={() => onChange(here, v.filter((_, j) => j !== i))}>
                      {removeLabel}
                    </button>
                  </div>
                ))}
                {key in TEMPLATES && (
                  <button type="button" className="link" onClick={() => onChange(here, [...v, { ...TEMPLATES[key] }])}>
                    + {addLabel}
                  </button>
                )}
              </fieldset>
            );
          }

          if (v && typeof v === "object") {
            return (
              <fieldset key={key}>
                <legend>{label}</legend>
                <ObjectEditor
                  value={v as JsonObject}
                  path={here}
                  lang={lang}
                  removeLabel={removeLabel}
                  addLabel={addLabel}
                  onChange={onChange}
                />
              </fieldset>
            );
          }

          const text = v === null || v === undefined ? "" : String(v);
          if (LONG_TEXT.has(key)) {
            return (
              <label key={key}>
                {label}
                <textarea rows={4} value={text} onChange={(e) => onChange(here, e.target.value)} />
              </label>
            );
          }
          return (
            <label key={key}>
              {label}
              <input
                type={DATE_KEYS.has(key) ? "date" : "text"}
                inputMode={NUMBER_KEYS.has(key) ? "decimal" : undefined}
                value={text}
                onChange={(e) => onChange(here, e.target.value)}
              />
            </label>
          );
        })}
    </>
  );
}

interface Props {
  language: Language;
  document: JsonObject;
  onNew: () => void;
}

export default function Review({ language, document, onNew }: Props) {
  const s = strings(language);
  const [doc, setDoc] = useState<JsonObject>(document);
  const [draft, setDraft] = useState<JsonObject>(document);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [docId, setDocId] = useState<string | null>(null);

  const onChange = (path: (string | number)[], value: Json) => {
    setDraft((d) => setAt(d, path, value) as JsonObject);
  };

  const run = async (task: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await task();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const validated = async (): Promise<JsonObject> => {
    const result = await validateDocument(clean(draft) as JsonObject);
    setDoc(result);
    setDraft(result);
    return result;
  };

  const onUpdate = () => run(async () => void (await validated()));

  const onPdf = () =>
    run(async () => {
      const { blob, documentId, filename } = await renderPdf(await validated());
      setDocId(documentId);
      const url = URL.createObjectURL(blob);
      const a = window.document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    });

  const onWhatsapp = () =>
    run(async () => {
      const { document_id, text } = await renderWhatsapp(await validated());
      setDocId(document_id);
      window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener");
    });

  const onCopy = () =>
    run(async () => {
      const { document_id, text } = await renderWhatsapp(await validated());
      setDocId(document_id);
      await navigator.clipboard.writeText(text);
      setNotice(s.copied);
    });

  const currency = typeof doc.currency === "string" ? doc.currency : "KES";
  const headline = (doc.total ?? doc.balance ?? null) as string | null;

  return (
    <div className="review">
      <div className="card summary">
        <div className="summary-type">{String(doc.type).replace(/_/g, " ")}</div>
        {headline && (
          <div className="summary-total">
            {currency} {Number(headline).toLocaleString("en-KE", { minimumFractionDigits: 2 })}
          </div>
        )}
        {docId && (
          <div className="muted small">
            {s.documentId}: {docId.slice(0, 12)}
          </div>
        )}
      </div>

      <div className="actions">
        <button className="primary" onClick={onPdf} disabled={busy}>{s.downloadPdf}</button>
        <button className="whatsapp" onClick={onWhatsapp} disabled={busy}>{s.shareWhatsapp}</button>
        <button onClick={onCopy} disabled={busy}>{s.copyText}</button>
      </div>

      {error && <div className="error">{error}</div>}
      {notice && <div className="notice">{notice}</div>}

      <form className="card editor" onSubmit={(e) => { e.preventDefault(); onUpdate(); }}>
        <h2>{s.review}</h2>
        <ObjectEditor
          value={draft}
          path={[]}
          lang={language}
          removeLabel={s.remove}
          addLabel={s.addItem}
          onChange={onChange}
        />
        <button type="submit" disabled={busy}>{s.update}</button>
      </form>

      <button className="link new" onClick={onNew}>{s.newDocument}</button>
    </div>
  );
}
