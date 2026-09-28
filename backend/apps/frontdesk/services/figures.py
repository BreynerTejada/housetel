"""Figures of one business day, shared by the Today panel and the night audit's closing report.

Definitions (they match the reports engine of C10):
- sold units of the night `day` = stays `confirmed`, `checked_in` or `checked_out` covering it
  (`checkin_date <= day < checkout_date`); tentative, cancelled and no-show stays are not sold. A dorm stay is
  one bed.
- sellable units of the night = `InventoryDay.total_units − blocked_units` of the active categories (rooms,
  or beds in dorms), materialized through the bookings `availability` contract.
- room revenue = net (without taxes) of the night `day` of each sold stay: its non-voided room charge when
  the night is already posted, else the night's `net` in `Stay.nightly_rates` (on the books).
- other revenue = net of the non-voided charges that are not room nights, with business date `day`
  (extras, fees, penalties, adjustments).
- ADR = room revenue / sold units; RevPAR = room revenue / sellable units; collected = approved payments −
  approved refunds with business date `day`.
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Sum

from apps.bookings.models import InventoryDay, Stay
from apps.bookings.services.availability import availability
from apps.core.money import D, quantize

SOLD_STATUSES = ("confirmed", "checked_in", "checked_out")
ZERO = Decimal("0")
CENTS = Decimal("0.01")


def money(value) -> str:
    """API money: a string with two decimals ("335000.00")."""
    return format(D(value).quantize(CENTS), "f")


def percent(part, whole) -> float:
    """`part / whole` in percentage points with one decimal (ROUND_HALF_UP); 0 when there is no whole."""
    if not whole:
        return 0.0
    return float((Decimal(part) * 100 / Decimal(whole)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def sold_stays(prop, day: date):
    return Stay.objects.filter(
        reservation__property=prop,
        checkin_date__lte=day,
        checkout_date__gt=day,
        status__in=SOLD_STATUSES,
    )


def capacity(prop, day: date) -> tuple[int, int]:
    """(total units, blocked units) of the night `day` over the property's active categories."""
    units = availability(property=prop, checkin=day, checkout=day + timedelta(days=1))
    if not units:
        return 0, 0
    totals = InventoryDay.objects.filter(room_type_id__in=list(units), date=day).aggregate(
        total=Sum("total_units"), blocked=Sum("blocked_units")
    )
    return totals["total"] or 0, totals["blocked"] or 0


def night_net(stay, day: date) -> Decimal:
    """Net of the night `day` from the stay's breakdown (`net`, or `amount` for entries without it)."""
    key = day.isoformat()
    for item in stay.nightly_rates or []:
        if item.get("date") == key:
            return D(item.get("net", item.get("amount")))
    return ZERO


def room_revenue(stays, day: date) -> Decimal:
    """Σ net of the night `day` over `stays` (posted room charge first, else the planned night)."""
    from apps.finance.models import Charge

    stays = list(stays)
    posted = dict(
        Charge.objects.filter(stay__in=stays, kind="room", night_date=day, voided_at__isnull=True)
        .values("stay_id")
        .annotate(net=Sum("amount"))
        .values_list("stay_id", "net")
    )
    return sum((posted[stay.pk] if stay.pk in posted else night_net(stay, day) for stay in stays), ZERO)


def other_revenue(prop, day: date) -> Decimal:
    from apps.finance.models import Charge

    total = (
        Charge.objects.filter(folio__property=prop, business_date=day, voided_at__isnull=True)
        .exclude(kind="room")
        .aggregate(net=Sum("amount"))["net"]
    )
    return total or ZERO


def payments(prop, day: date) -> dict:
    """Approved payments and refunds with business date `day`: totals and payments by method."""
    from apps.finance.models import Payment, Refund

    approved = Payment.objects.filter(folio__property=prop, business_date=day, status="approved")
    by_method = [
        {"method": method, "count": count, "total": money(total)}
        for method, count, total in approved.values("method")
        .annotate(count=Count("id"), total=Sum("amount"))
        .order_by("-total", "method")
        .values_list("method", "count", "total")
    ]
    paid = approved.aggregate(total=Sum("amount"))["total"] or ZERO
    refunded = (
        Refund.objects.filter(payment__folio__property=prop, business_date=day, status="approved").aggregate(
            total=Sum("amount")
        )["total"]
        or ZERO
    )
    return {
        "count": sum(item["count"] for item in by_method),
        "total": paid,
        "refunds": refunded,
        "net": paid - refunded,
        "by_method": by_method,
    }


def day_figures(prop, day: date) -> dict:
    """Occupancy and revenue of the business day `day` (money as API strings)."""
    currency = prop.currency or "COP"
    stays = list(sold_stays(prop, day).only("pk", "nightly_rates", "adults", "children"))
    occupied = len(stays)
    total, blocked = capacity(prop, day)
    available = total - blocked
    rooms = room_revenue(stays, day)
    other = other_revenue(prop, day)
    paid = payments(prop, day)
    return {
        "rooms_occupied": occupied,
        "rooms_available": available,
        "rooms_blocked": blocked,
        "rooms_free": available - occupied,
        "occupancy_pct": percent(occupied, available),
        "room_revenue": money(rooms),
        "other_revenue": money(other),
        "revenue": money(rooms + other),
        "adr": money(quantize(rooms / occupied, currency) if occupied else ZERO),
        "revpar": money(quantize(rooms / available, currency) if available > 0 else ZERO),
        "collected": money(paid["net"]),
        "payments": {
            "count": paid["count"],
            "total": money(paid["total"]),
            "refunds": money(paid["refunds"]),
            "by_method": paid["by_method"],
        },
    }
