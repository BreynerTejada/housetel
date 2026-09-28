"""Subscriptions and platform billing (spec §5 C11, plan C11).

Lifecycle of a subscription:

- Signup → `trialing` for 14 days (organization `trial`).
- Trial ends → the first period starts and its invoice is issued: with a payment method on file it is charged
  (→ `active`); without one, or if the charge fails → `past_due` (organization `past_due`).
- Every renewal date (`current_period_end`) → invoice for the next period (plan + IVA 19 %) → charge →
  `active` and the period advances; a failed charge → `past_due`.
- `past_due` → automatic retries 1, 3 and 7 days after the first failure; when the last one fails →
  `suspended` (organization `suspended`: the staff API answers 402 except accounts and billing).
- Paying every open invoice (retry, the hotel's "Pay" button or the admin's "mark as paid") → `active` again.

Charges go through the `saas_billing` integration (platform scope, `property=None`): simulated approves unless
`organization.settings["simulate_payment_failure"]`; real = Wompi with the platform credentials.
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.core.mail import send_mail
from django.db import connection, transaction
from django.utils import timezone

from apps.core import audit, integrations
from apps.core.alerts import raise_alert, resolve_alert
from apps.core.errors import ConflictError, DomainError
from apps.core.i18n import t
from apps.core.integrations import get_provider, get_setting
from apps.core.models import Organization
from apps.core.money import ZERO, quantize
from apps.core.runtime import public_base_url
from apps.finance.errors import ProviderError
from apps.saas.models import CommissionSettlement, Plan, PlatformInvoice, Subscription
from apps.saas.services.plans import plan_fits, plan_for_units

logger = logging.getLogger("housetel.saas")

TRIAL_DAYS = 14
TAX_RATE = Decimal("19.00")
DUE_DAYS = 5
RETRY_SCHEDULE_DAYS = (1, 3, 7)  # days after the first failed charge; the last failure suspends
UNPAID = (PlatformInvoice.Status.OPEN, PlatformInvoice.Status.FAILED)
INVOICE_LOCK_KEY = 7_311_011  # pg_advisory_xact_lock key for invoice numbering
MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]  # fmt: skip
MONTHS_EN = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]  # fmt: skip


class BillingError(DomainError):
    code = "billing_error"


# ---- Helpers --------------------------------------------------------------------------------------


def today() -> date:
    return timezone.localdate()


def add_cycle(start: date, cycle: str) -> date:
    return start + (relativedelta(years=1) if cycle == Subscription.Cycle.YEARLY else relativedelta(months=1))


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """First and last day (inclusive) of a month."""
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def month_label(day: date) -> dict:
    return {"es": f"{MONTHS_ES[day.month - 1]} {day.year}", "en": f"{MONTHS_EN[day.month - 1]} {day.year}"}


def money(value) -> str:
    """Money for JSON: string with 2 decimals, rounded to the currency unit ("349000.00")."""
    return f"{quantize(value or ZERO):.2f}"


def _fmt(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def get_subscription(organization) -> Subscription | None:
    return (
        Subscription.objects.select_related("plan", "organization").filter(organization=organization).first()
    )


def _set_org_status(org: Organization, status: str) -> None:
    if org.status != status:
        org.status = status
        org.save(update_fields=["status", "updated_at"])


# ---- Usage and plan limits ------------------------------------------------------------------------


def units_by_organization(org_ids=None) -> dict:
    """Sellable units per organization id: active rooms of active private categories + active beds of active
    rooms of active dorm categories, in active properties (same definition as the inventory)."""
    from django.db.models import Count

    from apps.inventory.models import Bed, Room

    rooms = Room.objects.filter(
        is_active=True, room_type__is_active=True, room_type__kind="private", property__status="active"
    )
    beds = Bed.objects.filter(
        is_active=True,
        room__is_active=True,
        room__room_type__is_active=True,
        room__room_type__kind="dorm",
        room__property__status="active",
    )
    if org_ids is not None:
        rooms = rooms.filter(property__organization_id__in=org_ids)
        beds = beds.filter(room__property__organization_id__in=org_ids)
    result: dict = {}
    for row in rooms.values("property__organization_id").annotate(n=Count("id")):
        result[row["property__organization_id"]] = row["n"]
    for row in beds.values("room__property__organization_id").annotate(n=Count("id")):
        key = row["room__property__organization_id"]
        result[key] = result.get(key, 0) + row["n"]
    return result


def usage(org: Organization, sub: Subscription | None = None) -> dict:
    sub = sub or get_subscription(org)
    units = units_by_organization([org.pk]).get(org.pk, 0)
    properties = org.properties.filter(status="active").count()
    plan = sub.plan if sub else None
    max_units = plan.max_units if plan else None
    max_properties = plan.max_properties if plan else None
    return {
        "units": units,
        "properties": properties,
        "max_units": max_units,
        "max_properties": max_properties,
        "units_percent": round(units * 100 / max_units) if max_units else None,
        "over_limit": bool(plan) and not plan_fits(plan, units=units, properties=properties),
    }


def _count(n: int, one: str, other: str) -> str:
    return f"{n} {one if n == 1 else other}"


def _limit(n: int | None, one: str, other: str) -> str:
    return f"{other} ilimitadas" if n is None else _count(n, one, other)


def check_plan_limit(org: Organization) -> bool:
    """Soft limit: raise (or resolve) the `plan_limit` alert on every active property. Returns over_limit."""
    sub = get_subscription(org)
    if sub is None:
        return False
    info = usage(org, sub)
    for prop in org.properties.filter(status="active"):
        if info["over_limit"]:
            raise_alert(
                property=prop,
                kind="plan_limit",
                severity="warning",
                title=f"Superaste el límite del plan {t(sub.plan.name)}",
                message=(
                    f"Tienes {_count(info['units'], 'unidad', 'unidades')} y "
                    f"{_count(info['properties'], 'propiedad', 'propiedades')}; el plan incluye "
                    f"{_limit(info['max_units'], 'unidad', 'unidades')} y "
                    f"{_limit(info['max_properties'], 'propiedad', 'propiedades')}. "
                    "Todo sigue funcionando: cambia de plan cuando quieras."
                ),
                link="/app/settings/billing",
                dedupe_key="saas:plan_limit",
                data={
                    "units": info["units"],
                    "max_units": info["max_units"],
                    "plan": sub.plan.code,
                    # P-INT: what the translated text needs (control:alertText.plan_limit)
                    "plan_name": sub.plan.name or {},
                    "properties": info["properties"],
                    "max_properties": info["max_properties"],
                },
                source="saas",
            )
        else:
            resolve_alert(prop, "saas:plan_limit")
    return info["over_limit"]


# ---- Invoices -------------------------------------------------------------------------------------


def next_invoice_number(year: int) -> str:
    """`HTP-<year>-<5 digits>`, sequential. Must run inside a transaction (advisory lock)."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [INVOICE_LOCK_KEY])
    prefix = f"HTP-{year}-"
    last = (
        PlatformInvoice.objects.filter(number__startswith=prefix)
        .order_by("-number")
        .values_list("number", flat=True)
        .first()
    )
    seq = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{seq:05d}"


