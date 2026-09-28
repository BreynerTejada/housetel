"""Platform metrics for the super-admin (`GET /api/v1/saas/admin/metrics/`).

Definitions:
- MRR = Σ monthly-equivalent price of subscriptions `active` or `past_due` (yearly / 12). Trials are shown
  apart (`trial_mrr`, what they would add if they convert).
- Churn 30 days = subscriptions cancelled in the last 30 days / (paying now + cancelled in the window).
- GMV marketplace (month) = Σ total of marketplace reservations created in the month that are confirmed,
  in house or checked out.
- Commissions (month) = Σ commissions accrued in the month that are not reversed.
- Monthly series (12 months, oldest first): `subscriptions` = Σ subtotals of subscription invoices by the
  month their period starts (yearly plans spread as /12), `commissions`, `gmv` and `new_organizations`.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.core.models import Organization
from apps.core.money import ZERO, quantize
from apps.saas.models import Commission, PlatformInvoice, Subscription

PAYING = (Subscription.Status.ACTIVE, Subscription.Status.PAST_DUE)
GMV_STATUSES = ("confirmed", "checked_in", "checked_out")


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _money(value) -> str:
    return f"{quantize(value or ZERO):.2f}"


def platform_metrics(today: date | None = None) -> dict:
    from apps.bookings.models import Reservation

    today = today or timezone.localdate()
    month_start = _month_start(today)
    now = timezone.now()

    subs = list(Subscription.objects.select_related("plan"))
    mrr = sum((s.monthly_amount for s in subs if s.status in PAYING), ZERO)
    trial_mrr = sum((s.monthly_amount for s in subs if s.status == Subscription.Status.TRIALING), ZERO)
    cancelled_30 = sum(
        1
        for s in subs
        if s.status == Subscription.Status.CANCELLED
        and s.cancelled_at
        and s.cancelled_at >= now - timedelta(days=30)
    )
    paying = sum(1 for s in subs if s.status in PAYING)
    churn = round(cancelled_30 * 100 / (paying + cancelled_30), 1) if (paying + cancelled_30) else 0.0

    org_counts = {
        row["status"]: row["n"] for row in Organization.objects.values("status").annotate(n=Count("id"))
    }

    marketplace = Reservation.objects.filter(source="marketplace", status__in=GMV_STATUSES)
    gmv_month = marketplace.filter(created_at__date__gte=month_start).aggregate(t=Sum("total_amount"))["t"]
    commissions_live = Commission.objects.exclude(status=Commission.Status.REVERSED)
    commissions_month = commissions_live.filter(
        accrual_date__gte=month_start, accrual_date__lte=today
    ).aggregate(t=Sum("amount"))["t"]
    commissions_pending = Commission.objects.filter(status=Commission.Status.PENDING).aggregate(
        t=Sum("amount")
    )["t"]
    unpaid = PlatformInvoice.objects.filter(status__in=("open", "failed")).aggregate(
        t=Sum("total"), n=Count("id")
    )

    # ---- 12-month series ----
    first_month = month_start - relativedelta(months=11)
    months = [first_month + relativedelta(months=i) for i in range(12)]
    series = {m: defaultdict(lambda: ZERO) for m in months}
    for invoice in PlatformInvoice.objects.filter(
        kind=PlatformInvoice.Kind.SUBSCRIPTION, period_start__gte=first_month - relativedelta(months=11)
    ).exclude(status=PlatformInvoice.Status.VOID):
        span = 12 if (invoice.period_end - invoice.period_start).days > 40 else 1
        share = invoice.subtotal / span
        for i in range(span):
            month = _month_start(invoice.period_start) + relativedelta(months=i)
            if month in series:
                series[month]["subscriptions"] += share
    for row in (
        commissions_live.filter(accrual_date__gte=first_month, accrual_date__lte=today)
        .annotate(m=TruncMonth("accrual_date"))
        .values("m")
        .annotate(t=Sum("amount"))
    ):
        month = row["m"] if isinstance(row["m"], date) else row["m"].date()
        if month in series:
            series[month]["commissions"] += row["t"] or ZERO
    for row in (
        marketplace.filter(created_at__date__gte=first_month)
        .annotate(m=TruncMonth("created_at"))
        .values("m")
        .annotate(t=Sum("total_amount"), n=Count("id"))
    ):
        month = timezone.localtime(row["m"]).date().replace(day=1) if hasattr(row["m"], "hour") else row["m"]
        if month in series:
            series[month]["gmv"] += row["t"] or ZERO
            series[month]["bookings"] += row["n"]
    for row in (
        Organization.objects.filter(created_at__date__gte=first_month)
        .annotate(m=TruncMonth("created_at"))
        .values("m")
        .annotate(n=Count("id"))
    ):
        month = timezone.localtime(row["m"]).date().replace(day=1) if hasattr(row["m"], "hour") else row["m"]
        if month in series:
            series[month]["new_organizations"] += row["n"]

    plan_mix = defaultdict(int)
    for s in subs:
        if s.status != Subscription.Status.CANCELLED:
            plan_mix[(s.plan.code, s.plan.sort)] += 1

    return {
        "as_of": today.isoformat(),
        "currency": "COP",
        "mrr": _money(mrr),
        "arr": _money(mrr * 12),
        "trial_mrr": _money(trial_mrr),
        "organizations": {
            "total": sum(org_counts.values()),
            "active": org_counts.get("active", 0),
            "trial": org_counts.get("trial", 0),
            "past_due": org_counts.get("past_due", 0),
            "suspended": org_counts.get("suspended", 0),
            "cancelled": org_counts.get("cancelled", 0),
        },
        "churn_30d": churn,
        "cancelled_30d": cancelled_30,
        "gmv_month": _money(gmv_month),
        "commissions_month": _money(commissions_month),
        "commissions_pending": _money(commissions_pending),
        "unpaid_invoices": {"count": unpaid["n"] or 0, "total": _money(unpaid["t"])},
        "series": [
            {
                "month": m.strftime("%Y-%m"),
                "subscriptions": _money(series[m]["subscriptions"]),
                "commissions": _money(series[m]["commissions"]),
                "gmv": _money(series[m]["gmv"]),
                "bookings": int(series[m]["bookings"]),
                "new_organizations": int(series[m]["new_organizations"]),
            }
            for m in months
        ],
        "plan_mix": [
            {"plan": code, "count": count}
            for (code, _sort), count in sorted(plan_mix.items(), key=lambda i: i[0][1])
        ],
    }


def organization_mrr(sub: Subscription | None) -> Decimal:
    if sub is None or sub.status not in PAYING:
        return ZERO
    return sub.monthly_amount
