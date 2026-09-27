"""Finance contracts (spec §4.2 + plan §C) and the services around them (B4).

Money rules:
- `Charge.amount` is NET; `tax_amount` goes apart; a charge's total = amount + tax_amount. Charges are never
  deleted: they are voided with a reason.
- Folio balance = Σ non-voided charges (amount + tax) − Σ approved payments + Σ approved refunds.
- Reservation balance = Σ total of billable stays + non-room charges − approved payments + approved refunds
  (room charges consume the expected stay total and are never counted twice).

Risky actions (void a charge or a payment, refund, complete a manual refund) require `confirm=True` and are
audited. Cash taken or given back requires the actor's open cash shift (`apps.finance.cash`) unless the
property sets `settings["require_cash_shift"] = False`.
"""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.core import alerts, audit, integrations, signals
from apps.core.codes import generate_code
from apps.core.dates import nights
from apps.core.errors import ConfirmationRequired, DomainError
from apps.core.i18n import t
from apps.core.money import D, quantize
from apps.finance.cash import current_cash_shift, money_str
from apps.finance.errors import (
    AlreadyVoidedError,
    CashShiftRequired,
    FolioClosedError,
    IntegrationMisconfigured,
    IntentClosed,
    OnlinePaymentsDisabled,
    PaymentNotRefundable,
    PaymentNotVoidable,
    ProviderError,
    RefundExceedsPayment,
    RefundNotPending,
    SimulationDisabled,
)
from apps.finance.models import Charge, Folio, Payment, PaymentIntent, Refund

ZERO = Decimal("0")
CENTS = Decimal("0.01")
# Stays whose total is owed: everything except cancelled / no-show (their penalties are charges).
BILLABLE_STAY_STATUSES = ["tentative", "confirmed", "checked_in", "checked_out"]
# Methods whose money leaves through a person, not through a provider API (refund = approved at once).
MANUAL_REFUND_INSTRUCTIONS = {
    Payment.Method.OTA_COLLECT: (
        "El pago lo cobró la OTA: procesa el reembolso en la extranet del canal y márcalo como hecho aquí."
    ),
}
PAYMENT_LINK_HOURS = 24  # default lifetime of a payment link (property.settings["payment_link_hours"])


def _user(actor):
    return actor if getattr(actor, "is_authenticated", False) else None


# --- Folios -------------------------------------------------------------------------------------------


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


# --- Charges ------------------------------------------------------------------------------------------


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
    referenced with 0, e.g. foreign non-resident lodging). Only `adjustment` charges may be negative
    (credits). Audited as `finance.charge_posted`."""
    _ensure_open(folio)
    if kind not in Charge.Kind.values:
        raise DomainError(f"Tipo de cargo inválido: {kind}", code="invalid_kind")
    if int(quantity) < 1:
        raise DomainError("La cantidad debe ser al menos 1", code="invalid_quantity")
    if D(amount) < 0 and kind != Charge.Kind.ADJUSTMENT:
        raise DomainError("Solo los ajustes pueden tener un valor negativo", code="invalid_amount")
    currency = folio.currency
    unit_price = D(amount).quantize(CENTS, rounding=ROUND_HALF_UP)
    net = quantize(D(amount) * int(quantity), currency)
    tax_amount = quantize(net * D(tax.rate) / 100, currency) if tax is not None and not tax_exempt else ZERO
    with transaction.atomic():  # the charge and its audit event, or nothing
        charge = Charge.objects.create(
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
        audit.record(
            action="finance.charge_posted",
            target=charge,
            summary=f"Cargo «{charge.description}» por {_money(charge.total, currency)}",
            actor=actor,
            source=source,
            property=folio.property,
            changes={
                "kind": kind,
                "quantity": charge.quantity,
                "amount": money_str(charge.amount),
                "tax_amount": money_str(tax_amount),
            },
        )
    return charge


def void_charge(charge, *, reason, actor, confirm) -> Charge:
    """Void a charge with a reason. Risky money action: requires `confirm=True` (else ConfirmationRequired).
    Charges are never deleted; the voided one stops counting in every balance."""
    if confirm is not True:
        raise ConfirmationRequired("Confirma la anulación del cargo")
    reason = _required_reason(reason)
    with transaction.atomic():
        charge = Charge.objects.select_for_update().select_related("folio__property").get(pk=charge.pk)
        _ensure_open(charge.folio)
        if charge.voided_at is not None:
            raise AlreadyVoidedError("Este cargo ya fue anulado")
        charge.voided_at = timezone.now()
        charge.voided_by = _user(actor)
        charge.void_reason = reason
        charge.save(update_fields=["voided_at", "voided_by", "void_reason", "updated_at"])
        audit.record(
            action="finance.charge_voided",
            target=charge,
            summary=f"Anuló el cargo «{charge.description}» ({_money(charge.total, charge.folio.currency)})",
            actor=actor,
            property=charge.folio.property,
            changes={
                "reason": reason,
                "amount": money_str(charge.amount),
                "tax_amount": money_str(charge.tax_amount),
            },
        )
    return charge


def guest_of(folio):
    """The folio's guest (or the reservation booker)."""
    if folio.guest_id:
        return folio.guest
    return folio.reservation.booker if folio.reservation_id else None


