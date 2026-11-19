from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import extract
from app.documents import Party
from app.main import app

client = TestClient(app)

TODAY = date(2026, 11, 19)
PROFILE = Party(name="Fatuma Plumbing", phone="0700000000")


def fake_llm(monkeypatch, *responses):
    calls = []
    queue = list(responses)

    def _fake(messages):
        calls.append(messages)
        return queue.pop(0)

    monkeypatch.setattr(extract, "call_llm", _fake)
    return calls


INVOICE = {
    "type": "invoice",
    "client": {"name": "Wanjiku Traders"},
    "items": [{"description": "Plumbing", "quantity": 3, "unit": "day", "unit_price": 5000}],
    "due_date": "2026-11-20",
}


def test_complete_invoice_uses_profile_and_computes_total(monkeypatch):
    fake_llm(monkeypatch, INVOICE)
    out = extract.extract_document("...", "sw", "invoice", PROFILE, TODAY)
    assert out["complete"] is True
    assert out["document"]["issuer"]["name"] == "Fatuma Plumbing"
    assert out["document"]["total"] == "15000.00"
    assert out["document"]["issue_date"] == "2026-11-19"
    assert out["document"]["language"] == "sw"


def test_missing_client_is_flagged(monkeypatch):
    data = {k: v for k, v in INVOICE.items() if k != "client"}
    fake_llm(monkeypatch, data)
    out = extract.extract_document("...", "en", "invoice", PROFILE, TODAY)
    assert out["complete"] is False
    assert "client" in out["missing_fields"]
    assert out["errors"] == []


def test_nulls_count_as_missing(monkeypatch):
    fake_llm(monkeypatch, {**INVOICE, "client": None, "notes": None})
    out = extract.extract_document("...", "en", "invoice", PROFILE, TODAY)
    assert "client" in out["missing_fields"]


def test_classifies_when_type_not_given(monkeypatch):
    receipt = {
        "type": "receipt",
        "payer": {"name": "Otieno Hardware"},
        "items": [{"description": "Cement", "quantity": 2, "unit": "bag", "unit_price": 1500}],
    }
    calls = fake_llm(monkeypatch, {"type": "receipt"}, receipt)
    out = extract.extract_document("...", "en", None, PROFILE, TODAY)
    assert out["document_type"] == "receipt"
    assert out["document"]["total"] == "3000.00"
    assert len(calls) == 2


def test_retries_once_on_bad_values(monkeypatch):
    bad = {**INVOICE, "due_date": "2026-11-01"}
    calls = fake_llm(monkeypatch, bad, INVOICE)
    out = extract.extract_document("...", "en", "invoice", PROFILE, TODAY)
    assert out["complete"] is True
    assert len(calls) == 2


def test_unknown_type_from_classifier_raises(monkeypatch):
    fake_llm(monkeypatch, {"type": "passport"})
    with pytest.raises(extract.ExtractionError):
        extract.extract_document("...", "en", None, PROFILE, TODAY)


def test_memo_sender_from_profile(monkeypatch):
    memo = {"to": ["All staff"], "subject": "Workshop", "body": "Saturday at 10."}
    fake_llm(monkeypatch, memo)
    out = extract.extract_document("...", "en", "memo", PROFILE, TODAY)
    assert out["document"]["sender"] == "Fatuma Plumbing"


def test_extract_endpoint_rejects_empty_transcript():
    res = client.post("/extract", json={"transcript": ""})
    assert res.status_code == 422


def test_extract_endpoint_returns_502_on_model_failure(monkeypatch):
    def _boom(messages):
        raise extract.ExtractionError("down")

    monkeypatch.setattr(extract, "call_llm", _boom)
    res = client.post("/extract", json={"transcript": "hello", "document_type": "memo"})
    assert res.status_code == 502


def test_calendar_maps_weekdays():
    cal = extract.upcoming_calendar(TODAY)
    assert "2026-11-20 Friday (Ijumaa) tomorrow / kesho" in cal
    assert "2026-11-27 Friday (Ijumaa)" in cal
    assert "2026-11-19 Thursday (Alhamisi) today / leo" in cal


def test_missing_item_description_is_flagged(monkeypatch):
    data = {**INVOICE, "items": [{"unit_price": 5000}]}
    fake_llm(monkeypatch, data)
    out = extract.extract_document("...", "sw", "invoice", PROFILE, TODAY)
    assert out["complete"] is False
    assert "items.0.description" in out["missing_fields"]


def test_receipt_payment_method_not_defaulted(monkeypatch):
    receipt = {
        "type": "receipt",
        "payer": {"name": "Otieno Hardware"},
        "items": [{"description": "Cement", "quantity": 2, "unit_price": 1500}],
    }
    fake_llm(monkeypatch, receipt)
    out = extract.extract_document("...", "en", "receipt", PROFILE, TODAY)
    assert out["document"]["payment_method"] is None
