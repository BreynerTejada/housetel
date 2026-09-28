"""Paying the balance from the portal: a payment link (Wompi or the simulated gateway) created by
`finance.create_payment_intent`, returning to `/g/<token>?paid=1` (finance adds `payment_ref`)."""

from decimal import Decimal, InvalidOperation

from apps.core.errors import ConflictError, DomainError
from apps.core.money import D, quantize
from apps.core.tokens import portal_url


class NothingToPay(ConflictError):
    code = "nothing_to_pay"


def create_payment(reservation, *, amount=None):
    """A payment link for `amount` (default: the whole balance). 0 < amount ≤ balance (`invalid_amount`);
    nothing owed → 409 `nothing_to_pay`. An open, unexpired link of the portal for the same amount is reused
    (a guest tapping "Pay" twice gets one link)."""
    from apps.finance.models import PaymentIntent
    from apps.finance.services import (
        create_payment_intent,
        get_or_create_folio,
        guest_part,
        intent_is_stale,
    )

    currency = reservation.currency
    # The link pays the guest's folio: only the guest side's part (a company's part is the company's, P4).
    due = quantize(guest_part(reservation), currency)
    if due <= 0:
        raise NothingToPay("Tu reserva no tiene saldo pendiente")
    try:
        value = due if amount in (None, "") else quantize(D(str(amount)), currency)
    except (InvalidOperation, ValueError):
        raise DomainError("Escribe un monto válido", code="invalid_amount", due=due) from None
    if value <= Decimal("0") or value > due:
        raise DomainError(
            f"El monto debe ser mayor que cero y no superar el saldo ({due:.0f} {currency})",
            code="invalid_amount",
            due=due,
        )
    folio = get_or_create_folio(reservation)
    open_links = PaymentIntent.objects.filter(
        folio=folio,
        amount=value,
        status__in=[PaymentIntent.Status.CREATED, PaymentIntent.Status.PENDING],
        return_url__contains="/g/",
    ).order_by("-created_at")
    for intent in open_links:
        if not intent_is_stale(intent):
            return intent
    return create_payment_intent(folio, amount=value, return_url=f"{portal_url(reservation)}?paid=1")


def intent_payload(intent) -> dict:
    return {
        "reference": intent.reference,
        "checkout_url": intent.checkout_url,
        "amount": f"{intent.amount:.2f}",
        "currency": intent.currency,
        "status": intent.status,
        "mode": intent.mode,
        "expires_at": intent.expires_at.isoformat() if intent.expires_at else None,
    }
