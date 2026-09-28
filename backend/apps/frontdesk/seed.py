"""Demo data of the front desk (plan C1 › Seed): the closing reports of the last 30 business days of every
demo property, rebuilt from the history the bookings and finance seeds left (room nights posted per night,
no-shows by arrival date, payments by business date). Idempotent: a property that already has reports is
skipped. It never runs the audit itself (the history is already closed)."""

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Sum

from apps.bookings.models import Reservation, Stay
from apps.frontdesk.models import NightAuditReport
from apps.frontdesk.services.figures import day_figures, money

DAYS = 30


def seed(ctx) -> None:
    for key, prop in ctx.properties.items():
        if NightAuditReport.objects.filter(property=prop).exists():
            ctx.log(f"  {key}: reportes de auditoría nocturna ya existen")
            continue
        today = prop.business_date
        reports = [_report(prop, today - timedelta(days=offset)) for offset in range(DAYS, 0, -1)]
        NightAuditReport.objects.bulk_create(reports)
        ctx.log(f"  {key}: {len(reports)} reportes de auditoría nocturna")


def _report(prop, day) -> NightAuditReport:
    from apps.finance.models import Charge

    zone = ZoneInfo(prop.timezone or "America/Bogota")
    started = datetime.combine(day + timedelta(days=1), time(2, 0), tzinfo=zone)
    nights = Charge.objects.filter(folio__property=prop, kind="room", night_date=day, voided_at__isnull=True)
    totals = nights.aggregate(net=Sum("amount"), tax=Sum("tax_amount"))
    net, tax = totals["net"] or 0, totals["tax"] or 0
    no_shows = [
        {
            "reservation_id": str(reservation.pk),
            "code": reservation.code,
            "guest_name": reservation.booker.full_name,
            "checkin": reservation.checkin_date.isoformat(),
            "fee": money(reservation.cancellation_fee),
        }
        for reservation in Reservation.objects.filter(property=prop, status="no_show", checkin_date=day)
        .select_related("booker")
        .order_by("code")
    ]
    stays = Stay.objects.filter(reservation__property=prop)
    summary = {
        "business_date": day.isoformat(),
        "next_business_date": (day + timedelta(days=1)).isoformat(),
        "auto_no_show": True,
        "room_charges": {
            "stays": nights.values("stay_id").distinct().count(),
            "nights": nights.count(),
            "net": money(net),
            "tax": money(tax),
            "total": money(net + tax),
        },
        "no_shows": no_shows,
        "no_show_fees": money(sum((Decimal(item["fee"]) for item in no_shows), Decimal("0"))),
        "overdue_departures": [],
        "pending_tentative": [],
        "errors": [],
        "activity": {
            "arrivals": stays.filter(checkin_date=day, status__in=["checked_in", "checked_out"]).count(),
            "departures": stays.filter(checkout_date=day, status="checked_out").count(),
            "in_house": stays.filter(
                checkin_date__lte=day, checkout_date__gt=day, status__in=["checked_in", "checked_out"]
            ).count(),
            "cancellations": Reservation.objects.filter(
                property=prop, status="cancelled", cancelled_at__date=day
            ).count(),
            "no_shows": len(no_shows),
        },
        "figures": day_figures(prop, day),
    }
    return NightAuditReport(
        property=prop,
        business_date=day,
        status=NightAuditReport.Status.COMPLETED,
        started_at=started,
        finished_at=started + timedelta(seconds=4),
        summary=summary,
    )
