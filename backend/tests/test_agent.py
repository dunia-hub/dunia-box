from datetime import date

from fastapi.testclient import TestClient

from app import agent, extract
from app import main as main_module
from app.agent import (
    AgentState,
    build_questions,
    completion_message,
    confirmation_message,
    is_no,
    is_skip,
    is_yes,
    run_turn,
)
from app.documents import Party
from app.main import app

client = TestClient(app)

TODAY = date(2026, 11, 19)
PROFILE = Party(name="Fatuma Plumbing", phone="0700000000")
PROFILE_NO_PHONE = Party(name="Fatuma Plumbing")

ITEMS = [{"description": "Kazi ya mabomba", "quantity": 3, "unit": "siku", "unit_price": 5000}]
WANJIKU = {"name": "Wanjiku Traders"}


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


def test_yes_no_skip_words():
    assert is_yes("Ndio") and is_yes("sawa, tengeneza") and is_yes("yes please")
    assert not is_yes("ndio lakini badilisha bei iwe elfu sita kwa siku")
    assert is_no("hapana") and is_no("wait")
    assert is_skip("hakuna") and is_skip("skip") and not is_skip("ilipwe Ijumaa")


def test_one_question_at_a_time():
    qs = build_questions(["client.name", "client", "items.0.description", "to"], "sw")
    assert qs == ["Hii ni ya nani?"]


def test_no_profile_asks_for_issuer(monkeypatch):
    fake_llm(monkeypatch, {"type": "invoice", "items": ITEMS, "client": WANJIKU})
    out = run_turn("...", AgentState(language="sw", document_type="invoice"), None, TODAY)
    assert out["reply_text"] == "Hati itolewe kwa jina gani?"


def test_full_conversation_with_due_date_and_confirmation(monkeypatch):
    calls = fake_llm(
        monkeypatch,
        {"type": "invoice", "items": ITEMS},
        {"type": "invoice", "items": ITEMS, "client": WANJIKU},
    )
    s = AgentState(language="sw", document_type="invoice")

    t1 = run_turn("Niandikie invoice...", s, PROFILE, TODAY)
    assert t1["reply_text"] == "Hii ni ya nani?"

    t2 = run_turn("Wanjiku Traders", AgentState(**t1["state"]), PROFILE, TODAY)
    assert t2["reply_text"] == "Tarehe ya kulipa ni lini?"
    assert t2["preview"]["total"] == "15000.00"

    t3 = run_turn("Ijumaa", AgentState(**t2["state"]), PROFILE, TODAY)
    assert t3["reply_text"] == "Nimeandaa ankara ya Wanjiku Traders, jumla KES 15,000, ilipwe 20 Novemba 2026. Niitengeneze?"
    assert t3["state"]["awaiting_confirmation"] is True

    t4 = run_turn("Ndio", AgentState(**t3["state"]), PROFILE, TODAY)
    assert t4["complete"] is True
    assert t4["reply_text"] == "Tayari. Ankara ya Wanjiku Traders iko tayari, jumla KES 15,000."
    assert len(t4["document_id"]) == 64
    assert len(calls) == 2  # the date and "Ndio" need no model call


def test_due_date_cannot_be_skipped(monkeypatch):
    fake_llm(
        monkeypatch,
        {"type": "invoice", "items": ITEMS, "client": WANJIKU},
        {"type": "invoice", "items": ITEMS, "client": WANJIKU},
    )
    t1 = run_turn("...", AgentState(language="sw", document_type="invoice"), PROFILE, TODAY)
    assert t1["reply_text"] == "Tarehe ya kulipa ni lini?"
    t2 = run_turn("ruka", AgentState(**t1["state"]), PROFILE, TODAY)
    assert t2["reply_text"] == "Tarehe ya kulipa ni lini?"


