import json
import logging
import os
import tempfile
from datetime import date
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError

from .agent import AgentState, run_turn
from .config import settings
from .documents import DOCUMENT_TYPES, Document, Party
from .extract import ExtractionError, extract_document
from .render import fingerprint, render_pdf, whatsapp_text
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

app = FastAPI(title="Dunia Box API", version="0.6.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["X-Document-Id", "Content-Disposition"],
)


class ExtractRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=20000)
    language: Literal["sw", "en"] = "en"
    document_type: DocumentType | None = None
    profile: Party | None = None
    today: date | None = None


class TurnRequest(BaseModel):
    utterance: str = Field(min_length=1, max_length=20000)
    state: AgentState = AgentState()
    profile: Party | None = None
    today: date | None = None
    speak: bool = True


async def save_upload(file: UploadFile) -> str:
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
                    raise HTTPException(413, f"File larger than {settings.max_upload_mb} MB")
                out.write(chunk)
        if size == 0:
            raise HTTPException(400, "Empty file")
    except Exception:
        if os.path.exists(path):
            os.remove(path)
        raise
    return path


async def transcribe_path(path: str, language: str) -> dict:
    try:
        return await run_in_threadpool(transcribe_file, path, language)
    except AudioTooLong:
        raise HTTPException(413, f"Audio longer than {settings.max_duration_min} minutes")
    except Exception:
        logger.exception("Transcription failed")
        raise HTTPException(422, "Could not process this audio file")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "stt_provider": settings.stt_provider,
        "fallback_to_whisper": settings.fallback_to_whisper,
        "whisper_model": settings.model_name,
        "llm_model": settings.llm_model,
        "tts_enabled": settings.tts_enabled,
        "tts_model": settings.tts_model,
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


@app.post("/render/pdf")
async def render_pdf_endpoint(doc: Document) -> Response:
    data = doc.model_dump(mode="json")
    doc_id = fingerprint(data)
    pdf = await run_in_threadpool(render_pdf, data)
    filename = f"{data['type']}-{doc_id[:12]}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Document-Id": doc_id,
        },
    )


@app.post("/render/whatsapp")
def render_whatsapp_endpoint(doc: Document) -> dict:
    data = doc.model_dump(mode="json")
    return {"document_id": fingerprint(data), "text": whatsapp_text(data)}


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


@app.post("/agent/turn")
async def agent_turn(req: TurnRequest) -> dict:
    try:
        return await run_in_threadpool(
            run_turn, req.utterance, req.state, req.profile, req.today, req.speak
        )
    except ExtractionError as exc:
        logger.warning("Agent turn failed: %s", exc)
        raise HTTPException(502, str(exc))


@app.post("/agent/voice-turn")
async def agent_voice_turn(
    file: UploadFile = File(...),
    state: str = Form("{}"),
    profile: str = Form(""),
    speak: bool = Form(True),
) -> dict:
    try:
        agent_state = AgentState.model_validate(json.loads(state or "{}"))
        agent_profile = Party.model_validate(json.loads(profile)) if profile else None
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(422, f"Invalid state or profile: {exc}")

    path = await save_upload(file)
    try:
        transcript = await transcribe_path(path, "auto")
    finally:
        if os.path.exists(path):
            os.remove(path)

    utterance = transcript["text"].strip()
    if not utterance:
        raise HTTPException(422, "No speech detected")

    try:
        result = await run_in_threadpool(
            run_turn, utterance, agent_state, agent_profile, None, speak
        )
    except ExtractionError as exc:
        logger.warning("Agent turn failed: %s", exc)
        raise HTTPException(502, str(exc))

    return {"transcript": utterance, **result}


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form("auto"),
) -> dict:
    language = language.strip().lower()
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(422, "language must be one of: sw, en, auto")

    path = await save_upload(file)
    try:
        return await transcribe_path(path, language)
    finally:
        # Audio is never kept after processing.
        if os.path.exists(path):
            os.remove(path)
