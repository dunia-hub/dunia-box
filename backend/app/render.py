import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).parent / "templates"

SWAHILI_MONTHS = [
    "Januari", "Februari", "Machi", "Aprili", "Mei", "Juni",
    "Julai", "Agosti", "Septemba", "Oktoba", "Novemba", "Desemba",
]

LABELS = {
    "en": {
        "invoice": "Invoice", "receipt": "Receipt", "quotation": "Quotation",
        "memo": "Memo", "letter": "Letter", "minutes": "Meeting Minutes",
        "sale_agreement": "Sale Agreement",
        "from": "From", "bill_to": "Bill to", "to": "To", "date": "Date",
        "due_date": "Due date", "valid_until": "Valid until", "reference": "No.",
        "description": "Description", "qty": "Qty", "unit_price": "Unit price",
        "amount": "Amount", "subtotal": "Subtotal", "tax": "Tax", "total": "Total",
        "amount_due": "Amount due", "paid": "Paid",
        "notes": "Notes", "received_from": "Received from",
        "payment_method": "Payment method", "payment_reference": "Payment reference",
        "paid_on": "Paid on", "subject": "Subject", "cc": "Cc",
        "chair": "Chair", "location": "Location", "attendees": "Present",
        "apologies": "Apologies", "agenda": "Agenda", "discussion": "Discussion",
        "decisions": "Decisions", "action_items": "Action items", "owner": "Owner",
        "due": "Due", "next_meeting": "Next meeting",
        "seller": "Seller", "buyer": "Buyer", "item": "Item",
        "item_details": "Item details", "price": "Price", "deposit": "Deposit",
        "balance": "Balance", "payment_terms": "Payment terms",
        "handover_date": "Handover date", "conditions": "Conditions",
        "witnesses": "Witnesses", "signature": "Signature", "name": "Name",
        "pay_here": "Pay here", "verify": "Verify",
        "document_id": "Document ID", "made_with": "Made with Dunia Box",
        "mpesa": "M-PESA", "cash": "Cash", "bank": "Bank transfer", "card": "Card",
        "usdc": "USDC", "other": "Other",
    },
    "sw": {
        "invoice": "Ankara", "receipt": "Risiti", "quotation": "Nukuu ya Bei",
        "memo": "Memo", "letter": "Barua", "minutes": "Kumbukumbu za Mkutano",
        "sale_agreement": "Mkataba wa Mauzo",
        "from": "Kutoka", "bill_to": "Kwa", "to": "Kwa", "date": "Tarehe",
        "due_date": "Tarehe ya kulipa", "valid_until": "Halali hadi", "reference": "Nambari",
        "description": "Maelezo", "qty": "Idadi", "unit_price": "Bei kwa kimoja",
        "amount": "Kiasi", "subtotal": "Jumla ndogo", "tax": "Kodi", "total": "Jumla",
        "amount_due": "Kiasi kinachodaiwa", "paid": "Imelipwa",
        "notes": "Maelezo ya ziada", "received_from": "Imepokelewa kutoka",
        "payment_method": "Njia ya malipo", "payment_reference": "Nambari ya malipo",
        "paid_on": "Ililipwa tarehe", "subject": "Kuhusu", "cc": "Nakala",
        "chair": "Mwenyekiti", "location": "Mahali", "attendees": "Waliohudhuria",
        "apologies": "Udhuru", "agenda": "Ajenda", "discussion": "Majadiliano",
        "decisions": "Maamuzi", "action_items": "Hatua za kuchukua", "owner": "Mhusika",
        "due": "Tarehe", "next_meeting": "Mkutano ujao",
        "seller": "Muuzaji", "buyer": "Mnunuzi", "item": "Bidhaa",
        "item_details": "Maelezo ya bidhaa", "price": "Bei", "deposit": "Malipo ya awali",
        "balance": "Salio", "payment_terms": "Masharti ya malipo",
        "handover_date": "Tarehe ya kukabidhi", "conditions": "Masharti",
        "witnesses": "Mashahidi", "signature": "Sahihi", "name": "Jina",
        "pay_here": "Lipa hapa", "verify": "Thibitisha",
        "document_id": "Kitambulisho cha hati", "made_with": "Imetengenezwa na Dunia Box",
        "mpesa": "M-PESA", "cash": "Taslimu", "bank": "Benki", "card": "Kadi",
        "usdc": "USDC", "other": "Nyingine",
    },
}


def label(key: str, language: str) -> str:
    return LABELS.get(language, LABELS["en"]).get(key, key)


def fmt_money(value, currency: str = "KES") -> str:
    if value is None:
        return ""
    return f"{currency} {Decimal(str(value)):,.2f}"


def fmt_qty(value) -> str:
    if value is None:
        return ""
    d = Decimal(str(value)).normalize()
    return f"{d:f}"