def is_tax_exempt(folio, tax) -> bool:
    """Taxes flagged `exempt_foreign_non_residents` are 0 for foreign non-resident guests (ET art. 481)."""
    if tax is None or not tax.exempt_foreign_non_residents:
        return False
    guest = guest_of(folio)
    return bool(guest and guest.is_foreign_non_resident)


def extra_default_quantity(extra, folio) -> int:
    """Units of an extra for the folio's reservation: per stay 1, per night N, per person P, per person-night
    P × N (P = adults + children; without a reservation everything counts as 1)."""
    reservation = folio.reservation if folio.reservation_id else None
    stay_nights = (
        max(1, len(nights(reservation.checkin_date, reservation.checkout_date))) if reservation else 1
    )
    persons = max(1, reservation.adults + reservation.children) if reservation else 1
    return {
        "per_stay": 1,
        "per_night": stay_nights,
        "per_person": persons,
        "per_person_night": persons * stay_nights,
    }.get(extra.charge_type, 1)


def extra_unit_net(extra, tax) -> Decimal:
    """Net unit price of an extra (prices with the tax included are split: price / (1 + rate))."""
    price = D(extra.price)
    if tax is not None and tax.included_in_price:
        return (price / (1 + D(tax.rate) / 100)).quantize(CENTS, rounding=ROUND_HALF_UP)
    return price


def post_extra_charge(folio, extra, *, quantity=None, actor=None, source="user") -> Charge:
    """Post an extra (desayuno, parqueadero…) with its tax, exemption and default quantity."""
    tax = extra.tax if extra.tax_id and extra.tax.is_active else None
    return post_charge(
        folio,
        kind=Charge.Kind.EXTRA,
        amount=extra_unit_net(extra, tax),
        description=t(extra.name, folio.property.default_language) or extra.code,
        quantity=int(quantity) if quantity is not None else extra_default_quantity(extra, folio),
        tax=tax,
        tax_exempt=is_tax_exempt(folio, tax),
        extra=extra,
        actor=actor,
        source=source,
    )


# --- Payments -----------------------------------------------------------------------------------------


