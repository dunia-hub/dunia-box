import base64
import json
import logging
from datetime import date
from decimal import Decimal
from typing import Literal

import httpx
from pydantic import BaseModel

from .config import settings
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
from .render import fingerprint, label, whatsapp_text

logger = logging.getLogger("dunia-box")

TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
MAX_QUESTIONS_PER_TURN = 2

DocumentType = Literal[
    "invoice", "receipt", "quotation", "memo", "letter", "minutes", "sale_agreement"
]


class AgentState(BaseModel):
    language: Literal["sw", "en"] = "en"
    document_type: DocumentType | None = None
    draft: dict = {}
    missing_fields: list[str] = []
    last_question: str | None = None
    turns: int = 0


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
}

FALLBACK_QUESTION = {"en": "Please tell me the {field}.", "sw": "Tafadhali niambie {field}."}
RETRY_MESSAGE = {
    "en": "I didn't get {field} right. Can you say it again?",
    "sw": "Sikuelewa {field} vizuri. Tafadhali rudia.",
}

COUNTERPARTY = {
    "invoice": ("client", "name"),
    "quotation": ("client", "name"),
    "receipt": ("payer", "name"),
    "letter": ("recipient", "name"),
    "sale_agreement": ("buyer", "name"),
}


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


def _spoken_amount(value, currency: str) -> str:
    d = Decimal(str(value))
    return f"{currency} {int(d):,}" if d == d.to_integral() else f"{currency} {d:,.2f}"


def completion_message(doc: dict) -> str:
    lang = doc.get("language", "en")
    kind = doc["type"]
    name = label(kind, lang)

    who = ""
    if kind in COUNTERPARTY:
        field, key = COUNTERPARTY[kind]
        who = doc.get(field, {}).get(key, "")
    elif kind == "memo":
        who = ", ".join(doc.get("to", []))
    elif kind == "minutes":
        who = doc.get("title", "")

    amount = ""
    if "total" in doc:
        amount = _spoken_amount(doc["total"], doc.get("currency", "KES"))
    elif "price" in doc:
        amount = _spoken_amount(doc["price"], doc.get("currency", "KES"))

    if lang == "sw":
        msg = f"Tayari. {name} ya {who} iko tayari" if who else f"Tayari. {name} iko tayari"
        return msg + (f", jumla {amount}." if amount else ".")
    msg = f"Done. Your {name.lower()} for {who} is ready" if who else f"Done. Your {name.lower()} is ready"
    return msg + (f", total {amount}." if amount else ".")


def update_document(utterance: str, state: AgentState, profile: Party | None, today: date) -> dict:
    doc_type = state.document_type
    schema = DOCUMENT_TYPES[doc_type].model_json_schema()
    rules = RULES.format(
        today=today.isoformat(),
        calendar=upcoming_calendar(today),
        language_name=LANGUAGE_NAMES[state.language],
    )
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
                f"Still missing: {', '.join(state.missing_fields) or 'nothing'}\n"
                f"Last question asked: {state.last_question or 'none'}\n\n"
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


def run_turn(
    utterance: str,
    state: AgentState,
    profile: Party | None = None,
    today: date | None = None,
    speak: bool = True,
) -> dict:
    today = today or date.today()

    if state.draft and state.document_type:
        result = update_document(utterance, state, profile, today)
    else:
        result = extract_document(utterance, state.language, state.document_type, profile, today)

    lang = state.language
    document, document_id, wa_text = None, None, None

    if result["complete"]:
        document = result["document"]
        document_id = fingerprint(document)
        wa_text = whatsapp_text(document)
        reply = completion_message(document)
        question = None
    elif result["missing_fields"]:
        questions = build_questions(result["missing_fields"], lang)
        reply = " ".join(questions)
        question = reply
    else:
        field = result["errors"][0]["field"] if result["errors"] else "document"
        reply = RETRY_MESSAGE[lang].format(field=_question_key(field).replace("_", " "))
        question = reply

    new_state = AgentState(
        language=lang,
        document_type=result["document_type"],
        draft=result["draft"],
        missing_fields=result["missing_fields"],
        last_question=question,
        turns=state.turns + 1,
    )

    return {
        "state": new_state.model_dump(mode="json"),
        "reply_text": reply,
        "reply_audio": synthesize(reply) if speak else None,
        "complete": result["complete"],
        "document": document,
        "document_id": document_id,
        "whatsapp_text": wa_text,
        "errors": result["errors"],
    }