def plan_line(plan: Plan, cycle: str, period_start: date, period_end_inclusive: date) -> dict:
    price = plan.price_for(cycle)
    cycle_es = "anual" if cycle == Subscription.Cycle.YEARLY else "mensual"
    cycle_en = "yearly" if cycle == Subscription.Cycle.YEARLY else "monthly"
    period = f"{_fmt(period_start)} – {_fmt(period_end_inclusive)}"
    return {
        "kind": "plan",
        "description": {
            "es": f"Plan {t(plan.name, 'es')} ({cycle_es}) · {period}",
            "en": f"{t(plan.name, 'en')} plan ({cycle_en}) · {period}",
        },
        "quantity": 1,
        "unit_price": money(price),
        "amount": money(price),
        "plan_code": plan.code,
    }


def create_invoice(
    org: Organization,
    *,
    kind: str,
    period_start: date,
    period_end: date,
    lines: list[dict],
    issued_at=None,
    due_date: date | None = None,
    actor=None,
    source: str = "automation",
) -> PlatformInvoice:
    subtotal = quantize(sum((Decimal(line["amount"]) for line in lines), ZERO))
    tax = quantize(subtotal * TAX_RATE / 100)
    issued_at = issued_at or timezone.now()
    with transaction.atomic():
        invoice = PlatformInvoice.objects.create(
            organization=org,
            number=next_invoice_number(timezone.localtime(issued_at).year),
            kind=kind,
            period_start=period_start,
            period_end=period_end,
            lines=lines,
            subtotal=subtotal,
            tax_rate=TAX_RATE,
            tax=tax,
            total=subtotal + tax,
            issued_at=issued_at,
            due_date=due_date or (timezone.localtime(issued_at).date() + timedelta(days=DUE_DAYS)),
        )
        audit.record(
            action="saas.invoice_issued",
            target=invoice,
            organization=org,
            actor=actor,
            source=source,
            summary=f"Factura de plataforma {invoice.number} por {invoice.total}",
            changes={"total": str(invoice.total), "kind": kind},
        )
    return invoice


def create_period_invoice(sub: Subscription, period_start: date, *, actor=None, source="automation"):
    period_end = add_cycle(period_start, sub.billing_cycle)
    return create_invoice(
        sub.organization,
        kind=PlatformInvoice.Kind.SUBSCRIPTION,
        period_start=period_start,
        period_end=period_end - timedelta(days=1),
        lines=[plan_line(sub.plan, sub.billing_cycle, period_start, period_end - timedelta(days=1))],
        actor=actor,
        source=source,
    )


