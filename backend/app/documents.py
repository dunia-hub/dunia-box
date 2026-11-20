from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    computed_field,
    model_validator,
)

Language = Literal["sw", "en"]
Currency = Literal["KES", "USD", "USDC"]
PaymentMethod = Literal["mpesa", "cash", "bank", "card", "usdc", "other"]

CENTS = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def _drop_computed(cls, data):
        # Calculated fields come back from the API; ignore them on input.
        if isinstance(data, dict):
            computed = set(cls.model_computed_fields)
            if computed:
                data = {k: v for k, v in data.items() if k not in computed}
        return data


# ---------- Shared parts ----------

class Party(Strict):
    name: str = Field(min_length=1)
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    wallet: str | None = None  # Solana address, used for signing and payment


class LineItem(Strict):
    description: str = Field(min_length=1)
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit: str | None = None  # e.g. day, bag, hour
    unit_price: Decimal = Field(ge=0)

    @computed_field
    @property
    def amount(self) -> Decimal:
        return money(self.quantity * self.unit_price)


class DocumentBase(Strict):
    language: Language = "en"
    issue_date: date
    reference: str | None = None  # document number, e.g. INV-0001


class PricedDocument(DocumentBase):
    currency: Currency = "KES"
    items: list[LineItem] = Field(min_length=1)
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1)  # 0.16 = 16% VAT

    @computed_field
    @property
    def subtotal(self) -> Decimal:
        return money(sum((i.amount for i in self.items), Decimal("0")))

    @computed_field
    @property
    def tax(self) -> Decimal:
        return money(self.subtotal * self.tax_rate)

    @computed_field
    @property
    def total(self) -> Decimal:
        return money(self.subtotal + self.tax)


# ---------- Money documents ----------

class Invoice(PricedDocument):
    type: Literal["invoice"] = "invoice"
    issuer: Party
    client: Party
    due_date: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.due_date and self.due_date < self.issue_date:
            raise ValueError("due_date cannot be before issue_date")
        return self


class Receipt(PricedDocument):
    type: Literal["receipt"] = "receipt"
    issuer: Party
    payer: Party
    payment_method: PaymentMethod | None = None
    payment_reference: str | None = None  # M-PESA code or transaction signature
    paid_on: date | None = None
    notes: str | None = None


class Quotation(PricedDocument):
    type: Literal["quotation"] = "quotation"
    issuer: Party
    client: Party
    valid_until: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.valid_until and self.valid_until < self.issue_date:
            raise ValueError("valid_until cannot be before issue_date")
        return self


# ---------- Everyday paperwork ----------

class Memo(DocumentBase):
    type: Literal["memo"] = "memo"
    to: list[str] = Field(min_length=1)
    sender: str = Field(min_length=1)
    cc: list[str] = []
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)


class Letter(DocumentBase):
    type: Literal["letter"] = "letter"
    sender: Party
    recipient: Party
    subject: str = Field(min_length=1)
    salutation: str | None = None
    body: str = Field(min_length=1)
    closing: str | None = None


class DiscussionPoint(Strict):
    topic: str = Field(min_length=1)
    notes: str = Field(min_length=1)


class ActionItem(Strict):
    task: str = Field(min_length=1)
    owner: str | None = None
    due: date | None = None


class Minutes(DocumentBase):
    type: Literal["minutes"] = "minutes"
    title: str = Field(min_length=1)
    location: str | None = None
    chair: str | None = None
    attendees: list[str] = Field(min_length=1)
    apologies: list[str] = []
    agenda: list[str] = []
    discussion: list[DiscussionPoint] = []
    decisions: list[str] = []
    action_items: list[ActionItem] = []
    next_meeting: date | None = None


# ---------- Agreements ----------

class SaleAgreement(DocumentBase):
    type: Literal["sale_agreement"] = "sale_agreement"
    seller: Party
    buyer: Party
    item: str = Field(min_length=1)          # e.g. Toyota Probox, plot, cow
    item_details: str | None = None          # e.g. reg number, serial, location
    currency: Currency = "KES"
    price: Decimal = Field(gt=0)
    deposit: Decimal = Field(default=Decimal("0"), ge=0)
    payment_terms: str | None = None
    handover_date: date | None = None
    conditions: list[str] = []
    witnesses: list[Party] = []

    @model_validator(mode="after")
    def check_deposit(self):
        if self.deposit > self.price:
            raise ValueError("deposit cannot be more than price")
        return self

    @computed_field
    @property
    def balance(self) -> Decimal:
        return money(self.price - self.deposit)


# ---------- Registry ----------

Document = Annotated[
    Union[Invoice, Receipt, Quotation, Memo, Letter, Minutes, SaleAgreement],
    Field(discriminator="type"),
]

DOCUMENT_TYPES: dict[str, type[DocumentBase]] = {
    "invoice": Invoice,
    "receipt": Receipt,
    "quotation": Quotation,
    "memo": Memo,
    "letter": Letter,
    "minutes": Minutes,
    "sale_agreement": SaleAgreement,
}

document_adapter: TypeAdapter = TypeAdapter(Document)


def parse_document(data: dict):
    return document_adapter.validate_python(data)
