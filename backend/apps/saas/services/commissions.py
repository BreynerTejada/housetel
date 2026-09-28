"""Marketplace commissions (spec §1 point 6, §5 C11).

- A marketplace reservation that is confirmed (or later in house / checked out) owes Housetel
  `lodging net of taxes × property.commission_rate %`, accrued on its checkout date.
- Cancelled or no-show: reversed, or recalculated over the cancellation / no-show fee when there is one
  (accrued on the cancellation date).
- `settle_month` groups the pending commissions accrued in a month per organization into a
  `CommissionSettlement` and bills them in a platform invoice (one line per property + IVA 19 %).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.core import audit
from apps.core.money import ZERO, D, quantize
from apps.saas.models import Commission, CommissionSettlement, PlatformInvoice
from apps.saas.services import billing

logger = logging.getLogger("housetel.saas")

MARKETPLACE_SOURCE = "marketplace"
EARNING_STATUSES = ("confirmed", "checked_in", "checked_out")
ENDED_STATUSES = ("cancelled", "no_show")
BILLABLE_STAY_STATUSES = ("tentative", "confirmed", "checked_in", "checked_out")


def lodging_net(reservation, *, all_stays: bool = False) -> Decimal:
    """Σ net nightly amounts (without taxes) of the billable stays of the reservation (`all_stays`: also the
    cancelled ones, e.g. the base a reversed commission had before the cancellation)."""
    total = ZERO
    for stay in reservation.stays.all():
        if not all_stays and stay.status not in BILLABLE_STAY_STATUSES:
            continue
        for night in stay.nightly_rates or []:
            value = night.get("net")
            if value in (None, ""):
                value = night.get("amount")
            total += D(value)
    return quantize(total, reservation.currency or "COP")


def commission_amount(base, rate, currency="COP") -> Decimal:
    return quantize(D(base) * D(rate) / 100, currency)


def _accrual_for_fee(reservation) -> date:
    if reservation.cancelled_at:
        return timezone.localtime(reservation.cancelled_at).date()
    return reservation.property.business_date or timezone.localdate()


def sync_commission(reservation) -> Commission | None:
    """Create / update / reverse the commission of a marketplace reservation (idempotent).

    Settled commissions are never rewritten (they are already on an invoice)."""
    from apps.bookings.models import Reservation

    reservation = (
        Reservation.objects.select_related("property", "property__organization")
        .prefetch_related("stays")
        .filter(pk=reservation.pk)
        .first()
    )
    if reservation is None or reservation.source != MARKETPLACE_SOURCE:
        return None
    prop = reservation.property
    currency = reservation.currency or prop.currency or "COP"
    rate = D(prop.commission_rate)
    commission = Commission.objects.filter(reservation=reservation).first()
    if commission is not None and commission.status == Commission.Status.SETTLED:
        return commission

    if reservation.status in EARNING_STATUSES:
        base = lodging_net(reservation)
        values = {
            "basis": Commission.Basis.STAY,
            "base_amount": base,
            "rate": rate,
            "amount": commission_amount(base, rate, currency),
            "status": Commission.Status.PENDING,
            "accrual_date": reservation.checkout_date,
            "reversed_at": None,
        }
    elif reservation.status in ENDED_STATUSES:
        fee = quantize(D(reservation.cancellation_fee), currency)
        if fee > 0:
            values = {
                "basis": Commission.Basis.FEE,
                "base_amount": fee,
                "rate": rate,
                "amount": commission_amount(fee, rate, currency),
                "status": Commission.Status.PENDING,
                "accrual_date": _accrual_for_fee(reservation),
                "reversed_at": None,
            }
        elif commission is None:
            return None
        else:
            values = {"status": Commission.Status.REVERSED, "reversed_at": timezone.now()}
    else:  # tentative: nothing is owed yet
        return commission

    if commission is None:
        commission = Commission.objects.create(
            organization=prop.organization,
            property=prop,
            reservation=reservation,
            currency=currency,
            **values,
        )
        action = "saas.commission_recorded"
    else:
        changed = {k: v for k, v in values.items() if getattr(commission, k) != v}
        if not changed:
            return commission
        for key, value in changed.items():
            setattr(commission, key, value)
        commission.save()
        action = (
            "saas.commission_reversed"
            if commission.status == Commission.Status.REVERSED
            else "saas.commission_updated"
        )
    audit.record(
        action=action,
        target=commission,
        property=prop,
        source="system",
        summary=f"Comisión {commission.amount} ({commission.rate} %) de la reserva {reservation.code}",
        changes={"status": commission.status, "amount": str(commission.amount)},
    )
    return commission


def settle_month(
    year: int, month: int, *, organization=None, actor=None, charge=True
) -> list[CommissionSettlement]:
    """Settle the pending commissions accrued in `year-month` (per organization) and invoice them.

    Idempotent: commissions already settled are skipped; a month without pending commissions creates nothing.
    """
    start, end = billing.month_bounds(year, month)
    pending = Commission.objects.filter(
        status=Commission.Status.PENDING, accrual_date__gte=start, accrual_date__lte=end
    ).select_related("property", "organization")
    if organization is not None:
        pending = pending.filter(organization=organization)
    by_org: dict = defaultdict(list)
    for commission in pending:
        by_org[commission.organization].append(commission)

    settlements = []
    for org, commissions in by_org.items():
        with transaction.atomic():
            settlement, _ = CommissionSettlement.objects.get_or_create(
                organization=org, period_start=start, defaults={"period_end": end}
            )
            if settlement.status != CommissionSettlement.Status.OPEN:
                logger.info(
                    "Settlement %s already invoiced; %d late commissions wait",
                    settlement.pk,
                    len(commissions),
                )
                continue
            Commission.objects.filter(pk__in=[c.pk for c in commissions]).update(
                status=Commission.Status.SETTLED, settlement=settlement, updated_at=timezone.now()
            )
            totals = settlement.commissions.aggregate(total=Sum("amount"), count=Count("id"))
            settlement.total = quantize(totals["total"] or ZERO)
            settlement.commissions_count = totals["count"] or 0
            settlement.save(update_fields=["total", "commissions_count", "updated_at"])
            invoice = _invoice_settlement(settlement, actor=actor)
            audit.record(
                action="saas.commissions_settled",
                target=settlement,
                organization=org,
                actor=actor,
                source="user" if actor is not None else "automation",
                summary=(
                    f"Liquidación de comisiones {start:%Y-%m}: {settlement.commissions_count} reservas, "
                    f"{settlement.total}"
                ),
            )
        if charge and invoice is not None:
            try:
                with transaction.atomic():
                    billing.charge_invoice(invoice, actor=actor)
            except Exception:  # noqa: BLE001 - the invoice stays open; the billing cycle retries
                logger.exception("Could not charge commissions invoice %s", invoice.pk)
        settlements.append(settlement)
    return settlements


def _invoice_settlement(settlement: CommissionSettlement, *, actor=None) -> PlatformInvoice | None:
    rows = (
        settlement.commissions.values("property_id", "property__name")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("property__name")
    )
    label = billing.month_label(settlement.period_start)
    lines = []
    for row in rows:
        amount = quantize(row["total"] or ZERO)
        if amount <= 0:
            continue
        lines.append(
            {
                "kind": "commission",
                "description": {
                    "es": (
                        f"Comisiones marketplace · {row['property__name']} · {label['es']} "
                        f"({row['count']} reservas)"
                    ),
                    "en": (
                        f"Marketplace commissions · {row['property__name']} · {label['en']} "
                        f"({row['count']} bookings)"
                    ),
                },
                "quantity": row["count"],
                "unit_price": billing.money(amount),
                "amount": billing.money(amount),
                "property_id": str(row["property_id"]),
                "settlement_id": str(settlement.pk),
            }
        )
    if not lines:
        return None
    invoice = billing.create_invoice(
        settlement.organization,
        kind=PlatformInvoice.Kind.COMMISSIONS,
        period_start=settlement.period_start,
        period_end=settlement.period_end,
        lines=lines,
        actor=actor,
        source="user" if actor is not None else "automation",
    )
    settlement.invoice = invoice
    settlement.status = CommissionSettlement.Status.INVOICED
    settlement.save(update_fields=["invoice", "status", "updated_at"])
    return invoice


def previous_month(day: date | None = None) -> tuple[int, int]:
    day = day or timezone.localdate()
    return (day.year - 1, 12) if day.month == 1 else (day.year, day.month - 1)


def commissions_summary(qs) -> dict:
    """Totals of a Commission queryset by status."""
    rows = qs.values("status").annotate(total=Sum("amount"), count=Count("id"))
    result = {status: {"total": "0.00", "count": 0} for status in Commission.Status.values}
    for row in rows:
        result[row["status"]] = {"total": billing.money(row["total"]), "count": row["count"]}
    return result