def upcoming_invoice(sub: Subscription) -> dict | None:
    """Preview of the next subscription charge (no commissions: those are settled monthly)."""
    if sub.status == Subscription.Status.CANCELLED or sub.cancel_at_period_end:
        return None
    if sub.status == Subscription.Status.TRIALING:
        start = timezone.localtime(sub.trial_ends_at).date() if sub.trial_ends_at else today()
    else:
        start = sub.current_period_end or today()
    subtotal = quantize(sub.plan.price_for(sub.billing_cycle))
    tax = quantize(subtotal * TAX_RATE / 100)
    return {
        "date": start.isoformat(),
        "period_start": start.isoformat(),
        "period_end": (add_cycle(start, sub.billing_cycle) - timedelta(days=1)).isoformat(),
        "subtotal": money(subtotal),
        "tax": money(tax),
        "total": money(subtotal + tax),
    }


# ---- Charges and payments -------------------------------------------------------------------------


def billing_mode() -> str:
    return get_setting(None, "saas_billing").mode


COLLECTION_UNAVAILABLE = (
    "Cobro de suscripciones sin configurar: no se cobró ni se marcó mora a ninguna organización. Configura "
    "WOMPI_PLATFORM_* y activa el cobro en Plataforma → Facturación."
)


def collection_available() -> bool:
    """Whether the platform can charge subscriptions in this installation (P-INT): the simulated gateway where
    simulations are on, or the platform's real Wompi once its `WOMPI_PLATFORM_*` keys are set and the
    integration is enabled (`core.integrations.is_live`). Without it the billing cycle charges nobody and
    never moves an organization to past due or suspended (a production server without the keys would
    otherwise suspend every hotel after three failed attempts)."""
    setting = get_setting(None, "saas_billing")
    if setting.mode == "simulated":
        return setting.enabled and integrations.mode_allowed("saas_billing", "simulated")
    return integrations.is_live(None, "saas_billing")


def _provider():
    return get_provider(None, "saas_billing")


def charge_invoice(
    invoice: PlatformInvoice, *, actor=None, source: str = "automation", require_payment_source: bool = True
) -> dict:
    """Try to collect an unpaid invoice with the billing provider. Returns the provider result
    (`status`: approved | declined | pending | requires_action | error)."""
    if invoice.status not in UNPAID:
        return {"status": "approved" if invoice.status == PlatformInvoice.Status.PAID else "void"}
    sub = get_subscription(invoice.organization)
    if require_payment_source and not (sub and sub.payment_source):
        return {"status": "requires_action", "message": "La organización no tiene un método de pago guardado"}
    result = _provider().charge(invoice, sub)
    status = result.get("status")
    invoice.attempts += 1
    invoice.payment_payload = {**(invoice.payment_payload or {}), **(result.get("payload") or {})}
    if status == "approved":
        invoice.save(update_fields=["attempts", "payment_payload", "updated_at"])
        mark_invoice_paid(
            invoice,
            reference=result.get("reference", ""),
            method=result.get("method", ""),
            actor=actor,
            source=source,
        )
    elif status == "pending":
        invoice.last_error = result.get("message", "")
        invoice.save(update_fields=["attempts", "payment_payload", "last_error", "updated_at"])
    else:
        invoice.status = PlatformInvoice.Status.FAILED
        invoice.last_error = result.get("message") or "Cobro rechazado"
        invoice.save(update_fields=["attempts", "payment_payload", "status", "last_error", "updated_at"])
        audit.record(
            action="saas.charge_failed",
            target=invoice,
            organization=invoice.organization,
            actor=actor,
            source=source,
            summary=f"Cobro fallido de {invoice.number}: {invoice.last_error}",
        )
    return result


def mark_invoice_paid(invoice: PlatformInvoice, *, reference="", method="", actor=None, source="user"):
    if invoice.status == PlatformInvoice.Status.PAID:
        return invoice
    if invoice.status == PlatformInvoice.Status.VOID:
        raise ConflictError("La factura está anulada", code="invoice_void")
    invoice.status = PlatformInvoice.Status.PAID
    invoice.paid_at = timezone.now()
    invoice.payment_reference = reference or invoice.payment_reference
    invoice.payment_method = method or invoice.payment_method
    invoice.last_error = ""
    invoice.save(
        update_fields=[
            "status", "paid_at", "payment_reference", "payment_method", "last_error", "updated_at",
        ]
    )  # fmt: skip
    CommissionSettlement.objects.filter(invoice=invoice).update(
        status=CommissionSettlement.Status.PAID, updated_at=timezone.now()
    )
    audit.record(
        action="saas.invoice_paid",
        target=invoice,
        organization=invoice.organization,
        actor=actor,
        source=source,
        summary=f"Factura {invoice.number} pagada ({invoice.total})",
        changes={"reference": invoice.payment_reference},
    )
    _settle_account(invoice.organization, actor=actor, source=source)
    return invoice