def record_payment(
    folio, *, amount, method, reference="", actor=None, status="approved", provider="manual", payload=None
) -> Payment:
    """Record a payment on the folio; an approved payment emits `payment_received` after commit.

    Cash needs the actor's open cash shift (`cash_shift_required`, 409) unless the property turned the rule
    off; any payment taken by a user with an open shift is linked to it. System payments (no actor) skip it.
    """
    amount = quantize(amount, folio.currency)
    if amount <= 0:
        raise DomainError("El monto debe ser mayor que cero", code="invalid_amount")
    if method not in Payment.Method.values:
        raise DomainError(f"Medio de pago inválido: {method}", code="invalid_method")
    if status not in Payment.Status.values:
        raise DomainError(f"Estado de pago inválido: {status}", code="invalid_status")
    _ensure_open(folio)
    shift = _cash_shift_for(folio.property, actor, cash=method == Payment.Method.CASH)
    with transaction.atomic():  # the payment and its audit event, or nothing
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
            cash_shift=shift,
        )
        audit.record(
            action="finance.payment_recorded",
            target=payment,
            summary=f"Pago ({payment.get_method_display()}) por {_money(amount, folio.currency)}",
            actor=actor,
            source="user" if _user(actor) else "system",
            property=folio.property,
            changes={"amount": money_str(amount), "method": method, "status": status, "provider": provider},
        )
        if status == Payment.Status.APPROVED:
            signals.send_on_commit(signals.payment_received, payment=payment)
    return payment


def void_payment(payment, *, reason, actor, confirm) -> Payment:
    """Void a MANUAL payment recorded by mistake (money never received). Online payments are refunded."""
    if confirm is not True:
        raise ConfirmationRequired("Confirma la anulación del pago")
    reason = _required_reason(reason)
    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related("folio__property").get(pk=payment.pk)
        if payment.provider != "manual" or payment.intent_id is not None:
            raise PaymentNotVoidable("Los pagos en línea no se anulan: se reembolsan")
        if payment.status != Payment.Status.APPROVED:
            raise PaymentNotVoidable("Solo se pueden anular pagos aprobados")
        if payment.refunds.exclude(status=Refund.Status.FAILED).exists():
            raise PaymentNotVoidable("El pago tiene reembolsos; no se puede anular")
        _ensure_open(payment.folio)
        payment.status = Payment.Status.VOIDED
        payment.voided_at = timezone.now()
        payment.voided_by = _user(actor)
        payment.void_reason = reason
        payment.save(update_fields=["status", "voided_at", "voided_by", "void_reason", "updated_at"])
        audit.record(
            action="finance.payment_voided",
            target=payment,
            summary=f"Anuló un pago de {_money(payment.amount, payment.folio.currency)}",
            actor=actor,
            property=payment.folio.property,
            changes={"reason": reason, "amount": money_str(payment.amount), "method": payment.method},
        )
    return payment


# --- Refunds ------------------------------------------------------------------------------------------


def refundable_amount(payment) -> Decimal:
    """What can still be refunded: the payment minus approved and pending refunds."""
    refunded = _sum(payment.refunds.exclude(status=Refund.Status.FAILED), F("amount"))
    return payment.amount - refunded


