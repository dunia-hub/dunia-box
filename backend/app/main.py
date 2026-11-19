import logging
import os
import tempfile
from datetime import date
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import settings
from .documents import DOCUMENT_TYPES, Document, Party
from .extract import ExtractionError, extract_document
from .transcribe import SUPPORTED_LANGUAGES, AudioTooLong, transcribe_file

logger = logging.getLogger("dunia-box")

ALLOWED_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".ogg", ".opus",
    ".webm", ".mp4", ".aac", ".flac",
}
CHUNK_SIZE = 1024 * 1024

DocumentType = Literal[
    "invoice", "receipt", "quotation", "memo", "letter", "minutes", "sale_agreement"
]

app = FastAPI(title="Dunia Box API", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class ExtractRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=20000)
    language: Literal["sw", "en"] = "en"
    document_type: DocumentType | None = None
    profile: Party | None = None
    today: date | None = None


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "stt_provider": settings.stt_provider,
        "fallback_to_whisper": settings.fallback_to_whisper,
        "whisper_model": settings.model_name,
        "llm_model": settings.llm_model,
    }


@app.get("/document-types")
def document_types() -> list[dict]:
    return [
        {"type": name, "schema": model.model_json_schema()}
        for name, model in DOCUMENT_TYPES.items()
    ]


@app.post("/documents/validate")
def validate_document(doc: Document) -> dict:
    return doc.model_dump(mode="json")


@app.post("/extract")
async def extract(req: ExtractRequest) -> dict:
    try:
        return await run_in_threadpool(
            extract_document,
            req.transcript,
            req.language,
            req.document_type,
            req.profile,
            req.today,
        )
    except ExtractionError as exc:
        logger.warning("Extraction failed: %s", exc)
        raise HTTPException(502, str(exc))


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
