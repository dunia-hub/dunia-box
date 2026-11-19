from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.documents import parse_document
from app.main import app

client = TestClient(app)

PLUMBER = {"name": "Fatuma Plumbing"}
WANJIKU = {"name": "Wanjiku Traders"}


def invoice(**overrides):
    data = {
        "type": "invoice",
        "language": "sw",
        "issue_date": "2026-11-19",
        "issuer": PLUMBER,
        "client": WANJIKU,
        "items": [
            {"description": "Plumbing", "quantity": 3, "unit": "day", "unit_price": 5000}
        ],
        "due_date": "2026-11-20",
    }
    data.update(overrides)
    return data


def test_invoice_totals():
    doc = parse_document(invoice())
    assert doc.subtotal == Decimal("15000.00")
    assert doc.tax == Decimal("0.00")
    assert doc.total == Decimal("15000.00")


def test_invoice_with_vat():
    doc = parse_document(invoice(tax_rate="0.16"))
    assert doc.tax == Decimal("2400.00")
    assert doc.total == Decimal("17400.00")


def test_invoice_due_before_issue_rejected():
    with pytest.raises(ValidationError):
        parse_document(invoice(due_date="2026-11-01"))


def test_invoice_needs_items():
    with pytest.raises(ValidationError):
        parse_document(invoice(items=[]))


def test_receipt_totals():
    doc = parse_document({
        "type": "receipt",
        "issue_date": "2026-11-19",
        "issuer": {"name": "Otieno Hardware"},
        "payer": {"name": "Fatuma"},
        "items": [{"description": "Cement", "quantity": 2, "unit": "bag", "unit_price": 1500}],
        "payment_method": "mpesa",
    })
    assert doc.total == Decimal("3000.00")


def test_sale_agreement_balance():
    doc = parse_document({
        "type": "sale_agreement",
        "issue_date": "2026-11-19",
        "seller": {"name": "Kamau"},
        "buyer": {"name": "Achieng"},
        "item": "Toyota Probox",
        "item_details": "KDA 123A",
        "price": 450000,
        "deposit": 150000,
    })
    assert doc.balance == Decimal("300000.00")


def test_sale_agreement_deposit_above_price_rejected():
    with pytest.raises(ValidationError):
        parse_document({
            "type": "sale_agreement",
            "issue_date": "2026-11-19",
            "seller": {"name": "Kamau"},
            "buyer": {"name": "Achieng"},
            "item": "Cow",
            "price": 50000,
            "deposit": 60000,
        })


def test_memo_needs_recipient():
    with pytest.raises(ValidationError):
        parse_document({
            "type": "memo",
            "issue_date": "2026-11-19",
            "to": [],
            "sender": "Dunia Hub",
            "subject": "Workshop",
            "body": "Saturday at 10.",
        })


def test_minutes_minimal():
    doc = parse_document({
        "type": "minutes",
        "issue_date": "2026-11-19",
        "title": "Weekly builders call",
        "attendees": ["Fatuma", "Kato"],
        "decisions": ["Ship PR 3 today"],
    })
    assert doc.attendees == ["Fatuma", "Kato"]


def test_unknown_type_rejected():
    with pytest.raises(ValidationError):
        parse_document({"type": "passport", "issue_date": "2026-11-19"})


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        parse_document(invoice(colour="blue"))


def test_document_types_endpoint():
    res = client.get("/document-types")
    assert res.status_code == 200
    assert len(res.json()) == 7


def test_validate_endpoint_returns_totals():
    res = client.post("/documents/validate", json=invoice())
    assert res.status_code == 200
    assert res.json()["total"] == "15000.00"


def test_validate_endpoint_rejects_bad_doc():
    res = client.post("/documents/validate", json=invoice(items=[]))
    assert res.status_code == 422