def _settle_account(org: Organization, *, actor=None, source="user") -> None:
    """After a payment: with no unpaid invoices left, a past-due or suspended subscription is active again."""
    if PlatformInvoice.objects.filter(organization=org, status__in=UNPAID).exists():
        return
    sub = get_subscription(org)
    if sub is None or sub.status not in (Subscription.Status.PAST_DUE, Subscription.Status.SUSPENDED):
        return
    was = sub.status
    sub.status = Subscription.Status.ACTIVE
    sub.retries = 0
    sub.next_retry_at = None
    sub.past_due_since = None
    sub.save(update_fields=["status", "retries", "next_retry_at", "past_due_since", "updated_at"])
    _set_org_status(org, Organization.Status.ACTIVE)
    audit.record(
        action="saas.subscription_reactivated",
        target=sub,
        organization=org,
        actor=actor,
        source=source,
        summary=f"Suscripción reactivada tras el pago ({was} → active)",
        changes={"status": [was, "active"]},
    )


def pay_invoice(invoice: PlatformInvoice, *, actor, return_url: str) -> dict:
    """The hotel pays an open invoice now. Simulated mode charges at once (approved unless the organization
    simulates failures); real mode returns the Wompi checkout URL."""
    if invoice.status == PlatformInvoice.Status.PAID:
        raise ConflictError("La factura ya está pagada", code="invoice_paid")
    if invoice.status == PlatformInvoice.Status.VOID:
        raise ConflictError("La factura está anulada", code="invoice_void")
    provider = _provider()
    if provider.mode == "simulated":
        result = charge_invoice(invoice, actor=actor, source="user", require_payment_source=False)
        invoice.refresh_from_db()
        return {"status": result.get("status"), "checkout_url": None, "message": result.get("message", "")}
    try:
        checkout = provider.create_checkout(invoice, return_url=return_url)
    except ProviderError as exc:
        raise BillingError(str(exc), code="provider_error") from exc
    invoice.payment_payload = {**(invoice.payment_payload or {}), **(checkout.get("payload") or {})}
    invoice.save(update_fields=["payment_payload", "updated_at"])
    return {"status": "requires_action", "checkout_url": checkout.get("checkout_url"), "message": ""}


def verify_invoice_payment(invoice: PlatformInvoice, *, actor=None) -> PlatformInvoice:
    """Ask the provider about a checkout started for this invoice (real mode return page / webhook)."""
    if invoice.status not in UNPAID:
        return invoice
    result = _provider().fetch_status(invoice)
    if result.get("status") == "approved":
        mark_invoice_paid(
            invoice, reference=result.get("reference", ""), method=result.get("method", ""), actor=actor
        )
    elif result.get("status") in ("declined", "error", "voided"):
        invoice.status = PlatformInvoice.Status.FAILED
        invoice.last_error = result.get("message") or "Pago rechazado"
        invoice.save(update_fields=["status", "last_error", "updated_at"])
    return invoice


def void_invoice(invoice: PlatformInvoice, *, actor, reason: str = "") -> PlatformInvoice:
    if invoice.status == PlatformInvoice.Status.PAID:
        raise ConflictError("Una factura pagada no se puede anular", code="invoice_paid")
    if invoice.status == PlatformInvoice.Status.VOID:
        return invoice
    invoice.status = PlatformInvoice.Status.VOID
    invoice.last_error = reason
    invoice.save(update_fields=["status", "last_error", "updated_at"])
    for settlement in CommissionSettlement.objects.filter(invoice=invoice):
        settlement.status = CommissionSettlement.Status.OPEN
        settlement.invoice = None
        settlement.save(update_fields=["status", "invoice", "updated_at"])
    audit.record(
        action="saas.invoice_voided",
        target=invoice,
        organization=invoice.organization,
        actor=actor,
        summary=f"Factura {invoice.number} anulada. {reason}".strip(),
    )
    _settle_account(invoice.organization, actor=actor)
    return invoice


# ---- Payment method -------------------------------------------------------------------------------

CARD_BRANDS = (
    ("4", "VISA"),
    ("51", "MASTERCARD"),
    ("52", "MASTERCARD"),
    ("53", "MASTERCARD"),
    ("54", "MASTERCARD"),
    ("55", "MASTERCARD"),
    ("2", "MASTERCARD"),
    ("34", "AMEX"),
    ("37", "AMEX"),
)


def _luhn_ok(number: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(number)):
        digit = int(char)
        if index % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def payment_method_setup() -> dict:
    """What the card form needs: simulated → `{mode}`; real → Wompi tokenization data and the acceptance
    documents (fetched server-side from the platform merchant)."""
    provider = _provider()
    if provider.mode != "real":
        return {"mode": "simulated"}
    try:
        return {"mode": "real", **provider.card_setup()}
    except ProviderError as exc:
        raise BillingError(str(exc), code="provider_error") from exc


