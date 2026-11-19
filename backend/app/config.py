import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

STT_PROVIDERS = {"scribe", "whisper"}


def _bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    stt_provider: str = os.getenv("STT_PROVIDER", "scribe").strip().lower()
    fallback_to_whisper: bool = _bool("FALLBACK_TO_WHISPER", "true")
    scribe_model: str = os.getenv("SCRIBE_MODEL", "scribe_v1")
    elevenlabs_api_key: str = os.getenv("ELEVENLABS_API_KEY", "").strip()

    model_name: str = os.getenv("WHISPER_MODEL", "large-v3-turbo")
    device: str = os.getenv("WHISPER_DEVICE", "cpu")
    compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "100"))
    max_duration_min: int = int(os.getenv("MAX_DURATION_MIN", "30"))
    allowed_origins: tuple[str, ...] = tuple(
        o.strip()
        for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        if o.strip()
    )

    def __post_init__(self) -> None:
        if self.stt_provider not in STT_PROVIDERS:
            raise ValueError(f"STT_PROVIDER must be one of {sorted(STT_PROVIDERS)}")


settings = Settings()