def refund_payment(payment, *, amount, reason, actor, confirm) -> Refund:
    """Refund (part of) an approved payment. Requires `confirm=True`; amount ≤ what is left to refund.

    Manual methods are approved at once (cash comes out of the actor's shift); OTA-collected money and
    online methods without an API refund stay `pending` with instructions and an alert until someone
    completes them (`complete_refund`).
    """
    if confirm is not True:
        raise ConfirmationRequired("Confirma el reembolso")
    reason = _required_reason(reason)
    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related("folio__property").get(pk=payment.pk)
        folio, prop = payment.folio, payment.folio.property
        amount = quantize(amount, folio.currency)
        if amount <= 0:
            raise DomainError("El monto debe ser mayor que cero", code="invalid_amount")
        _ensure_open(folio)  # closed = settled and read-only; a refund would leave it closed with money owed
        if payment.status != Payment.Status.APPROVED:
            raise PaymentNotRefundable("Solo se pueden reembolsar pagos aprobados")
        refundable = refundable_amount(payment)
        if amount > refundable:
            raise RefundExceedsPayment(
                f"Solo quedan {_money(refundable, folio.currency)} por reembolsar de este pago",
                refundable=refundable,
            )
        # Refunds of desk payments (cash, card terminal, transfer…) are movements of the actor's shift; only
        # cash ones change the expected cash. Online refunds happen at the provider, not at the desk.
        shift = _cash_shift_for(
            prop, actor, cash=payment.method == Payment.Method.CASH, link=payment.provider == "manual"
        )
        refund = Refund.objects.create(
            payment=payment,
            amount=amount,
            status=Refund.Status.PENDING,
            reason=reason,
            requested_by=_user(actor),
            business_date=prop.business_date,
            cash_shift=shift,
        )
        outcome = _execute_refund(payment, refund)
        refund.status = outcome["status"]
        refund.provider_reference = outcome.get("provider_reference", "") or ""
        refund.provider_payload = {**(outcome.get("payload") or {}), **_error_of(outcome)}
        refund.instructions = outcome.get("instructions", "") or ""
        if refund.status != Refund.Status.PENDING:
            refund.completed_at = timezone.now()
        if refund.status == Refund.Status.APPROVED:
            refund.approved_by = _user(actor)
        refund.save()
        audit.record(
            action="finance.payment_refunded",
            target=refund,
            summary=f"Reembolso de {_money(amount, folio.currency)} ({refund.get_status_display().lower()})",
            actor=actor,
            property=prop,
            changes={
                "amount": money_str(amount),
                "payment_id": str(payment.pk),
                "method": payment.method,
                "status": refund.status,
                "reason": reason,
            },
        )
        if refund.status == Refund.Status.PENDING:
            _alert_refund(
                refund,
                kind="refund_pending",
                severity="warning",
                title=f"Reembolso pendiente de {_money(amount, folio.currency)}",
                message=refund.instructions,
            )
        elif refund.status == Refund.Status.FAILED:
            _alert_refund(
                refund,
                kind="refund_failed",
                severity="critical",
                title=f"Falló un reembolso de {_money(amount, folio.currency)}",
                message=outcome.get("message") or refund.reason,
            )
    return refund


def complete_refund(refund, *, actor, confirm, outcome="approved", reference="") -> Refund:
    """Mark a `pending` refund as done (`approved`) or `failed` after the manual step."""
    if confirm is not True:
        raise ConfirmationRequired("Confirma que el reembolso se completó")
    if outcome not in (Refund.Status.APPROVED, Refund.Status.FAILED):
        raise DomainError("Resultado inválido", code="invalid_outcome")
    with transaction.atomic():
        refund = (
            Refund.objects.select_for_update().select_related("payment__folio__property").get(pk=refund.pk)
        )
        if refund.status != Refund.Status.PENDING:
            raise RefundNotPending("Este reembolso no está pendiente")
        refund.status = outcome
        refund.provider_reference = (reference or "").strip() or refund.provider_reference
        refund.completed_at = timezone.now()
        if outcome == Refund.Status.APPROVED:
            refund.approved_by = _user(actor)
        refund.save()
        prop = refund.payment.folio.property
        audit.record(
            action="finance.refund_completed",
            target=refund,
            summary=f"Reembolso de {_money(refund.amount, refund.payment.folio.currency)}: {outcome}",
            actor=actor,
            property=prop,
            changes={"status": outcome, "provider_reference": refund.provider_reference},
        )
        alerts.resolve_alert(prop, f"refund:{refund.pk}", actor=_user(actor))
    return refund


def _execute_refund(payment, refund) -> dict:
    """Give the money back. Payments of a registered online provider go through it (simulated → approved,
    Wompi card → API void, other Wompi methods → pending manual transfer); the rest are manual."""
    provider = _provider_for_payment(payment)
    if provider is not None:
        return provider.refund(payment, refund.amount)
    instructions = MANUAL_REFUND_INSTRUCTIONS.get(payment.method)
    if instructions:
        return {"status": Refund.Status.PENDING, "instructions": instructions}
    return {"status": Refund.Status.APPROVED}


def _error_of(outcome: dict) -> dict:
    return (
        {"error": outcome["message"]} if outcome.get("status") == "failed" and outcome.get("message") else {}
    )