def set_payment_method(sub: Subscription, data: dict, *, actor) -> Subscription:
    """Simulated mode: validate a test card and keep only brand / last 4 / expiry. Real mode: store the Wompi
    payment source created from a card token tokenized in the browser (`token` + `acceptance_token` +
    `accept_personal_auth`)."""
    provider = _provider()
    if provider.mode == "real":
        try:
            source = provider.create_payment_source(
                token=data.get("token", ""),
                acceptance_token=data.get("acceptance_token", ""),
                accept_personal_auth=data.get("accept_personal_auth", ""),
                customer_email=actor.email,
            )
        except ProviderError as exc:
            raise BillingError(str(exc), code="provider_error") from exc
    else:
        number = "".join(ch for ch in str(data.get("number", "")) if ch.isdigit())
        fields = {}
        if not (13 <= len(number) <= 19) or not _luhn_ok(number):
            fields["number"] = ["Número de tarjeta inválido"]
        try:
            exp_month, exp_year = int(data.get("exp_month")), int(data.get("exp_year"))
        except (TypeError, ValueError):
            exp_month = exp_year = 0
        if exp_year < 100:
            exp_year += 2000
        now = today()
        if not (1 <= exp_month <= 12) or (exp_year, exp_month) < (now.year, now.month):
            fields["exp_month"] = ["La tarjeta está vencida o la fecha no es válida"]
        cvc = str(data.get("cvc", ""))
        if not (cvc.isdigit() and len(cvc) in (3, 4)):
            fields["cvc"] = ["CVC inválido"]
        holder = str(data.get("holder", "")).strip()
        if not holder:
            fields["holder"] = ["Escribe el nombre como aparece en la tarjeta"]
        if fields:
            raise DomainError("Revisa los datos de la tarjeta", code="validation_error", fields=fields)
        brand = next((name for prefix, name in CARD_BRANDS if number.startswith(prefix)), "CARD")
        source = {
            "type": "card",
            "brand": brand,
            "last4": number[-4:],
            "exp_month": exp_month,
            "exp_year": exp_year,
            "holder": holder[:80],
            "simulated": True,
        }
    sub.payment_source = source
    sub.save(update_fields=["payment_source", "updated_at"])
    audit.record(
        action="saas.payment_method_updated",
        target=sub,
        organization=sub.organization,
        actor=actor,
        summary=f"Método de pago actualizado ({source.get('brand', 'card')} •••• {source.get('last4', '')})",
    )
    return sub


# ---- Subscription changes -------------------------------------------------------------------------


def create_trial_subscription(org: Organization, *, units: int, properties: int = 1) -> Subscription:
    trial_ends_at = org.trial_ends_at or (timezone.now() + timedelta(days=TRIAL_DAYS))
    return Subscription.objects.create(
        organization=org,
        plan=plan_for_units(units, properties),
        status=Subscription.Status.TRIALING,
        billing_cycle=Subscription.Cycle.MONTHLY,
        trial_ends_at=trial_ends_at,
    )


def ensure_subscription(org: Organization) -> Subscription:
    """The organization's subscription; organizations created outside the signup get one on first access
    (trial if the organization is in trial, otherwise mirroring its status, starting today)."""
    sub = get_subscription(org)
    if sub is not None:
        return sub
    units = units_by_organization([org.pk]).get(org.pk, 0)
    properties = max(1, org.properties.count())
    if org.status == Organization.Status.TRIAL:
        return create_trial_subscription(org, units=units, properties=properties)
    status = {
        Organization.Status.PAST_DUE: Subscription.Status.PAST_DUE,
        Organization.Status.SUSPENDED: Subscription.Status.SUSPENDED,
        Organization.Status.CANCELLED: Subscription.Status.CANCELLED,
    }.get(org.status, Subscription.Status.ACTIVE)
    start = today()
    return Subscription.objects.create(
        organization=org,
        plan=plan_for_units(units, properties),
        status=status,
        billing_cycle=Subscription.Cycle.MONTHLY,
        current_period_start=start,
        current_period_end=add_cycle(start, Subscription.Cycle.MONTHLY),
    )


def change_plan(
    sub: Subscription, plan: Plan, *, cycle: str | None = None, actor, source="user", force=False
):
    if not plan.is_active and not force:
        raise DomainError("Ese plan no está disponible", code="plan_inactive")
    info = usage(sub.organization, sub)
    if not force and not plan_fits(plan, units=info["units"], properties=info["properties"]):
        raise DomainError(
            f"El plan {t(plan.name)} no alcanza para {info['units']} unidades y "
            f"{info['properties']} propiedades",
            code="plan_too_small",
            units=info["units"],
            properties=info["properties"],
        )
    cycle = cycle or sub.billing_cycle
    before = {"plan": sub.plan.code, "billing_cycle": sub.billing_cycle}
    sub.plan = plan
    sub.billing_cycle = cycle
    sub.save(update_fields=["plan", "billing_cycle", "updated_at"])
    audit.record(
        action="saas.plan_changed",
        target=sub,
        organization=sub.organization,
        actor=actor,
        source=source,
        summary=f"Plan cambiado de {before['plan']} a {plan.code} ({cycle})",
        changes={"before": before, "after": {"plan": plan.code, "billing_cycle": cycle}},
    )
    check_plan_limit(sub.organization)
    return sub


