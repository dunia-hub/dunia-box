from functools import lru_cache

from faster_whisper import WhisperModel

from .config import settings

SUPPORTED_LANGUAGES = {"sw", "en", "auto"}

# Nudges the model toward Kenyan Swahili/English code-switching.
MIXED_PROMPT = (
    "Mazungumzo haya ni kwa Kiswahili na English, "
    "wakati mwingine yamechanganywa."
)


class AudioTooLong(Exception):
    pass


@lru_cache(maxsize=1)
def get_model() -> WhisperModel:
    return WhisperModel(
        settings.model_name,
        device=settings.device,
        compute_type=settings.compute_type,
    )


def transcribe_file(path: str, language: str) -> dict:
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

    # info is available before segments are decoded, so long files stop early.
    if info.duration > settings.max_duration_min * 60:
        raise AudioTooLong(info.duration)

    out = [
        {
            "start": round(s.start, 2),
            "end": round(s.end, 2),
            "text": s.text.strip(),
        }
        for s in segments
    ]

    return {
        "text": " ".join(seg["text"] for seg in out).strip(),
        "requested_language": language,
        "detected_language": info.language,
        "language_probability": round(info.language_probability, 3),
        "duration_sec": round(info.duration, 2),
        "segments": out,
    }