def _alert_refund(refund, *, kind, severity, title, message) -> None:
    folio = refund.payment.folio
    reservation_id = folio.reservation_id
    alerts.raise_alert(
        property=folio.property,
        kind=kind,
        severity=severity,
        title=title,
        message=message or refund.reason,
        link=f"/app/reservations/{reservation_id}" if reservation_id else "/app/cashier",
        dedupe_key=f"refund:{refund.pk}",
        data={"refund_id": str(refund.pk), "payment_id": str(refund.payment_id)},
        source="finance",
    )


# --- Payment intents (online payments) ---------------------------------------------------------------


def create_payment_intent(folio, *, amount, return_url, provider_kind="payments") -> PaymentIntent:
    """Create a payment link with the property's payments provider (real Wompi or simulated).

    The link lives `property.settings["payment_link_hours"]` (24 h by default), and never longer than the hold
    of a tentative reservation (after it the booking is released). `return_url` is where the gateway sends the
    guest back; `payment_ref=<reference>` is appended (`providers.redirect_url_for`). Nothing is persisted if
    the provider cannot build the checkout (e.g. Wompi keys missing).
    """
    amount = quantize(amount, folio.currency)
    if amount <= 0:
        raise DomainError("El monto debe ser mayor que cero", code="invalid_amount")
    _ensure_open(folio)
    prop = folio.property
    setting = integrations.get_setting(prop, provider_kind)
    if not setting.enabled:
        raise OnlinePaymentsDisabled("Los pagos en línea están desactivados para este hotel")
    provider = integrations.get_provider(prop, provider_kind)
    now = timezone.now()
    hours = int((prop.settings or {}).get("payment_link_hours", PAYMENT_LINK_HOURS))
    expires_at = now + timedelta(hours=hours)
    reservation = folio.reservation if folio.reservation_id else None
    hold = reservation.hold_expires_at if reservation and reservation.status == "tentative" else None
    if hold and now < hold < expires_at:
        expires_at = hold
    with transaction.atomic():
        intent = PaymentIntent.objects.create(
            property=prop,
            folio=folio,
            amount=amount,
            currency=folio.currency,
            provider=provider.code or provider.mode,
            mode=provider.mode,
            reference=_new_reference(folio),
            status=PaymentIntent.Status.CREATED,
            expires_at=expires_at,
            return_url=return_url or "",
        )
        intent.checkout_url = provider.create_checkout(intent)["checkout_url"]
        intent.save(update_fields=["checkout_url", "updated_at"])
        audit.record(
            action="finance.payment_intent_created",
            target=intent,
            summary=f"Link de pago {intent.reference} por {_money(amount, folio.currency)}: {provider.label}",
            source="system",
            property=prop,
            changes={"amount": money_str(amount), "provider": intent.provider, "mode": intent.mode},
        )
    return intent


def sync_payment_intent(intent) -> PaymentIntent:
    """Actively verify an intent with the provider that created it (by its mode) and apply the result.

    Idempotent: the intent row is locked and a Payment is created only once (`Payment.intent` is unique),
    then `record_payment` emits `payment_received`. Declined links can still be paid on a retry; money
    reported after expiry is recorded too. Provider failures leave the intent as it was (with the error in
    `status_message`).
    """
    fresh = PaymentIntent.objects.select_related("property", "folio__reservation").get(pk=intent.pk)
    result, error = None, ""
    try:
        result = provider_for_intent(fresh).fetch_status(fresh)
    except (ProviderError, IntegrationMisconfigured) as exc:
        error = getattr(exc, "message", None) or str(exc)
    with transaction.atomic():
        locked = (
            PaymentIntent.objects.select_for_update().select_related("property", "folio").get(pk=intent.pk)
        )
        locked.last_checked_at = timezone.now()
        if result is None:
            locked.status_message = error[:255]
            locked.save(update_fields=["last_checked_at", "status_message", "updated_at"])
            return locked
        _apply_provider_status(locked, result)
    return locked


