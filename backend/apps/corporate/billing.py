"""Read model of the reservation's "Facturación" tab: who pays, the folios with their parts and the company's
credit (nothing here writes)."""

from decimal import Decimal

from apps.corporate.routing import ROUTE_VALUES, billing_of
from apps.corporate.services import _credit_payload, company_ref, credit_status
from apps.finance import services as finance
from apps.finance.models import Folio
from apps.finance.reporting import annotate_folio_totals

ZERO = Decimal("0")


def _money(value) -> str:
    return f"{value:.2f}"


def billing_payload(reservation) -> dict:
    billing = billing_of(reservation)
    booker = reservation.booker
    parts = finance.company_parts(reservation)
    total = finance.reservation_total_balance(reservation)
    guest_due = total - sum((part.expected for part in parts), ZERO)
    folios = annotate_folio_totals(
        Folio.objects.filter(reservation=reservation).select_related("company").order_by("created_at")
    )
    company = billing.company if billing and billing.company_id else None
    return {
        "reservation": {
            "id": str(reservation.pk),
            "code": reservation.code,
            "status": reservation.status,
            "checkin_date": reservation.checkin_date.isoformat(),
            "checkout_date": reservation.checkout_date.isoformat(),
            "booker": {
                "id": str(booker.pk),
                "full_name": booker.full_name,
                "document_type": booker.document_type,
                "document_number": booker.document_number,
                "email": booker.email,
            },
        },
        "billing": {
            "bill_to": billing.bill_to if billing else "guest",
            "company": company_ref(company) if company else None,
            "routing": list(billing.routing or []) if billing else [],
            "purchase_order": billing.purchase_order if billing else "",
            "notes": billing.notes if billing else "",
            "updated_at": billing.updated_at.isoformat() if billing else None,
            "updated_by": billing.updated_by.full_name if billing and billing.updated_by_id else None,
        },
        "folios": [
            {
                "id": str(folio.pk),
                "folio_type": folio.folio_type,
                "status": folio.status,
                "company": company_ref(folio.company) if folio.company_id else None,
                "balance": _money(
                    folio.charges_net + folio.tax_amount_total - folio.payments_sum + folio.refunds_sum
                ),
                "expected_balance": _money(finance.folio_expected_balance(folio)),
            }
            for folio in folios
        ],
        "balances": {
            "total": _money(total),
            "guest": _money(guest_due),
            "checkout_due": _money(total - sum((part.expected for part in parts if part.credit), ZERO)),
            "companies": [
                {
                    "company": company_ref(part.company),
                    "expected": _money(part.expected),
                    "credit": part.credit,
                    "blocks_checkout": not part.credit and part.expected > 0,
                }
                for part in parts
            ],
        },
        "credit": _credit_payload(credit_status(company)) if company else None,
        "routes": ROUTE_VALUES,
    }
