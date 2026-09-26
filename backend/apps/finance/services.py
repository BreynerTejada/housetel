"""Finance contracts (spec §4.2 + plan §C). Phase A implements folio/charge/payment/balances simply;
B4 adds audit, cash-shift rules, void/refund, payment intents and providers.

`Charge.amount` is net; `tax_amount` goes apart. Folio balance = Σ non-voided charges (amount + tax)
− Σ approved payments + Σ approved refunds.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import F, Sum

from apps.core import signals
from apps.core.errors import DomainError
from apps.core.money import D, quantize
from apps.finance.models import Charge, Folio, Payment, PaymentIntent, Refund

ZERO = Decimal("0")
CENTS = Decimal("0.01")
# Stays whose total is owed: everything except cancelled / no-show (their penalties are charges).
BILLABLE_STAY_STATUSES = ["tentative", "confirmed", "checked_in", "checked_out"]


def _user(actor):
    return actor if getattr(actor, "is_authenticated", False) else None


def get_or_create_folio(reservation, *, stay=None) -> Folio:
    """The reservation's guest folio (one per reservation, or per stay when `stay` is given)."""
    from apps.bookings.models import Reservation

    with transaction.atomic():
        Reservation.objects.select_for_update().filter(
            pk=reservation.pk
        ).first()  # serialize concurrent callers
        folio = (
            Folio.objects.filter(reservation=reservation, stay=stay, folio_type=Folio.FolioType.GUEST)
            .order_by("created_at")
            .first()
        )
        if folio is None:
            folio = Folio.objects.create(
                property=reservation.property,
                reservation=reservation,
                stay=stay,
                guest=reservation.booker,
                folio_type=Folio.FolioType.GUEST,
                currency=reservation.currency,
            )
    return folio


def post_charge(
    folio,
    *,
    kind,
    amount,
    description,
    quantity=1,
    tax=None,
    tax_exempt=False,
    stay=None,
    night_date=None,
    extra=None,
    actor=None,
    source="user",
    business_date=None,
) -> Charge:
    """Post a charge. `amount` is the NET unit price;
    `tax_amount = quantize(amount × quantity × tax.rate / 100)` unless `tax_exempt` (the tax stays
    referenced with 0, e.g. foreign non-resident lodging)."""
    if folio.status == Folio.Status.CLOSED:
        raise DomainError("El folio está cerrado", code="folio_closed")
    if kind not in Charge.Kind.values:
        raise DomainError(f"Tipo de cargo inválido: {kind}", code="invalid_kind")
    if int(quantity) < 1:
        raise DomainError("La cantidad debe ser al menos 1", code="invalid_quantity")
    currency = folio.currency
    unit_price = D(amount).quantize(CENTS, rounding=ROUND_HALF_UP)
    net = quantize(D(amount) * int(quantity), currency)
    tax_amount = quantize(net * D(tax.rate) / 100, currency) if tax is not None and not tax_exempt else ZERO
    return Charge.objects.create(
        folio=folio,
        business_date=business_date or folio.property.business_date,
        kind=kind,
        description=description[:255],
        quantity=int(quantity),
        unit_price=unit_price,
        amount=net,
        tax=tax,
        tax_amount=tax_amount,
        stay=stay,
        night_date=night_date,
        extra=extra,
        posted_by=_user(actor),
        source=source,
    )


def void_charge(charge, *, reason, actor, confirm) -> Charge:
    """Void a charge with a reason (requires `confirm=True`, else ConfirmationRequired). Implemented by B4."""
    raise NotImplementedError("finance.void_charge: B4 implementa esta función")


def record_payment(
    folio, *, amount, method, reference="", actor=None, status="approved", provider="manual", payload=None
) -> Payment:
    """Record a payment on the folio; an approved payment emits `payment_received` after commit."""
    amount = quantize(amount, folio.currency)
    if amount <= 0:
        raise DomainError("El monto debe ser mayor que cero", code="invalid_amount")
    if method not in Payment.Method.values:
        raise DomainError(f"Medio de pago inválido: {method}", code="invalid_method")
    if status not in Payment.Status.values:
        raise DomainError(f"Estado de pago inválido: {status}", code="invalid_status")
    payment = Payment.objects.create(
        folio=folio,
        amount=amount,
        method=method,
        status=status,
        provider=provider,
        provider_reference=reference or "",
        provider_payload=payload or {},
        business_date=folio.property.business_date,
        received_by=_user(actor),
    )
    if status == Payment.Status.APPROVED:
        signals.send_on_commit(signals.payment_received, payment=payment)
    return payment


def refund_payment(payment, *, amount, reason, actor, confirm) -> Refund:
    """Refund (part of) a payment (requires `confirm=True`). Implemented by B4."""
    raise NotImplementedError("finance.refund_payment: B4 implementa esta función")


def create_payment_intent(folio, *, amount, return_url, provider_kind="payments") -> PaymentIntent:
    """Create a PaymentIntent with the property's payments provider (real Wompi or simulated).
    Implemented by B4."""
    raise NotImplementedError("finance.create_payment_intent: B4 implementa esta función")


def sync_payment_intent(intent) -> PaymentIntent:
    """Actively verify an intent with its provider; on approval creates exactly one Payment.
    Implemented by B4."""
    raise NotImplementedError("finance.sync_payment_intent: B4 implementa esta función")


def folio_balance(folio) -> Decimal:
    charges = _sum(Charge.objects.filter(folio=folio, voided_at__isnull=True), F("amount") + F("tax_amount"))
    payments = _sum(Payment.objects.filter(folio=folio, status=Payment.Status.APPROVED), F("amount"))
    refunds = _sum(Refund.objects.filter(payment__folio=folio, status=Refund.Status.APPROVED), F("amount"))
    return charges - payments + refunds


def reservation_balance(reservation) -> Decimal:
    """What the reservation still owes across all its folios.

    Σ total_amount of billable stays (all but cancelled/no-show; stay totals include taxes) + non-room charges
    (with tax, not voided) − approved payments + approved refunds. Posted `room` charges consume the
    expected stay total and are never added twice.
    """
    stays = _sum(reservation.stays.filter(status__in=BILLABLE_STAY_STATUSES), F("total_amount"))
    other_charges = _sum(
        Charge.objects.filter(folio__reservation=reservation, voided_at__isnull=True).exclude(
            kind=Charge.Kind.ROOM
        ),
        F("amount") + F("tax_amount"),
    )
    payments = _sum(
        Payment.objects.filter(folio__reservation=reservation, status=Payment.Status.APPROVED), F("amount")
    )
    refunds = _sum(
        Refund.objects.filter(payment__folio__reservation=reservation, status=Refund.Status.APPROVED),
        F("amount"),
    )
    return stays + other_charges - payments + refunds


def _sum(queryset, expression) -> Decimal:
    return queryset.aggregate(total=Sum(expression))["total"] or ZERO
