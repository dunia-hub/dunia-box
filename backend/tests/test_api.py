from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


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
