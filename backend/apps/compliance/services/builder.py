"""What an invoice says: lines grouped from the folio's charges, the customer (the booker) and the totals.

Grouping (one line per group, in this order: lodging, extras, fees, penalties, adjustments):
- lodging nights by (category, net unit price, tax treatment): "Alojamiento Estándar · 2 noches";
- extras by (extra, unit price, tax treatment), summing quantities;
- anything else by (kind, description, unit price, tax treatment).
Tax treatment of a charge: no `tax` → "excluded" (not subject to IVA, e.g. cancellation penalties); `tax` set
with `tax_amount = 0` → "exempt" (foreign non-resident, ET art. 481 lit. d); otherwise "taxed".
Totals are exactly the folio's: Σ net (`Charge.amount`) + Σ `Charge.tax_amount` of the given charges.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from apps.compliance.models import FINAL_CONSUMER_ID
from apps.core.i18n import t

EXEMPT_NOTE = "Exento de IVA — Art. 481 lit. d) E.T., servicios hoteleros a no residentes"
FINAL_CONSUMER_NAME = "Consumidor final"

# Guest.document_type → DIAN identification document code (tabla 13.2.1 del anexo técnico; Factus V2 uses
# the same codes as `identification_document_code`).
DIAN_DOCUMENT_CODES = {
    "CC": "13",
    "TI": "12",
    "CE": "22",
    "NIT": "31",
    "PA": "41",
    "DNI": "42",
    "PEP": "47",
    "PPT": "48",
    "OTHER": "42",
}
_KIND_ORDER = {"room": 0, "extra": 1, "fee": 2, "other": 3, "tax": 4, "cancellation_fee": 5, "adjustment": 6}
_LINE_CODES = {
    "cancellation_fee": "PEN",
    "fee": "CARGO",
    "adjustment": "AJUSTE",
    "other": "OTRO",
    "tax": "IMP",
}
_NIT_WEIGHTS = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)


@dataclass
class DocumentData:
    customer: dict
    lines: list[dict]
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    exempt_note: str
    charge_ids: list = field(default_factory=list)


def check_digit(nit: str) -> str:
    """DIAN check digit (dígito de verificación) of a NIT; accepts "800197268" or "800197268-4"."""
    digits = re.sub(r"\D", "", (nit or "").split("-")[0])
    total = sum(int(d) * _NIT_WEIGHTS[i] for i, d in enumerate(reversed(digits)))
    remainder = total % 11
    return str(11 - remainder if remainder > 1 else remainder)


def invoice_customer(guest, *, final_consumer_id: str = FINAL_CONSUMER_ID) -> dict:
    """Customer block of the invoice. Without an identity document it is the DIAN "consumidor final"."""
    contact = {
        "guest_id": str(guest.pk) if guest else None,
        "email": guest.email if guest else "",
        "phone": guest.phone if guest else "",
        "is_foreign_non_resident": bool(guest and guest.is_foreign_non_resident),
    }
    if guest is None or not guest.document_number:
        return {
            **contact,
            "is_final_consumer": True,
            "name": FINAL_CONSUMER_NAME,
            "document_type": "CC",
            "dian_document_code": "13",
            "document_number": final_consumer_id,
            "dv": "",
            "legal_organization": "person",
            "address": "",
            "city": "",
            "country": "CO",
            "nationality": guest.nationality if guest else "",
        }
    document_type = guest.document_type or ("PA" if guest.is_foreign_non_resident else "CC")
    is_company = document_type == "NIT"
    number = guest.document_number.split("-")[0] if is_company else guest.document_number
    return {
        **contact,
        "is_final_consumer": False,
        "name": guest.full_name,
        "document_type": document_type,
        "dian_document_code": DIAN_DOCUMENT_CODES.get(document_type, "13"),
        "document_number": number,
        "dv": check_digit(number) if is_company else "",
        "legal_organization": "company" if is_company else "person",
        "address": guest.address,
        "city": guest.city_of_residence,
        "country": (guest.country_of_residence or guest.nationality or "CO").upper(),
        "nationality": guest.nationality,
    }


def tax_status(charge) -> str:
    if charge.tax_id is None:
        return "excluded"
    return "exempt" if charge.tax_amount == 0 else "taxed"


def _tax_code(charge) -> str:
    if charge.tax_id is None:
        return ""
    return "04" if charge.tax.code.upper().startswith("INC") else "01"


def _group_key(charge) -> tuple:
    status = tax_status(charge)
    rate = charge.tax.rate if status == "taxed" else Decimal("0")
    if charge.kind == "room":
        category = charge.stay.room_type_id if charge.stay_id else None
        return ("room", category, charge.unit_price, status, rate)
    if charge.kind == "extra":
        return (
            "extra",
            charge.extra_id or charge.description.strip().lower(),
            charge.unit_price,
            status,
            rate,
        )
    return (charge.kind, charge.description.strip().lower(), charge.unit_price, status, rate)


def _line_code(charge) -> str:
    if charge.kind == "room":
        return f"ALOJ-{charge.stay.room_type.code}" if charge.stay_id else "ALOJ"
    if charge.kind == "extra":
        return f"EXT-{charge.extra.code}" if charge.extra_id else "EXT"
    return _LINE_CODES.get(charge.kind, "OTRO")


def _describe(charge, quantity: int) -> str:
    if charge.kind == "room":
        name = t(charge.stay.room_type.name, "es") if charge.stay_id else ""
        nights = "noche" if quantity == 1 else "noches"
        return f"Alojamiento {name} · {quantity} {nights}".replace("  ", " ")
    return charge.description


def group_lines(charges) -> list[dict]:
    groups: dict[tuple, dict] = {}
    for charge in charges:
        key = _group_key(charge)
        group = groups.get(key)
        if group is None:
            group = groups[key] = {
                "first": charge,
                "quantity": 0,
                "net": Decimal("0"),
                "tax": Decimal("0"),
                "ids": [],
            }
        group["quantity"] += charge.quantity
        group["net"] += charge.amount
        group["tax"] += charge.tax_amount
        group["ids"].append(str(charge.pk))
    ordered = sorted(groups.values(), key=lambda g: _KIND_ORDER.get(g["first"].kind, 9))
    lines = []
    for group in ordered:
        charge = group["first"]
        status = tax_status(charge)
        lines.append(
            {
                "code": _line_code(charge),
                "kind": charge.kind,
                "description": _describe(charge, group["quantity"]),
                "quantity": group["quantity"],
                "unit_price": f"{charge.unit_price:.2f}",
                "net": f"{group['net']:.2f}",
                "tax_code": _tax_code(charge),
                "tax_status": status,
                "tax_rate": f"{charge.tax.rate:.2f}" if status == "taxed" else "0.00",
                "tax_amount": f"{group['tax']:.2f}",
                "total": f"{group['net'] + group['tax']:.2f}",
                "charge_ids": group["ids"],
            }
        )
    return lines


def build_document(folio, charges, *, final_consumer_id: str = FINAL_CONSUMER_ID) -> DocumentData:
    """Customer, lines and totals of an invoice covering `charges` (non-voided charges of `folio`)."""
    reservation = folio.reservation
    guest = reservation.booker if reservation is not None else folio.guest
    lines = group_lines(charges)
    subtotal = sum((Decimal(line["net"]) for line in lines), Decimal("0"))
    tax_total = sum((Decimal(line["tax_amount"]) for line in lines), Decimal("0"))
    exempt = any(line["tax_status"] == "exempt" for line in lines)
    return DocumentData(
        customer=invoice_customer(guest, final_consumer_id=final_consumer_id),
        lines=lines,
        subtotal=subtotal,
        tax_total=tax_total,
        total=subtotal + tax_total,
        exempt_note=EXEMPT_NOTE if exempt else "",
        charge_ids=[charge.pk for charge in charges],
    )


def tax_totals(lines) -> dict[str, Decimal]:
    """Taxes of the document by DIAN tax code: {"01": IVA, "04": INC} (exempt/excluded lines add 0)."""
    totals = {"01": Decimal("0"), "04": Decimal("0")}
    for line in lines:
        code = line.get("tax_code") or "01"
        totals[code] = totals.get(code, Decimal("0")) + Decimal(line.get("tax_amount") or 0)
    return totals
