import logging
import os
from functools import lru_cache

import av
import httpx
from faster_whisper import WhisperModel

from .config import settings

logger = logging.getLogger("dunia-box")

SUPPORTED_LANGUAGES = {"sw", "en", "auto"}

# Nudges Whisper toward Kenyan Swahili/English code-switching.
MIXED_PROMPT = (
    "Mazungumzo haya ni kwa Kiswahili na English, "
    "wakati mwingine yamechanganywa."
)

SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"
ISO3_TO_ISO1 = {"swa": "sw", "swh": "sw", "eng": "en"}


class AudioTooLong(Exception):
    pass


class TranscriptionError(Exception):
    pass


def probe_duration(path: str) -> float:
    with av.open(path) as container:
        if container.duration is None:
            return 0.0
        return container.duration / av.time_base


@lru_cache(maxsize=1)
def get_model() -> WhisperModel:
    return WhisperModel(
        settings.model_name,
        device=settings.device,
        compute_type=settings.compute_type,
    )


def transcribe_whisper(path: str, language: str, duration: float | None = None) -> dict:
    model = get_model()
    is_auto = language == "auto"

    segments, info = model.transcribe(
        path,
        language=None if is_auto else language,
        multilingual=is_auto,
        initial_prompt=None if language == "en" else MIXED_PROMPT,
        vad_filter=True,
        beam_size=5,
    )

    out = [
        {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
        for s in segments
    ]

    return {
        "text": " ".join(seg["text"] for seg in out).strip(),
        "provider": "whisper",
        "requested_language": language,
        "detected_language": info.language,
        "language_probability": round(info.language_probability, 3),
        "duration_sec": round(duration if duration is not None else info.duration, 2),
        "segments": out,
    }


def transcribe_scribe(path: str, language: str, duration: float) -> dict:
    if not settings.elevenlabs_api_key:
        raise TranscriptionError("ELEVENLABS_API_KEY is not set")

    data = {"model_id": settings.scribe_model}
    if language != "auto":
        data["language_code"] = language

    with open(path, "rb") as f:
        res = httpx.post(
            SCRIBE_URL,
            headers={"xi-api-key": settings.elevenlabs_api_key},
            data=data,
            files={"file": (os.path.basename(path), f)},
            timeout=120,
        )

    if res.status_code != 200:
        raise TranscriptionError(f"Scribe error {res.status_code}: {res.text[:300]}")

    body = res.json()
    text = (body.get("text") or "").strip()
    words = [w for w in body.get("words", []) if w.get("type") == "word"]
    raw_lang = body.get("language_code") or ""

    return {
        "text": text,
        "provider": "scribe",
        "requested_language": language,
        "detected_language": ISO3_TO_ISO1.get(raw_lang, raw_lang),
        "language_probability": round(body.get("language_probability") or 0.0, 3),
        "duration_sec": round(duration, 2),
        "segments": (
            [{"start": round(words[0]["start"], 2), "end": round(words[-1]["end"], 2), "text": text}]
            if words
            else []
        ),
    }


def transcribe_file(path: str, language: str) -> dict:
    duration = probe_duration(path)
    if duration > settings.max_duration_min * 60:
        raise AudioTooLong(duration)

    if settings.stt_provider == "scribe":
        try:
            return transcribe_scribe(path, language, duration)
        except Exception:
            if not settings.fallback_to_whisper:
                raise
            logger.exception("Scribe failed, falling back to Whisper")

    return transcribe_whisper(path, language, duration)