def cancel_subscription(sub: Subscription, *, actor, reason: str = "") -> Subscription:
    if sub.status == Subscription.Status.CANCELLED:
        raise ConflictError("La suscripción ya está cancelada", code="already_cancelled")
    sub.cancel_at_period_end = True
    sub.save(update_fields=["cancel_at_period_end", "updated_at"])
    audit.record(
        action="saas.subscription_cancel_requested",
        target=sub,
        organization=sub.organization,
        actor=actor,
        summary=f"Cancelación al final del periodo. {reason}".strip(),
    )
    return sub


def resume_subscription(sub: Subscription, *, actor) -> Subscription:
    if sub.status == Subscription.Status.CANCELLED:
        raise ConflictError(
            "La suscripción ya terminó; contáctanos para reactivarla", code="already_cancelled"
        )
    sub.cancel_at_period_end = False
    sub.save(update_fields=["cancel_at_period_end", "updated_at"])
    audit.record(
        action="saas.subscription_resumed",
        target=sub,
        organization=sub.organization,
        actor=actor,
        summary="La suscripción seguirá renovándose",
    )
    return sub


def suspend_organization(org: Organization, *, actor=None, reason: str = "", source="user") -> Organization:
    if org.status == Organization.Status.SUSPENDED:
        raise ConflictError("La organización ya está suspendida", code="already_suspended")
    sub = get_subscription(org)
    if sub is not None and sub.status != Subscription.Status.CANCELLED:
        sub.status = Subscription.Status.SUSPENDED
        sub.next_retry_at = None
        sub.save(update_fields=["status", "next_retry_at", "updated_at"])
    before = org.status
    _set_org_status(org, Organization.Status.SUSPENDED)
    audit.record(
        action="saas.organization_suspended",
        target=org,
        organization=org,
        actor=actor,
        source=source,
        summary=f"Organización suspendida. {reason}".strip(),
        changes={"status": [before, "suspended"]},
    )
    _notify_owners(
        org,
        "Tu cuenta de Housetel está suspendida",
        "Suspendimos el acceso a tu cuenta por falta de pago. Entra a Configuración → Plan y facturación "
        f"para pagar y reactivarla al instante: {public_base_url()}/app/settings/billing",
    )
    return org


def reactivate_organization(org: Organization, *, actor=None, source="user") -> Organization:
    """Admin override: the organization works again (unpaid invoices stay open and can still be paid)."""
    sub = get_subscription(org)
    before = org.status
    sub_changed = False
    if sub is not None and sub.status in (Subscription.Status.SUSPENDED, Subscription.Status.PAST_DUE):
        in_trial = (
            sub.trial_ends_at is not None
            and sub.trial_ends_at > timezone.now()
            and not sub.current_period_start
            and not PlatformInvoice.objects.filter(
                organization=org, status=PlatformInvoice.Status.PAID
            ).exists()
        )
        sub.retries = 0
        sub.next_retry_at = None
        sub.past_due_since = None
        if in_trial:  # suspended by hand during the trial: the trial goes on
            sub.status = Subscription.Status.TRIALING
        else:
            sub.status = Subscription.Status.ACTIVE
            if not sub.current_period_end or sub.current_period_end <= today():
                sub.current_period_start = today()
                sub.current_period_end = add_cycle(today(), sub.billing_cycle)
        sub.save()
        sub_changed = True
    if sub is not None and sub.status == Subscription.Status.TRIALING:
        status = Organization.Status.TRIAL
    else:
        status = Organization.Status.ACTIVE
    if before == status and not sub_changed:
        raise ConflictError("La organización ya está activa", code="already_active")
    _set_org_status(org, status)
    audit.record(
        action="saas.organization_reactivated",
        target=org,
        organization=org,
        actor=actor,
        source=source,
        summary="Organización reactivada",
        changes={"status": [before, status]},
    )
    return org


