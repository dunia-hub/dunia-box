from fastapi.testclient import TestClient

from app.documents import parse_document
from app.main import app
from app.render import fingerprint, fmt_date, fmt_money, whatsapp_text
from scripts.render_samples import SAMPLES

client = TestClient(app)

INVOICE = SAMPLES["invoice_sw"]


def dumped(data):
    return parse_document(data).model_dump(mode="json")


def test_money_and_date_formatting():
    assert fmt_money("15000", "KES") == "KES 15,000.00"
    assert fmt_date("2026-11-20", "sw") == "20 Novemba 2026"
    assert fmt_date("2026-11-20", "en") == "20 November 2026"


def test_fingerprint_ignores_key_order():
    doc = dumped(INVOICE)
    reordered = dict(reversed(list(doc.items())))
    assert fingerprint(doc) == fingerprint(reordered)


def test_fingerprint_changes_when_content_changes():
    doc = dumped(INVOICE)
    edited = {**doc, "due_date": "2026-11-27"}
    assert fingerprint(doc) != fingerprint(edited)


def test_whatsapp_invoice_in_swahili():
    text = whatsapp_text(dumped(INVOICE))
    assert "*Ankara INV-0001*" in text
    assert "*Jumla: KES 15,000.00*" in text
    assert "20 Novemba 2026" in text


def test_whatsapp_covers_every_type():
    for name, data in SAMPLES.items():
        text = whatsapp_text(dumped(data))
        assert text.strip(), name


def test_pdf_endpoint_returns_pdf_with_id():
    res = client.post("/render/pdf", json=INVOICE)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF")
    assert len(res.headers["x-document-id"]) == 64


def test_pdf_renders_every_type():
    for name, data in SAMPLES.items():
        res = client.post("/render/pdf", json=data)
        assert res.status_code == 200, name
        assert res.content.startswith(b"%PDF"), name


def test_whatsapp_endpoint():
    res = client.post("/render/whatsapp", json=INVOICE)
    assert res.status_code == 200
    body = res.json()
    assert body["document_id"] == fingerprint(dumped(INVOICE))
    assert "Ankara" in body["text"]


def test_render_rejects_invalid_document():
    res = client.post("/render/pdf", json={**INVOICE, "items": []})
    assert res.status_code == 422
