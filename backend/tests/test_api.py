from fastapi.testclient import TestClient

from app.main import app
from app.transcribe import ISO3_TO_ISO1

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["stt_provider"] in {"scribe", "whisper"}


def test_rejects_bad_language():
    res = client.post(
        "/transcribe",
        files={"file": ("a.wav", b"123", "audio/wav")},
        data={"language": "fr"},
    )
    assert res.status_code == 422


def test_rejects_bad_extension():
    res = client.post(
        "/transcribe",
        files={"file": ("a.txt", b"123", "text/plain")},
        data={"language": "auto"},
    )
    assert res.status_code == 415


def test_rejects_empty_file():
    res = client.post(
        "/transcribe",
        files={"file": ("a.wav", b"", "audio/wav")},
        data={"language": "auto"},
    )
    assert res.status_code == 400


def test_rejects_unreadable_audio():
    res = client.post(
        "/transcribe",
        files={"file": ("a.wav", b"not really audio", "audio/wav")},
        data={"language": "auto"},
    )
    assert res.status_code == 422


def test_scribe_language_codes_map_to_iso1():
    assert ISO3_TO_ISO1["swa"] == "sw"
    assert ISO3_TO_ISO1["eng"] == "en"
