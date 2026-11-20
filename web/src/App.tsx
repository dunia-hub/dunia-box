import { useState } from "react";
import Conversation from "./components/Conversation";
import Review from "./components/Review";
import { strings } from "./i18n";
import { loadJson, saveJson } from "./storage";
import type { Json, JsonObject, Language, Party } from "./types";

type View = "talk" | "review";

const SPEAKER_FIELDS = ["issuer", "sender", "seller"];

function speakerFrom(doc: JsonObject): Party | null {
  for (const field of SPEAKER_FIELDS) {
    const value: Json | undefined = doc[field];
    if (typeof value === "string" && value.trim()) return { name: value.trim() };
    if (value && typeof value === "object" && !Array.isArray(value) && typeof value.name === "string") {
      const p = value as Record<string, Json>;
      const str = (k: string) => (typeof p[k] === "string" ? (p[k] as string) : null);
      return { name: p.name as string, phone: str("phone"), email: str("email"), address: str("address"), wallet: str("wallet") };
    }
  }
  return null;
}

function mergeProfile(current: Party | null, found: Party): Party {
  if (!current || current.name !== found.name) return found;
  return {
    name: found.name,
    phone: found.phone ?? current.phone ?? null,
    email: found.email ?? current.email ?? null,
    address: found.address ?? current.address ?? null,
    wallet: found.wallet ?? current.wallet ?? null,
  };
}

export default function App() {
  const [language, setLanguage] = useState<Language>(() => loadJson<Language>("dunia.language", "sw"));
  const [profile, setProfile] = useState<Party | null>(() => loadJson<Party | null>("dunia.profile", null));
  const [view, setView] = useState<View>("talk");
  const [document, setDocument] = useState<JsonObject | null>(null);
  const [session, setSession] = useState(0);
  const s = strings(language);

  const changeLanguage = (lang: Language) => {
    setLanguage(lang);
    saveJson("dunia.language", lang);
    if (view === "talk") setSession((n) => n + 1);
  };

  const onComplete = (doc: JsonObject) => {
    const found = speakerFrom(doc);
    if (found) {
      const next = mergeProfile(profile, found);
      setProfile(next);
      saveJson("dunia.profile", next);
    }
    setDocument(doc);
    setView("review");
  };

  const forgetMe = () => {
    setProfile(null);
    saveJson("dunia.profile", null);
    setSession((n) => n + 1);
  };

  const startNew = () => {
    setDocument(null);
    setSession((n) => n + 1);
    setView("talk");
  };

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <div className="brand">Dunia Box</div>
          <div className="tagline">{profile ? profile.name : s.tagline}</div>
        </div>
        <div className="topbar-actions">
          <div className="lang-toggle" role="group" aria-label="Language">
            <button className={language === "sw" ? "active" : ""} onClick={() => changeLanguage("sw")}>SW</button>
            <button className={language === "en" ? "active" : ""} onClick={() => changeLanguage("en")}>EN</button>
          </div>
          {profile && (
            <button className="link small" onClick={forgetMe}>{s.forgetMe}</button>
          )}
        </div>
      </header>

      <main>
        {view === "talk" && (
          <Conversation
            key={`${session}-${language}`}
            language={language}
            profile={profile}
            onComplete={onComplete}
          />
        )}

        {view === "review" && document && (
          <Review key={session} language={language} document={document} onNew={startNew} />
        )}
      </main>
    </div>
  );
}
