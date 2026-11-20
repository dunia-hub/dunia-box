import base64
import json
import logging
import re
from datetime import date
from decimal import Decimal
from typing import Literal

import httpx
from pydantic import BaseModel

from .config import settings
from .dates import parse_spoken_date
from .documents import DOCUMENT_TYPES, Party
from .extract import (
    LANGUAGE_NAMES,
    RULES,
    _prepare,
    _validate,
    call_llm,
    extract_document,
    upcoming_calendar,
)
from .render import fingerprint, fmt_date, label, whatsapp_text

logger = logging.getLogger("dunia-box")

TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
MAX_QUESTIONS_PER_TURN = 1
MAX_ATTEMPTS = 2

DocumentType = Literal[
    "invoice", "receipt", "quotation", "memo", "letter", "minutes", "sale_agreement"
]

DATE_FIELDS = {"due_date", "valid_until", "handover_date", "paid_on", "next_meeting"}


class AgentState(BaseModel):
    language: Literal["sw", "en"] = "en"
    document_type: DocumentType | None = None
    draft: dict = {}
    missing_fields: list[str] = []
    asked_optional: list[str] = []
    pending_optional: list[str] = []
    awaiting_confirmation: bool = False
    asking: str | None = None
    attempts: dict[str, int] = {}
    last_question: str | None = None
    turns: int = 0


# ---------- Questions ----------

QUESTIONS = {
    "issuer": {"en": "What name should the document be issued under?", "sw": "Hati itolewe kwa jina gani?"},
    "client": {"en": "Who is this for?", "sw": "Hii ni ya nani?"},
    "payer": {"en": "Who paid?", "sw": "Nani amelipa?"},
    "items": {"en": "What items or work should I include, and at what price?", "sw": "Niweke bidhaa au kazi gani, na kwa bei gani?"},
    "items.description": {"en": "What is the item or work?", "sw": "Ni bidhaa au kazi gani?"},
    "items.unit_price": {"en": "What is the price?", "sw": "Bei ni ngapi?"},
    "to": {"en": "Who is the memo for?", "sw": "Memo hii ni kwa nani?"},
    "sender": {"en": "Who is it from?", "sw": "Inatoka kwa nani?"},
    "subject": {"en": "What is the subject?", "sw": "Inahusu nini?"},
    "body": {"en": "What should it say?", "sw": "Iseme nini?"},
    "recipient": {"en": "Who is the letter to?", "sw": "Barua ni kwa nani?"},
    "title": {"en": "What was the meeting about?", "sw": "Mkutano ulikuwa wa nini?"},
    "attendees": {"en": "Who attended?", "sw": "Nani walihudhuria?"},
    "seller": {"en": "Who is the seller?", "sw": "Muuzaji ni nani?"},
    "buyer": {"en": "Who is the buyer?", "sw": "Mnunuzi ni nani?"},
    "item": {"en": "What is being sold?", "sw": "Kinachouzwa ni nini?"},
    "price": {"en": "What is the price?", "sw": "Bei ni ngapi?"},
    # Follow-ups
    "due_date": {"en": "What is the due date?", "sw": "Tarehe ya kulipa ni lini?"},
    "issuer.phone": {"en": "What's your phone number? It will appear on the document.", "sw": "Nambari yako ya simu ni ipi? Itaonekana kwenye hati."},
    "valid_until": {"en": "How long is this price valid?", "sw": "Bei hii ni halali hadi lini?"},
    "payment_method": {"en": "How did they pay? M-PESA, cash, bank or USDC?", "sw": "Walilipa vipi? M-PESA, taslimu, benki au USDC?"},
    "payment_reference": {"en": "What's the payment reference, if there is one?", "sw": "Nambari ya malipo ni ipi, kama ipo?"},
    "item_details": {"en": "Any details about the item, like a registration or serial number?", "sw": "Kuna maelezo zaidi ya bidhaa, kama nambari ya usajili?"},
    "payment_terms": {"en": "How will the balance be paid?", "sw": "Salio litalipwa vipi?"},
    "handover_date": {"en": "When will it be handed over?", "sw": "Itakabidhiwa lini?"},
    "decisions": {"en": "What decisions were made?", "sw": "Mlifanya maamuzi gani?"},
    "action_items": {"en": "Any action items? Who will do what?", "sw": "Kuna hatua za kuchukua? Nani atafanya nini?"},
}