def _apply_provider_status(intent, result: dict) -> None:
    status = result.get("status") or "created"
    previous = intent.status
    if result.get("provider_reference"):
        intent.provider_transaction_id = str(result["provider_reference"])[:120]
    if result.get("method"):
        intent.method = result["method"]
    intent.status_message = str(result.get("message") or "")[:255]
    if status == "approved":
        _record_intent_payment(intent, result)
        intent.status = PaymentIntent.Status.APPROVED
    elif status == "voided":
        _void_intent_payment(intent)
    elif status in ("declined", "error") and previous != PaymentIntent.Status.APPROVED:
        intent.status = status
    elif status == "pending" and previous in ("created", "declined", "error"):
        intent.status = PaymentIntent.Status.PENDING
    elif status == "expired" and previous in ("created", "pending", "declined", "error"):
        intent.status = PaymentIntent.Status.EXPIRED
    intent.save()
    if intent.status != previous:
        audit.record(
            action="finance.payment_intent_updated",
            target=intent,
            summary=f"Link de pago {intent.reference}: {previous} → {intent.status}",
            source="system",
            property=intent.property,
            changes={"status": [previous, intent.status]},
        )


def _record_intent_payment(intent, result: dict) -> None:
    if Payment.objects.filter(intent=intent).exists():
        return
    folio = Folio.objects.select_for_update().select_related("property").get(pk=intent.folio_id)
    if folio.status == Folio.Status.CLOSED:
        folio.status, folio.closed_at = Folio.Status.OPEN, None
        folio.save(update_fields=["status", "closed_at", "updated_at"])
        audit.record(
            action="finance.folio_reopened",
            target=folio,
            source="system",
            property=folio.property,
            summary=f"Folio reabierto: llegó el pago del link {intent.reference}",
        )
        _alert_intent(
            intent,
            "payment_on_closed_folio",
            "Llegó un pago a un folio cerrado",
            "El folio se reabrió para registrarlo. Revisa si hay que reembolsar un excedente.",
        )
    amount = quantize(result.get("amount") or intent.amount, intent.currency)
    payment = record_payment(
        folio,
        amount=amount,
        method=result.get("method") or Payment.Method.WOMPI_OTHER,
        reference=str(result.get("provider_reference") or intent.reference),
        status=Payment.Status.APPROVED,
        provider=intent.provider,
        payload=result.get("payload") or {},
    )
    payment.intent = intent
    payment.save(update_fields=["intent", "updated_at"])
    if amount != intent.amount:
        _alert_intent(
            intent,
            "payment_amount_mismatch",
            "El monto pagado no coincide con el link",
            f"Se esperaban {_money(intent.amount, intent.currency)} y se pagaron "
            f"{_money(amount, intent.currency)}.",
        )


def _void_intent_payment(intent) -> None:
    payment = Payment.objects.select_for_update().filter(intent=intent).first()
    if payment is None or payment.status != Payment.Status.APPROVED:
        return
    if payment.refunds.exclude(status=Refund.Status.FAILED).exists():
        return  # our own refund (card void) explains it: the refund already gives the money back
    payment.status = Payment.Status.VOIDED
    payment.voided_at = timezone.now()
    payment.void_reason = "Anulado en el proveedor de pagos"
    payment.save(update_fields=["status", "voided_at", "void_reason", "updated_at"])
    audit.record(
        action="finance.payment_voided",
        target=payment,
        source="system",
        property=intent.property,
        summary=f"El proveedor anuló el pago del link {intent.reference}",
        changes={"reason": payment.void_reason},
    )
    _alert_intent(
        intent,
        "payment_voided_by_provider",
        "Un pago en línea fue anulado en el proveedor",
        f"El pago del link {intent.reference} ya no cuenta en el saldo.",
    )


def _alert_intent(intent, kind: str, title: str, message: str) -> None:
    reservation_id = intent.folio.reservation_id
    alerts.raise_alert(
        property=intent.property,
        kind=kind,
        severity="warning",
        title=title,
        message=message,
        link=f"/app/reservations/{reservation_id}" if reservation_id else "/app/cashier",
        dedupe_key=f"intent:{intent.reference}:{kind}",
        data={"intent_id": str(intent.pk), "reference": intent.reference},
        source="finance",
    )