def extend_trial(org: Organization, days: int, *, actor) -> Subscription:
    if not 1 <= int(days) <= 90:
        raise DomainError("Los días deben estar entre 1 y 90", code="invalid_days")
    sub = get_subscription(org)
    if sub is None:
        raise DomainError("La organización no tiene suscripción", code="no_subscription")
    never_paid = not PlatformInvoice.objects.filter(
        organization=org, status=PlatformInvoice.Status.PAID
    ).exists()
    if sub.status != Subscription.Status.TRIALING and not never_paid:
        raise ConflictError("Solo se extiende la prueba de quien aún no ha pagado", code="not_in_trial")
    base = max(sub.trial_ends_at or timezone.now(), timezone.now())
    sub.trial_ends_at = base + timedelta(days=int(days))
    if sub.status != Subscription.Status.TRIALING:
        # Back to the trial: the invoices issued when it expired no longer apply.
        for invoice in PlatformInvoice.objects.filter(organization=org, status__in=UNPAID):
            void_invoice(invoice, actor=actor, reason="Prueba extendida")
        sub.status = Subscription.Status.TRIALING
        sub.current_period_start = sub.current_period_end = None
        sub.retries = 0
        sub.next_retry_at = sub.past_due_since = None
    sub.save()
    org.trial_ends_at = sub.trial_ends_at
    org.status = Organization.Status.TRIAL
    org.save(update_fields=["trial_ends_at", "status", "updated_at"])
    audit.record(
        action="saas.trial_extended",
        target=sub,
        organization=org,
        actor=actor,
        summary=f"Prueba extendida {days} días (hasta {timezone.localtime(sub.trial_ends_at):%d/%m/%Y})",
    )
    return sub


def end_trial_now(org: Organization, *, actor) -> Subscription:
    """Admin action: the trial ends now and the first period starts (same path as the billing cycle): with a
    card on file the first invoice is charged (→ active); without one, or if the charge fails → past due."""
    sub = get_subscription(org)
    if sub is None or sub.status != Subscription.Status.TRIALING:
        raise ConflictError("La organización no está en prueba", code="not_in_trial")
    now = timezone.now()
    sub.trial_ends_at = now
    sub.save(update_fields=["trial_ends_at", "updated_at"])
    org.trial_ends_at = now
    org.save(update_fields=["trial_ends_at", "updated_at"])
    audit.record(
        action="saas.trial_ended",
        target=sub,
        organization=org,
        actor=actor,
        summary="Prueba terminada por el equipo de Housetel",
    )
    _process_subscription(sub, CycleReport(), now)
    sub.refresh_from_db()
    return sub


# ---- Billing cycle (automation `saas.billing_cycle`) ----------------------------------------------


@dataclass
class CycleReport:
    trials_converted: int = 0
    renewed: int = 0
    paid: int = 0
    failed: int = 0
    past_due: int = 0
    suspended: int = 0
    recovered: int = 0
    cancelled: int = 0
    errors: list = field(default_factory=list)
    skipped: str = ""  # why nothing was charged (collection not configured, P-INT)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def _start_past_due(sub: Subscription, report: CycleReport, now) -> None:
    sub.status = Subscription.Status.PAST_DUE
    sub.retries = 0
    sub.past_due_since = now
    sub.next_retry_at = now + timedelta(days=RETRY_SCHEDULE_DAYS[0])
    sub.save(update_fields=["status", "retries", "past_due_since", "next_retry_at", "updated_at"])
    _set_org_status(sub.organization, Organization.Status.PAST_DUE)
    report.past_due += 1
    audit.record(
        action="saas.subscription_past_due",
        target=sub,
        organization=sub.organization,
        source="automation",
        summary="Suscripción en mora: el cobro no se pudo hacer",
    )
    _notify_owners(
        sub.organization,
        "No pudimos cobrar tu suscripción de Housetel",
        "Tu factura de Housetel está pendiente. Reintentaremos el cobro en los próximos días; también puedes "
        "pagarla ahora desde Configuración → Plan y facturación: "
        f"{public_base_url()}/app/settings/billing",
    )


def _charge_and_track(sub: Subscription, invoice: PlatformInvoice, report: CycleReport, now) -> None:
    result = charge_invoice(invoice)
    if result.get("status") == "approved":
        report.paid += 1
        if sub.status != Subscription.Status.ACTIVE:
            sub.refresh_from_db()
            if sub.status == Subscription.Status.TRIALING:
                sub.status = Subscription.Status.ACTIVE
                sub.save(update_fields=["status", "updated_at"])
        _set_org_status(sub.organization, Organization.Status.ACTIVE)
    elif result.get("status") == "pending":
        return  # verified later (webhook / next run)
    else:
        report.failed += 1
        _start_past_due(sub, report, now)