# Optional in the schema, but always asked for these types (no skipping).
REQUIRED_FOLLOWUPS = {"invoice": ["due_date"]}

OPTIONAL_FIELDS = {
    "invoice": ["issuer.phone"],
    "quotation": ["valid_until", "issuer.phone"],
    "receipt": ["payment_method", "payment_reference"],
    "sale_agreement": ["item_details", "payment_terms", "handover_date"],
    "minutes": ["decisions", "action_items"],
    "memo": [],
    "letter": [],
}

FALLBACK_QUESTION = {"en": "Please tell me the {field}.", "sw": "Tafadhali niambie {field}."}
RETRY_MESSAGE = {
    "en": "I didn't get {field} right. Can you say it again?",
    "sw": "Sikuelewa {field} vizuri. Tafadhali rudia.",
}
WHAT_TO_CHANGE = {
    "en": "Okay. Tell me what to change.",
    "sw": "Sawa. Niambie unachotaka kubadilisha.",
}

COUNTERPARTY = {
    "invoice": ("client", "name"),
    "quotation": ("client", "name"),
    "receipt": ("payer", "name"),
    "letter": ("recipient", "name"),
    "sale_agreement": ("buyer", "name"),
}

YES_WORDS = {"ndio", "ndiyo", "sawa", "poa", "fiti", "tengeneza", "endelea", "yes", "yeah", "yep", "ok", "okay", "sure", "create", "go"}
NO_WORDS = {"hapana", "sio", "badilisha", "subiri", "no", "nope", "change", "wait"}
SKIP_WORDS = {"hapana", "hakuna", "sina", "sijui", "ruka", "baadaye", "no", "none", "nope", "skip", "later"}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def _short(text: str) -> bool:
    return len(_words(text)) <= 4


def is_yes(text: str) -> bool:
    w = set(_words(text))
    return _short(text) and bool(w & YES_WORDS) and not (w & NO_WORDS)


def is_no(text: str) -> bool:
    w = set(_words(text))
    return _short(text) and bool(w & NO_WORDS) and not (w & YES_WORDS)


def is_skip(text: str) -> bool:
    return _short(text) and bool(set(_words(text)) & SKIP_WORDS)


def _question_key(field: str) -> str:
    parts = [p for p in field.split(".") if not p.isdigit()]
    full = ".".join(parts)
    return full if full in QUESTIONS else parts[0]


def build_questions(missing: list[str], language: str) -> list[str]:
    seen, questions = set(), []
    for field in missing:
        key = _question_key(field)
        if key in seen:
            continue
        seen.add(key)
        template = QUESTIONS.get(key, {}).get(language)
        questions.append(template or FALLBACK_QUESTION[language].format(field=key.replace("_", " ")))
        if len(questions) == MAX_QUESTIONS_PER_TURN:
            break
    return questions