def _provider_class(*, mode=None, code=None):
    registered = integrations.providers_for("payments")
    if mode is not None:
        return registered.get(mode)
    return next((cls for cls in registered.values() if getattr(cls, "code", "") == code), None)


def provider_for_intent(intent):
    """The provider of the mode the intent was created with (property settings may have changed since)."""
    cls = _provider_class(mode=intent.mode)
    if cls is None:
        raise integrations.IntegrationNotAvailable(f"No hay proveedor de pagos «{intent.mode}»")
    return cls(integrations.get_setting(intent.property, "payments"))


def _provider_for_payment(payment):
    """The registered online provider that took the payment, or None for manual/other providers."""
    cls = _provider_class(code=payment.provider) if payment.provider != "manual" else None
    return cls(integrations.get_setting(payment.folio.property, "payments")) if cls else None


def _new_reference(folio) -> str:
    base = folio.reservation.code if folio.reservation_id else f"F-{folio.pk.hex[:6].upper()}"
    for _ in range(10):
        reference = f"{base}-{generate_code('', 6)}"
        if not PaymentIntent.objects.filter(reference=reference).exists():
            return reference
    raise DomainError("No se pudo generar la referencia del pago", code="reference_unavailable")


SIMULATED_METHODS = {
    "card": Payment.Method.WOMPI_CARD,
    "pse": Payment.Method.WOMPI_PSE,
    "nequi": Payment.Method.WOMPI_NEQUI,
}
OPEN_INTENT_STATUSES = ("created", "pending")


def intent_is_stale(intent, now=None) -> bool:
    """An unpaid link past its deadline (or older than 24 h without one)."""
    now = now or timezone.now()
    if intent.status not in OPEN_INTENT_STATUSES:
        return False
    if intent.expires_at:
        return intent.expires_at <= now
    return intent.created_at <= now - timedelta(hours=24)


def simulated_payments_enabled(property) -> bool:
    """The simulated gateway only works while the hotel's payments integration is in simulated mode: once it
    takes real payments (Wompi), an old simulated link must not record money that never moved."""
    return integrations.get_setting(property, "payments").mode == PaymentIntent.Mode.SIMULATED


def decide_simulated_intent(intent, *, outcome, method) -> PaymentIntent:
    """The guest's decision on the simulated gateway (`approved | declined | expired`, `card | pse | nequi`).

    Works like a provider webhook: the decision is stored and the intent is verified with
    `sync_payment_intent`. A paid link accepts the same approval again (idempotent); paid or expired links
    reject other decisions (`intent_closed`); declined links can be retried. A hotel in real mode rejects
    every decision (`simulation_disabled`).
    """
    if not simulated_payments_enabled(intent.property):
        raise SimulationDisabled("Este hotel ya cobra pagos reales: el link simulado no se puede usar")
    with transaction.atomic():
        locked = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
        if intent_is_stale(locked):
            locked.status = PaymentIntent.Status.EXPIRED
            locked.save(update_fields=["status", "updated_at"])
            audit.record(
                action="finance.payment_intent_updated",
                target=locked,
                source="guest",
                property=locked.property,
                summary=f"Link de pago {locked.reference} vencido",
                changes={"status": ["created", "expired"]},
            )
    locked.refresh_from_db()
    if locked.status == PaymentIntent.Status.APPROVED and outcome == "approved":
        return locked
    if locked.status in (PaymentIntent.Status.APPROVED, PaymentIntent.Status.EXPIRED):
        raise IntentClosed("Este link de pago ya no se puede usar")
    with transaction.atomic():
        locked = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
        locked.payload = {
            **(locked.payload or {}),
            "simulation": {
                "outcome": outcome,
                "method": SIMULATED_METHODS[method],
                "transaction_id": f"SIM-{generate_code('', 10)}",
                "decided_at": timezone.now().isoformat(),
            },
        }
        locked.save(update_fields=["payload", "updated_at"])
    return sync_payment_intent(locked)