def test_skip_optional_phone_without_model_call(monkeypatch):
    calls = fake_llm(
        monkeypatch,
        {"type": "invoice", "items": ITEMS, "client": WANJIKU, "due_date": "2026-11-27"},
    )
    t1 = run_turn("...", AgentState(language="en", document_type="invoice"), PROFILE_NO_PHONE, TODAY)
    assert t1["reply_text"] == "What's your phone number? It will appear on the document."

    t2 = run_turn("skip", AgentState(**t1["state"]), PROFILE_NO_PHONE, TODAY)
    assert t2["reply_text"].endswith("Shall I create it?")
    assert len(calls) == 1


def test_no_during_confirmation_asks_what_to_change(monkeypatch):
    fake_llm(monkeypatch, {"type": "invoice", "items": ITEMS, "client": WANJIKU, "due_date": "2026-11-27"})
    t1 = run_turn("...", AgentState(language="sw", document_type="invoice"), PROFILE, TODAY)
    assert t1["state"]["awaiting_confirmation"] is True

    t2 = run_turn("hapana", AgentState(**t1["state"]), PROFILE, TODAY)
    assert t2["reply_text"] == "Sawa. Niambie unachotaka kubadilisha."
    assert t2["complete"] is False


def test_change_during_confirmation_updates_and_reconfirms(monkeypatch):
    fake_llm(
        monkeypatch,
        {"type": "invoice", "items": ITEMS, "client": WANJIKU, "due_date": "2026-11-27"},
        {"type": "invoice", "client": WANJIKU, "due_date": "2026-11-27",
         "items": [{**ITEMS[0], "unit_price": 6000}]},
    )
    t1 = run_turn("...", AgentState(language="sw", document_type="invoice"), PROFILE, TODAY)
    t2 = run_turn("badilisha bei iwe elfu sita kwa siku", AgentState(**t1["state"]), PROFILE, TODAY)
    assert "KES 18,000" in t2["reply_text"]
    assert t2["state"]["awaiting_confirmation"] is True


def test_messages_in_english():
    doc = {"type": "receipt", "language": "en", "payer": {"name": "Otieno Hardware"},
           "total": "3000.00", "currency": "KES"}
    assert completion_message(doc) == "Done. Your receipt for Otieno Hardware is ready, total KES 3,000."
    assert confirmation_message(doc) == "I've prepared your receipt for Otieno Hardware, total KES 3,000. Shall I create it?"


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
    assert body["reply_audio"] is None
    assert body["state"]["awaiting_confirmation"] is True
    assert body["preview"]["sender"] == "Dunia Hub"


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


def test_spoken_date_answer_needs_no_model_call(monkeypatch):
    calls = fake_llm(monkeypatch, {"type": "invoice", "items": ITEMS, "client": WANJIKU})
    t1 = run_turn("...", AgentState(language="sw", document_type="invoice"), PROFILE, TODAY)
    assert t1["state"]["asking"] == "due_date"

    t2 = run_turn("Ijumaa", AgentState(**t1["state"]), PROFILE, TODAY)
    assert t2["state"]["draft"]["due_date"] == "2026-11-20"  # TODAY is Thursday 19 Nov
    assert t2["reply_text"].endswith("Niitengeneze?")
    assert len(calls) == 1


def test_required_followup_stops_after_two_tries(monkeypatch):
    fake_llm(
        monkeypatch,
        {"type": "invoice", "items": ITEMS, "client": WANJIKU},
        {"type": "invoice", "items": ITEMS, "client": WANJIKU},
        {"type": "invoice", "items": ITEMS, "client": WANJIKU},
    )
    t1 = run_turn("...", AgentState(language="sw", document_type="invoice"), PROFILE, TODAY)
    t2 = run_turn("sijui bado", AgentState(**t1["state"]), PROFILE, TODAY)
    assert t2["reply_text"] == "Tarehe ya kulipa ni lini?"
    t3 = run_turn("sijui bado", AgentState(**t2["state"]), PROFILE, TODAY)
    assert t3["reply_text"].endswith("Niitengeneze?")