def _get(data: dict, path: str):
    value = data
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _is_empty(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _spoken_amount(value, currency: str) -> str:
    d = Decimal(str(value))
    return f"{currency} {int(d):,}" if d == d.to_integral() else f"{currency} {d:,.2f}"


def _counterparty(doc: dict) -> str:
    kind = doc["type"]
    if kind in COUNTERPARTY:
        field, key = COUNTERPARTY[kind]
        return (doc.get(field) or {}).get(key, "")
    if kind == "memo":
        return ", ".join(doc.get("to", []))
    if kind == "minutes":
        return doc.get("title", "")
    return ""


def _amount(doc: dict) -> str:
    cur = doc.get("currency", "KES")
    if doc.get("total") is not None:
        return _spoken_amount(doc["total"], cur)
    if doc.get("price") is not None:
        return _spoken_amount(doc["price"], cur)
    return ""


def confirmation_message(doc: dict) -> str:
    lang = doc.get("language", "en")
    name = label(doc["type"], lang)
    who, amount = _counterparty(doc), _amount(doc)
    due = fmt_date(doc.get("due_date"), lang) if doc.get("due_date") else ""

    if lang == "sw":
        parts = [f"Nimeandaa {name.lower()}" + (f" ya {who}" if who else "")]
        if amount:
            parts.append(f"jumla {amount}")
        if due:
            parts.append(f"ilipwe {due}")
        return ", ".join(parts) + ". Niitengeneze?"

    parts = [f"I've prepared your {name.lower()}" + (f" for {who}" if who else "")]
    if amount:
        parts.append(f"total {amount}")
    if due:
        parts.append(f"due {due}")
    return ", ".join(parts) + ". Shall I create it?"


def completion_message(doc: dict) -> str:
    lang = doc.get("language", "en")
    name = label(doc["type"], lang)
    who, amount = _counterparty(doc), _amount(doc)

    if lang == "sw":
        msg = f"Tayari. {name} ya {who} iko tayari" if who else f"Tayari. {name} iko tayari"
        return msg + (f", jumla {amount}." if amount else ".")
    msg = f"Done. Your {name.lower()} for {who} is ready" if who else f"Done. Your {name.lower()} is ready"
    return msg + (f", total {amount}." if amount else ".")


# ---------- Model calls ----------

def update_document(utterance: str, state: AgentState, profile: Party | None, today: date) -> dict:
    doc_type = state.document_type
    schema = DOCUMENT_TYPES[doc_type].model_json_schema()
    rules = RULES.format(
        today=today.isoformat(),
        calendar=upcoming_calendar(today),
        language_name=LANGUAGE_NAMES[state.language],
    )
    field_hint = f"The question was about the field: {state.asking}\n" if state.asking else ""
    messages = [
        {
            "role": "system",
            "content": (
                f"You update a {doc_type} draft using the speaker's latest answer.\n\n"
                f"{rules}\n- Keep everything already in the draft unless the speaker changes it.\n\n"
                f"JSON schema:\n{json.dumps(schema)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Current draft:\n{json.dumps(state.draft, ensure_ascii=False)}\n\n"
                f"Last question asked: {state.last_question or 'none'}\n{field_hint}\n"
                f"Speaker's answer:\n{utterance}\n\n"
                "Return the full updated JSON."
            ),
        },
    ]

    raw = call_llm(messages)
    result = _validate(doc_type, _prepare(raw, doc_type, state.language, today, profile))

    if result["errors"]:
        messages += [
            {"role": "assistant", "content": json.dumps(raw, ensure_ascii=False)},
            {
                "role": "user",
                "content": (
                    "Fix these problems and return the full JSON again. "
                    "Leave out anything that was not said.\n"
                    + json.dumps(result["errors"], ensure_ascii=False)
                ),
            },
        ]
        raw = call_llm(messages)
        result = _validate(doc_type, _prepare(raw, doc_type, state.language, today, profile))

    return {"document_type": doc_type, **result}


def synthesize(text: str) -> str | None:
    if not (settings.tts_enabled and settings.elevenlabs_api_key):
        return None
    try:
        res = httpx.post(
            TTS_URL.format(voice_id=settings.tts_voice_id),
            headers={"xi-api-key": settings.elevenlabs_api_key, "Accept": "audio/mpeg"},
            json={"text": text, "model_id": settings.tts_model},
            timeout=60,
        )
        if res.status_code != 200:
            logger.warning("TTS failed %s: %s", res.status_code, res.text[:200])
            return None
        return base64.b64encode(res.content).decode("ascii")
    except httpx.HTTPError:
        logger.exception("TTS request failed")
        return None


# ---------- Turn ----------

def run_turn(
    utterance: str,
    state: AgentState,
    profile: Party | None = None,
    today: date | None = None,
    speak: bool = True,
) -> dict:
    today = today or date.today()
    lang = state.language
    asked = list(state.asked_optional)
    attempts = dict(state.attempts)
    confirmed = False
    has_draft = bool(state.draft and state.document_type)

    def respond(reply: str, result: dict | None, **changes) -> dict:
        doc_type = result["document_type"] if result else state.document_type
        draft = result["draft"] if result else state.draft
        missing = result["missing_fields"] if result else state.missing_fields
        new_state = AgentState(
            language=lang,
            document_type=doc_type,
            draft=draft,
            missing_fields=missing,
            asked_optional=changes.get("asked_optional", asked),
            pending_optional=changes.get("pending_optional", []),
            awaiting_confirmation=changes.get("awaiting_confirmation", False),
            asking=changes.get("asking"),
            attempts=changes.get("attempts", attempts),
            last_question=changes.get("last_question"),
            turns=state.turns + 1,
        )
        complete = changes.get("complete", False)
        document = result["document"] if result and complete else None
        return {
            "state": new_state.model_dump(mode="json"),
            "reply_text": reply,
            "reply_audio": synthesize(reply) if speak else None,
            "complete": complete,
            "document": document,
            "preview": result["document"] if result and not complete else None,
            "document_id": fingerprint(document) if document else None,
            "whatsapp_text": whatsapp_text(document) if document else None,
            "errors": result["errors"] if result else [],
        }

    def ask(field: str, result: dict, **changes) -> dict:
        reply = QUESTIONS.get(field, {}).get(lang) or build_questions([field], lang)[0]
        tries = {**attempts, field: attempts.get(field, 0) + 1}
        return respond(reply, result, asking=field, attempts=tries, last_question=reply, **changes)

    parsed_date = (
        parse_spoken_date(utterance, today)
        if has_draft and state.asking in DATE_FIELDS
        else None
    )

    # 1. Work out the new draft for this turn.
    if has_draft and state.awaiting_confirmation and is_yes(utterance):
        result = {"document_type": state.document_type, **_validate(state.document_type, state.draft)}
        confirmed = result["complete"]
    elif has_draft and state.awaiting_confirmation and is_no(utterance):
        return respond(WHAT_TO_CHANGE[lang], None, last_question=WHAT_TO_CHANGE[lang])
    elif parsed_date is not None:
        draft = {**state.draft, state.asking: parsed_date.isoformat()}
        result = {"document_type": state.document_type, **_validate(state.document_type, draft)}
    elif has_draft and state.pending_optional and is_skip(utterance):
        result = {"document_type": state.document_type, **_validate(state.document_type, state.draft)}
    elif has_draft:
        result = update_document(utterance, state, profile, today)
    else:
        result = extract_document(utterance, lang, state.document_type, profile, today)

    # 2. Required fields missing: ask for the first one.
    if result["missing_fields"]:
        field = _question_key(result["missing_fields"][0])
        return ask(field, result)

    # 3. Values that failed validation: ask again.
    if result["errors"]:
        field = _question_key(result["errors"][0]["field"])
        reply = RETRY_MESSAGE[lang].format(field=field.replace("_", " "))
        return respond(reply, result, asking=field, last_question=reply)

    doc = result["document"]

    # 4. Confirmed: finish.
    if confirmed:
        return respond(completion_message(doc), result, complete=True)

    # 5. Details that must be asked, up to MAX_ATTEMPTS each so it never loops.
    needed = [
        f for f in REQUIRED_FOLLOWUPS.get(doc["type"], [])
        if _is_empty(_get(doc, f)) and attempts.get(f, 0) < MAX_ATTEMPTS
    ]
    if needed:
        return ask(needed[0], result)

    # 6. Useful details not given yet: ask once, can be skipped.
    todo = [
        f for f in OPTIONAL_FIELDS.get(doc["type"], [])
        if f not in asked and _is_empty(_get(doc, f))
    ]
    if todo:
        field = todo[0]
        return ask(field, result, asked_optional=asked + [field], pending_optional=[field])

    # 7. Everything in place: confirm before creating.
    reply = confirmation_message(doc)
    return respond(reply, result, awaiting_confirmation=True, last_question=reply)