def sync_open_intents(property, *, now=None) -> dict:
    """Automation `finance.sync_pending_intents`: verify every `created`/`pending` link of the property and
    expire the ones past `expires_at` (or older than 24 h without one) that are still unpaid."""
    now = now or timezone.now()
    report = {"checked": 0, "approved": 0, "expired": 0}
    open_statuses = [PaymentIntent.Status.CREATED, PaymentIntent.Status.PENDING]
    for intent in PaymentIntent.objects.filter(property=property, status__in=open_statuses).order_by(
        "created_at"
    ):
        report["checked"] += 1
        synced = sync_payment_intent(intent)
        if synced.status == PaymentIntent.Status.APPROVED:
            report["approved"] += 1
            continue
        if intent_is_stale(synced, now):
            PaymentIntent.objects.filter(pk=synced.pk, status__in=open_statuses).update(
                status=PaymentIntent.Status.EXPIRED, updated_at=now
            )
            audit.record(
                action="finance.payment_intent_updated",
                target=synced,
                source="automation",
                property=property,
                summary=f"Link de pago {synced.reference} vencido",
                changes={"status": [synced.status, PaymentIntent.Status.EXPIRED]},
            )
            report["expired"] += 1
    return report


# --- Folio closing ------------------------------------------------------------------------------------

DEPARTED_STAY_STATUSES = {"checked_out", "cancelled", "no_show"}


def close_settled_folios(reservation) -> list[Folio]:
    """Close every open folio of the reservation when all its stays left (at least one checked out), the
    reservation balance is exactly 0 and no refund is still on its way (`pending`). Emits `folio_closed`
    per folio after commit."""
    statuses = set(reservation.stays.values_list("status", flat=True))
    if "checked_out" not in statuses or not statuses <= DEPARTED_STAY_STATUSES:
        return []
    if reservation_balance(reservation) != 0:
        return []
    if Refund.objects.filter(payment__folio__reservation=reservation, status=Refund.Status.PENDING).exists():
        return []
    closed = []
    with transaction.atomic():
        for folio in Folio.objects.select_for_update().filter(
            reservation=reservation, status=Folio.Status.OPEN
        ):
            folio.status = Folio.Status.CLOSED
            folio.closed_at = timezone.now()
            folio.save(update_fields=["status", "closed_at", "updated_at"])
            audit.record(
                action="finance.folio_closed",
                target=folio,
                source="system",
                property=folio.property,
                summary=f"Folio de la reserva {reservation.code} cerrado con saldo 0",
            )
            signals.send_on_commit(signals.folio_closed, folio=folio)
            closed.append(folio)
    return closed


# --- Balances -----------------------------------------------------------------------------------------


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


# --- Helpers ------------------------------------------------------------------------------------------


def _sum(queryset, expression) -> Decimal:
    return queryset.aggregate(total=Sum(expression))["total"] or ZERO


def _ensure_open(folio) -> None:
    if folio.status == Folio.Status.CLOSED:
        raise FolioClosedError("El folio está cerrado")


def _required_reason(reason) -> str:
    reason = (reason or "").strip()
    if not reason:
        raise DomainError("Indica el motivo", code="reason_required")
    return reason


def _cash_shift_for(prop, actor, *, cash: bool, link: bool = True):
    """The actor's open shift. Cash needs one (unless the property turned the rule off); other manual
    movements are linked to it when it exists (`link`)."""
    user = _user(actor)
    if user is None:
        return None
    shift = current_cash_shift(prop, user)
    if cash and shift is None and (prop.settings or {}).get("require_cash_shift", True):
        raise CashShiftRequired("Abre tu turno de caja para recibir o devolver efectivo")
    return shift if (cash or link) else None


def _money(amount, currency="COP") -> str:
    """`$ 350.000` style amount for audit summaries and messages (COP without decimals)."""
    value = quantize(amount, currency)
    digits = f"{abs(value):,.0f}" if currency == "COP" else f"{abs(value):,.2f}"
    digits = digits.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if value < 0 else ''}$ {digits}"
