import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
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


settings = Settings()
