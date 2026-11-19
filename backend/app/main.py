import logging
import os
import tempfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .transcribe import SUPPORTED_LANGUAGES, AudioTooLong, transcribe_file

logger = logging.getLogger("dunia-box")

ALLOWED_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".ogg", ".opus",
    ".webm", ".mp4", ".aac", ".flac",
}
CHUNK_SIZE = 1024 * 1024

app = FastAPI(title="Dunia Box API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "stt_provider": settings.stt_provider,
        "fallback_to_whisper": settings.fallback_to_whisper,
        "whisper_model": settings.model_name,
    }


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form("auto"),
) -> dict:
    language = language.strip().lower()
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(422, "language must be one of: sw, en, auto")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, f"Unsupported file type: {ext or 'none'}")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    fd, path = tempfile.mkstemp(suffix=ext)
    size = 0

    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := await file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        413, f"File larger than {settings.max_upload_mb} MB"
                    )
                out.write(chunk)

        if size == 0:
            raise HTTPException(400, "Empty file")

        try:
            return await run_in_threadpool(transcribe_file, path, language)
        except AudioTooLong:
            raise HTTPException(
                413, f"Audio longer than {settings.max_duration_min} minutes"
            )
        except Exception:
            logger.exception("Transcription failed")
            raise HTTPException(422, "Could not process this audio file")
    finally:
        # Audio is never kept after processing.
        if os.path.exists(path):
            os.remove(path)