def fmt_date(value, language: str = "en") -> str:
    if not value:
        return ""
    d = value if isinstance(value, date) else date.fromisoformat(str(value))
    if language == "sw":
        return f"{d.day} {SWAHILI_MONTHS[d.month - 1]} {d.year}"
    return f"{d.day} {d.strftime('%B')} {d.year}"


def fingerprint(doc: dict) -> str:
    canonical = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def short_id(doc: dict) -> str:
    return fingerprint(doc)[:12]


# ---------- WhatsApp text ----------

def _items_lines(doc: dict, lang: str) -> list[str]:
    cur = doc.get("currency", "KES")
    lines = []
    for item in doc.get("items", []):
        qty = fmt_qty(item.get("quantity"))
        unit = f" {item['unit']}" if item.get("unit") else ""
        lines.append(
            f"• {item['description']}: {qty}{unit} x {fmt_money(item['unit_price'], cur)}"
            f" = {fmt_money(item['amount'], cur)}"
        )
    return lines


def whatsapp_text(doc: dict) -> str:
    lang = doc.get("language", "en")
    t = lambda key: label(key, lang)  # noqa: E731
    kind = doc["type"]
    cur = doc.get("currency", "KES")
    ref = f" {doc['reference']}" if doc.get("reference") else ""
    lines = [f"*{t(kind)}{ref}*", f"{t('date')}: {fmt_date(doc['issue_date'], lang)}"]

    if kind in {"invoice", "quotation"}:
        lines += [f"{t('from')}: {doc['issuer']['name']}", f"{t('bill_to')}: {doc['client']['name']}", ""]
        lines += _items_lines(doc, lang)
        if Decimal(str(doc.get("tax", "0"))) > 0:
            lines.append(f"{t('tax')}: {fmt_money(doc['tax'], cur)}")
        lines.append(f"*{t('total')}: {fmt_money(doc['total'], cur)}*")
        if kind == "invoice" and doc.get("due_date"):
            lines.append(f"{t('due_date')}: {fmt_date(doc['due_date'], lang)}")
        if kind == "quotation" and doc.get("valid_until"):
            lines.append(f"{t('valid_until')}: {fmt_date(doc['valid_until'], lang)}")

    elif kind == "receipt":
        lines += [f"{t('from')}: {doc['issuer']['name']}", f"{t('received_from')}: {doc['payer']['name']}", ""]
        lines += _items_lines(doc, lang)
        lines.append(f"*{t('total')}: {fmt_money(doc['total'], cur)}*")
        if doc.get("payment_method"):
            lines.append(f"{t('payment_method')}: {t(doc['payment_method'])}")
        if doc.get("payment_reference"):
            lines.append(f"{t('payment_reference')}: {doc['payment_reference']}")

    elif kind == "memo":
        lines += [
            f"{t('to')}: {', '.join(doc['to'])}",
            f"{t('from')}: {doc['sender']}",
            f"*{t('subject')}: {doc['subject']}*",
            "",
            doc["body"],
        ]

    elif kind == "letter":
        lines += [
            f"{t('from')}: {doc['sender']['name']}",
            f"{t('to')}: {doc['recipient']['name']}",
            f"*{t('subject')}: {doc['subject']}*",
            "",
            doc["body"],
        ]

    elif kind == "minutes":
        lines += [f"*{doc['title']}*", f"{t('attendees')}: {', '.join(doc['attendees'])}"]
        if doc.get("decisions"):
            lines += ["", f"*{t('decisions')}*"] + [f"• {d}" for d in doc["decisions"]]
        if doc.get("action_items"):
            lines += ["", f"*{t('action_items')}*"]
            for a in doc["action_items"]:
                owner = f" ({a['owner']})" if a.get("owner") else ""
                lines.append(f"• {a['task']}{owner}")

    elif kind == "sale_agreement":
        lines += [
            f"{t('seller')}: {doc['seller']['name']}",
            f"{t('buyer')}: {doc['buyer']['name']}",
            f"{t('item')}: {doc['item']}" + (f" ({doc['item_details']})" if doc.get("item_details") else ""),
            f"*{t('price')}: {fmt_money(doc['price'], cur)}*",
            f"{t('deposit')}: {fmt_money(doc['deposit'], cur)}",
            f"{t('balance')}: {fmt_money(doc['balance'], cur)}",
        ]

    lines += ["", f"{t('document_id')}: {short_id(doc)}"]
    return "\n".join(lines)


# ---------- PDF ----------

def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["money"] = fmt_money
    env.filters["qty"] = fmt_qty
    env.filters["date"] = fmt_date
    return env


def render_html(doc: dict) -> str:
    lang = doc.get("language", "en")
    template = _env().get_template(f"{doc['type']}.html")
    return template.render(
        doc=doc,
        lang=lang,
        t=lambda key: label(key, lang),
        doc_id=fingerprint(doc),
        short_id=short_id(doc),
    )


def render_pdf(doc: dict) -> bytes:
    from weasyprint import HTML  # imported here so tests without Pango still load

    return HTML(string=render_html(doc), base_url=str(TEMPLATES_DIR)).write_pdf()
