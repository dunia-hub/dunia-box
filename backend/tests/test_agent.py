from datetime import date

from fastapi.testclient import TestClient

from app import agent, extract
from app import main as main_module
from app.agent import AgentState, build_questions, completion_message, run_turn
from app.documents import Party
from app.main import app

client = TestClient(app)

TODAY = date(2026, 11, 19)
PROFILE = Party(name="Fatuma Plumbing")

ITEMS = [{"description": "Kazi ya mabomba", "quantity": 3, "unit": "siku", "unit_price": 5000}]


def fake_llm(monkeypatch, *responses):
    queue = list(responses)
    calls = []

    def _fake(messages):
        calls.append(messages)
        return queue.pop(0)

    monkeypatch.setattr(extract, "call_llm", _fake)
    monkeypatch.setattr(agent, "call_llm", _fake)
    monkeypatch.setattr(agent, "synthesize", lambda text: "AUDIO")
    return calls


def test_questions_dedupe_and_limit():
    qs = build_questions(["client.name", "client", "items.0.description", "items.1.description", "to"], "sw")
    assert qs == ["Hii ni ya nani?", "Ni bidhaa au kazi gani?"]


def test_unknown_field_uses_fallback():
    assert build_questions(["payment_terms"], "en") == ["Please tell me the payment terms."]


def test_first_turn_asks_for_missing_client(monkeypatch):
    fake_llm(monkeypatch, {"type": "invoice", "items": ITEMS})
    out = run_turn("...", AgentState(language="sw", document_type="invoice"), PROFILE, TODAY)
    assert out["complete"] is False
    assert out["reply_text"] == "Hii ni ya nani?"
    assert out["state"]["missing_fields"] == ["client"]
    assert out["state"]["draft"]["issuer"]["name"] == "Fatuma Plumbing"
    assert out["reply_audio"] == "AUDIO"


def test_second_turn_completes_document(monkeypatch):
    calls = fake_llm(
        monkeypatch,
        {"type": "invoice", "items": ITEMS},
        {"type": "invoice", "items": ITEMS, "client": {"name": "Wanjiku Traders"}},
    )
    first = run_turn("...", AgentState(language="sw", document_type="invoice"), PROFILE, TODAY)
    second = run_turn("Wanjiku Traders", AgentState(**first["state"]), PROFILE, TODAY)

    assert second["complete"] is True
    assert second["reply_text"] == "Tayari. Ankara ya Wanjiku Traders iko tayari, jumla KES 15,000."
    assert len(second["document_id"]) == 64
    assert "*Jumla: KES 15,000.00*" in second["whatsapp_text"]
    assert second["state"]["turns"] == 2
    assert "Current draft" in calls[1][1]["content"]


def test_completion_message_english_receipt():
    doc = {"type": "receipt", "language": "en", "payer": {"name": "Otieno Hardware"},
           "total": "3000.00", "currency": "KES"}
    assert completion_message(doc) == "Done. Your receipt for Otieno Hardware is ready, total KES 3,000."


def test_turn_endpoint_without_speech(monkeypatch):
    fake_llm(monkeypatch, {"type": "memo", "to": ["All staff"], "subject": "Workshop", "body": "Saturday at 10."})
    res = client.post("/agent/turn", json={
        "utterance": "Memo to all staff about Saturday workshop",
        "state": {"language": "en", "document_type": "memo"},
        "profile": {"name": "Dunia Hub"},
        "speak": False,
    })
    assert res.status_code == 200
    body = res.json()
    assert body["complete"] is True
    assert body["reply_audio"] is None
    assert body["document"]["sender"] == "Dunia Hub"


def test_voice_turn_endpoint(monkeypatch):
    fake_llm(monkeypatch, {"type": "invoice", "items": ITEMS})
    monkeypatch.setattr(main_module, "transcribe_file", lambda path, lang: {"text": "Niandikie invoice"})
    res = client.post(
        "/agent/voice-turn",
        files={"file": ("a.m4a", b"fake audio", "audio/mp4")},
        data={
            "state": '{"language": "sw", "document_type": "invoice"}',
            "profile": '{"name": "Fatuma Plumbing"}',
            "speak": "false",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["transcript"] == "Niandikie invoice"
    assert body["reply_text"] == "Hii ni ya nani?"


def test_voice_turn_rejects_bad_state():
    res = client.post(
        "/agent/voice-turn",
        files={"file": ("a.m4a", b"fake audio", "audio/mp4")},
        data={"state": "not json"},
    )
    assert res.status_code == 422
