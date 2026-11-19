import json
import logging
from datetime import date, timedelta

import httpx
from pydantic import ValidationError

from .config import settings
from .documents import DOCUMENT_TYPES, Party

logger = logging.getLogger("dunia-box")

LANGUAGE_NAMES = {"sw": "Swahili", "en": "English"}

SWAHILI_WEEKDAYS = [
    "Jumatatu", "Jumanne", "Jumatano", "Alhamisi", "Ijumaa", "Jumamosi", "Jumapili",
]

TYPE_HINTS = {
    "invoice": "a bill asking a client to pay for goods or services",
    "receipt": "proof that a payment was received",
    "quotation": "a price estimate given before work or a sale",
    "memo": "a short internal note to people in an organisation",
    "letter": "a formal letter to a person or office",
    "minutes": "a record of what happened in a meeting",
    "sale_agreement": "an agreement where a seller sells an item to a buyer",
}

# Which field the speaker fills for each document type.
SPEAKER_FIELD = {
    "invoice": "issuer",
    "receipt": "issuer",
    "quotation": "issuer",
    "letter": "sender",
    "sale_agreement": "seller",
}

RULES = """Rules:
- Use only information in the transcript and the speaker profile. Never invent names, amounts, dates, phone numbers, addresses or payment methods. If something is not said, leave it out.
- Swahili numbers: mia = 100, elfu = 1,000, laki = 100,000, milioni = 1,000,000. "elfu tano" = 5000, "elfu mbili mia tano" = 2500, "laki moja" = 100000. Write all amounts as plain numbers without commas.
- "bob", "shilingi", "ksh" and "shillings" mean currency KES.
- "three days of plumbing, 5000 per day" means one item: quantity 3, unit "day", unit_price 5000.
- If the speaker does not say what an item is, leave out its description. Never use an amount or a currency as a description.
- Do not calculate totals, subtotals, tax amounts or balances. Code does that.
- Dates use YYYY-MM-DD. Today is {today}. Never calculate dates yourself. For weekday names and words like kesho or tomorrow, copy the date from this calendar:
{calendar}
- The speaker is the person in the speaker profile. Do not put the speaker as the client, payer, recipient or buyer unless the transcript says so.
- Write all free text (item descriptions, subject, body, notes, conditions) in {language_name}, translating where needed. For example, in Swahili "plumbing" becomes "Kazi ya mabomba".
- Keep people and business names as spoken, with normal capitalisation (for example "Otieno Hardware").
- Return one JSON object matching the schema. Include "type". No extra keys."""


class ExtractionError(Exception):
    pass


def upcoming_calendar(today: date, days: int = 14) -> str:
    lines = []
    for offset in range(days + 1):
        d = today + timedelta(days=offset)
        label = f"{d.isoformat()} {d.strftime('%A')} ({SWAHILI_WEEKDAYS[d.weekday()]})"
        if offset == 0:
            label += " today / leo"
        elif offset == 1:
            label += " tomorrow / kesho"
        elif offset == 2:
            label += " day after tomorrow / kesho kutwa"
        lines.append(f"  {label}")
    return "\n".join(lines)


def call_llm(messages: list[dict]) -> dict:
    if not settings.llm_api_key:
        raise ExtractionError("LLM_API_KEY is not set")

    res = httpx.post(
        f"{settings.llm_base_url}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json={
            "model": settings.llm_model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    if res.status_code != 200:
        raise ExtractionError(f"LLM error {res.status_code}: {res.text[:300]}")

    content = res.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ExtractionError("Model did not return valid JSON") from exc


def classify(transcript: str) -> str:
    options = "\n".join(f'- "{name}": {hint}' for name, hint in TYPE_HINTS.items())
    data = call_llm([
        {
            "role": "system",
            "content": (
                "You decide which document a person is asking for. "
                f"Choose exactly one type:\n{options}\n"
                'Reply with JSON: {"type": "<one of the types>"}'
            ),
        },
        {"role": "user", "content": transcript},
    ])
    doc_type = data.get("type")
    if doc_type not in DOCUMENT_TYPES:
        raise ExtractionError(f"Could not tell which document this is: {doc_type!r}")
    return doc_type


def _drop_nulls(value):
    if isinstance(value, dict):
        return {k: _drop_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_drop_nulls(v) for v in value if v is not None]
    return value


def _prepare(data: dict, doc_type: str, language: str, today: date, profile: Party | None) -> dict:
    data = _drop_nulls(data if isinstance(data, dict) else {})
    data["type"] = doc_type
    data["language"] = language
    data.setdefault("issue_date", today.isoformat())

    if profile is not None:
        speaker = profile.model_dump(exclude_none=True)
        if doc_type in SPEAKER_FIELD:
            data.setdefault(SPEAKER_FIELD[doc_type], speaker)
        elif doc_type == "memo":
            data.setdefault("sender", profile.name)
    return data


def _validate(doc_type: str, data: dict) -> dict:
    model = DOCUMENT_TYPES[doc_type]
    try:
        doc = model.model_validate(data)
    except ValidationError as err:
        missing, errors = [], []
        for e in err.errors():
            field = ".".join(str(p) for p in e["loc"]) or "document"
            if e["type"] == "missing":
                missing.append(field)
            else:
                errors.append({"field": field, "message": e["msg"]})
        return {
            "complete": False,
            "document": None,
            "draft": data,
            "missing_fields": missing,
            "errors": errors,
        }
    return {
        "complete": True,
        "document": doc.model_dump(mode="json"),
        "draft": data,
        "missing_fields": [],
        "errors": [],
    }


def extract_document(
    transcript: str,
    language: str = "en",
    document_type: str | None = None,
    profile: Party | None = None,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    doc_type = document_type or classify(transcript)
    schema = DOCUMENT_TYPES[doc_type].model_json_schema()

    rules = RULES.format(
        today=today.isoformat(),
        calendar=upcoming_calendar(today),
        language_name=LANGUAGE_NAMES[language],
    )
    profile_text = (
        json.dumps(profile.model_dump(exclude_none=True), ensure_ascii=False)
        if profile else "unknown"
    )

    messages = [
        {
            "role": "system",
            "content": (
                f"You turn spoken requests in Swahili, English or a mix into a {doc_type} "
                f"document.\n\n{rules}\n\nJSON schema:\n{json.dumps(schema)}"
            ),
        },
        {
            "role": "user",
            "content": f"Speaker profile: {profile_text}\n\nTranscript:\n{transcript}",
        },
    ]

    raw = call_llm(messages)
    result = _validate(doc_type, _prepare(raw, doc_type, language, today, profile))

    # One retry when the model produced wrong values (not just missing ones).
    if result["errors"]:
        logger.info("Retrying extraction with validation errors: %s", result["errors"])
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
        result = _validate(doc_type, _prepare(raw, doc_type, language, today, profile))

    return {"document_type": doc_type, "transcript": transcript, **result}
