from pathlib import Path

from app.documents import parse_document
from app.render import render_pdf, whatsapp_text

OUT = Path(__file__).resolve().parents[2] / "output"

SAMPLES = {
    "invoice_sw": {
        "type": "invoice", "language": "sw", "issue_date": "2026-11-19", "reference": "INV-0001",
        "issuer": {"name": "Fatuma Plumbing", "phone": "0700 000 000"},
        "client": {"name": "Wanjiku Traders"},
        "items": [{"description": "Kazi ya mabomba", "quantity": 3, "unit": "siku", "unit_price": 5000}],
        "due_date": "2026-11-20",
    },
    "invoice_en": {
        "type": "invoice", "language": "en", "issue_date": "2026-11-19", "reference": "INV-0002",
        "issuer": {"name": "Fatuma Plumbing", "phone": "0700 000 000"},
        "client": {"name": "Wanjiku Traders"},
        "items": [
            {"description": "Plumbing work", "quantity": 3, "unit": "day", "unit_price": 5000},
            {"description": "PVC pipes", "quantity": 4, "unit_price": 850},
        ],
        "tax_rate": "0.16", "due_date": "2026-11-27", "notes": "Pay via M-PESA or USDC.",
    },
    "receipt_en": {
        "type": "receipt", "language": "en", "issue_date": "2026-11-19", "reference": "RCT-0001",
        "issuer": {"name": "Fatuma Plumbing"}, "payer": {"name": "Otieno Hardware"},
        "items": [{"description": "Cement", "quantity": 2, "unit": "bag", "unit_price": 1500}],
        "payment_method": "mpesa", "payment_reference": "SKL3X9Q2AB", "paid_on": "2026-11-19",
    },
    "quotation_sw": {
        "type": "quotation", "language": "sw", "issue_date": "2026-11-19",
        "issuer": {"name": "Fatuma Plumbing"}, "client": {"name": "Shule ya Msingi Kibera"},
        "items": [{"description": "Kubadilisha mabomba ya maji", "quantity": 1, "unit_price": 45000}],
        "valid_until": "2026-12-03",
    },
    "memo_en": {
        "type": "memo", "language": "en", "issue_date": "2026-11-20",
        "to": ["All Dunians"], "sender": "Dunia Hub", "cc": ["Workshop mentors"],
        "subject": "Saturday builder session",
        "body": "Our next builder session is on Saturday at 10am.\n\nBring your laptop and one idea you want feedback on.",
    },
    "letter_sw": {
        "type": "letter", "language": "sw", "issue_date": "2026-11-20",
        "sender": {"name": "Fatuma Yattani", "address": "Nairobi"},
        "recipient": {"name": "Chifu wa Kata ya Kilimani"},
        "subject": "Ombi la kibali cha mkutano",
        "salutation": "Mheshimiwa Chifu,",
        "body": "Tunaomba kibali cha kufanya mkutano wa jamii tarehe 28 Novemba 2026 katika ukumbi wa kata.\n\nMkutano utahusu mafunzo ya teknolojia kwa vijana.",
        "closing": "Wako mwaminifu,",
    },
    "minutes_en": {
        "type": "minutes", "language": "en", "issue_date": "2026-11-20",
        "title": "Weekly builders call", "location": "Online", "chair": "Fatuma",
        "attendees": ["Fatuma", "Kato", "Bronson"], "apologies": ["Tevin"],
        "agenda": ["Product progress", "Next workshop"],
        "discussion": [{"topic": "Product progress", "notes": "Speech to document extraction is working on Swahili and English voice notes."}],
        "decisions": ["Ship PDF templates this week"],
        "action_items": [{"task": "Review PDF templates", "owner": "Kato", "due": "2026-11-22"}],
        "next_meeting": "2026-11-27",
    },
    "sale_agreement_sw": {
        "type": "sale_agreement", "language": "sw", "issue_date": "2026-11-20",
        "seller": {"name": "Kamau Njoroge", "phone": "0711 111 111"},
        "buyer": {"name": "Achieng Otieno", "phone": "0722 222 222"},
        "item": "Toyota Probox", "item_details": "KDA 123A, rangi nyeupe",
        "price": 450000, "deposit": 150000,
        "payment_terms": "Salio lilipwe ndani ya siku 30",
        "handover_date": "2026-11-25",
        "conditions": ["Gari linauzwa jinsi lilivyo", "Muuzaji atakabidhi kadi ya usajili baada ya malipo kamili"],
        "witnesses": [{"name": "Mwangi Kariuki"}],
    },
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, data in SAMPLES.items():
        doc = parse_document(data).model_dump(mode="json")
        (OUT / f"{name}.pdf").write_bytes(render_pdf(doc))
        (OUT / f"{name}.txt").write_text(whatsapp_text(doc), encoding="utf-8")
        print(f"Wrote {name}.pdf and {name}.txt")
    print(f"\nSaved to {OUT}")


if __name__ == "__main__":
    main()