def _process_subscription(sub: Subscription, report: CycleReport, now) -> None:
    today_ = timezone.localtime(now).date()
    org = sub.organization
    # 1. Trial over.
    if sub.status == Subscription.Status.TRIALING and sub.trial_ends_at and sub.trial_ends_at <= now:
        if sub.cancel_at_period_end:
            _cancel_now(sub, report)
            return
        sub.current_period_start = today_
        sub.current_period_end = add_cycle(today_, sub.billing_cycle)
        sub.save(update_fields=["current_period_start", "current_period_end", "updated_at"])
        invoice = create_period_invoice(sub, today_)
        report.trials_converted += 1
        if sub.payment_source:
            _charge_and_track(sub, invoice, report, now)
        else:
            _start_past_due(sub, report, now)
        return
    # 2. Renewal.
    if (
        sub.status in (Subscription.Status.ACTIVE, Subscription.Status.PAST_DUE)
        and sub.current_period_end
        and sub.current_period_end <= today_
    ):
        if sub.cancel_at_period_end:
            _cancel_now(sub, report)
            return
        start = sub.current_period_end
        sub.current_period_start = start
        sub.current_period_end = add_cycle(start, sub.billing_cycle)
        sub.save(update_fields=["current_period_start", "current_period_end", "updated_at"])
        invoice = create_period_invoice(sub, start)
        report.renewed += 1
        if sub.status == Subscription.Status.ACTIVE:
            _charge_and_track(sub, invoice, report, now)
        return
    # 3. Retries of a past-due subscription.
    if sub.status == Subscription.Status.PAST_DUE and sub.next_retry_at and sub.next_retry_at <= now:
        approved = True
        for invoice in PlatformInvoice.objects.filter(organization=org, status__in=UNPAID).order_by(
            "issued_at"
        ):
            result = charge_invoice(invoice)
            if result.get("status") != "approved":
                approved = False
                break
        sub.refresh_from_db()
        if approved and sub.status == Subscription.Status.ACTIVE:
            report.recovered += 1
            return
        sub.retries += 1
        if sub.retries >= len(RETRY_SCHEDULE_DAYS):
            sub.save(update_fields=["retries", "updated_at"])
            suspend_organization(org, source="automation", reason="Tres intentos de cobro fallidos")
            report.suspended += 1
        else:
            base = sub.past_due_since or now
            sub.next_retry_at = base + timedelta(days=RETRY_SCHEDULE_DAYS[sub.retries])
            sub.save(update_fields=["retries", "next_retry_at", "updated_at"])


def _cancel_now(sub: Subscription, report: CycleReport) -> None:
    sub.status = Subscription.Status.CANCELLED
    sub.cancelled_at = timezone.now()
    sub.save(update_fields=["status", "cancelled_at", "updated_at"])
    _set_org_status(sub.organization, Organization.Status.CANCELLED)
    report.cancelled += 1
    audit.record(
        action="saas.subscription_cancelled",
        target=sub,
        organization=sub.organization,
        source="automation",
        summary="Suscripción cancelada al final del periodo",
    )


def run_billing_cycle(now=None) -> CycleReport:
    """One pass over every subscription; each one in its own savepoint (one failure never stops the rest)."""
    now = now or timezone.now()
    report = CycleReport()
    if not collection_available():
        report.skipped = COLLECTION_UNAVAILABLE
        logger.warning("Billing cycle: subscription charges are not configured; nothing was charged")
    subs = Subscription.objects.select_related("plan", "organization").exclude(
        status=Subscription.Status.CANCELLED
    )
    for sub in subs:
        try:
            if not report.skipped:
                with transaction.atomic():
                    _process_subscription(sub, report, now)
        except Exception as exc:  # noqa: BLE001 - reported in the run details, the loop goes on
            logger.exception("Billing cycle failed for organization %s", sub.organization_id)
            report.errors.append({"organization": str(sub.organization_id), "error": f"{exc}"[:300]})
        try:
            check_plan_limit(sub.organization)
        except Exception:  # noqa: BLE001
            logger.exception("Plan limit check failed for organization %s", sub.organization_id)
    return report


# ---- Notifications --------------------------------------------------------------------------------


def _notify_owners(org: Organization, subject: str, body: str) -> None:
    """Best-effort email to the organization's active owners (Mailpit locally); never raises."""
    from apps.accounts.models import Membership

    emails = list(
        Membership.objects.filter(organization=org, is_active=True, role__code="owner").values_list(
            "user__email", flat=True
        )
    )
    if not emails:
        return

    def _send():
        try:
            send_mail(f"{subject} · {org.name}", body, None, emails, fail_silently=True)
        except Exception:  # noqa: BLE001
            logger.warning("Could not email the owners of %s", org.pk)

    transaction.on_commit(_send)


def organization_summary(org: Organization) -> dict:
    """Small status payload for the topbar chip (any member)."""
    sub = get_subscription(org)
    trial_days_left = None
    if sub and sub.status == Subscription.Status.TRIALING and sub.trial_ends_at:
        trial_days_left = max(0, (timezone.localtime(sub.trial_ends_at).date() - today()).days)
    open_total = sum(
        (
            inv.total
            for inv in PlatformInvoice.objects.filter(organization=org, status__in=UNPAID).only("total")
        ),
        ZERO,
    )
    return {
        "organization_status": org.status,
        "subscription_status": sub.status if sub else None,
        "plan": {"code": sub.plan.code, "name": sub.plan.name} if sub else None,
        "trial_ends_at": sub.trial_ends_at.isoformat() if sub and sub.trial_ends_at else None,
        "trial_days_left": trial_days_left,
        "open_balance": money(open_total),
    }


def unpaid_invoices(org):
    return PlatformInvoice.objects.filter(organization=org, status__in=UNPAID)
