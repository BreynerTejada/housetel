"""`apps.frontdesk.seed.seed(ctx)`: closing reports of the last 30 business days of every demo property,
computed from the history the bookings/finance seeds left (idempotent)."""

import random
from datetime import date, timedelta

import pytest

from apps.bookings.tests.helpers import oct_
from apps.core.seed import SeedContext
from apps.frontdesk.models import NightAuditReport
from apps.frontdesk.seed import seed
from apps.frontdesk.tests.helpers import departed, no_show

pytestmark = pytest.mark.django_db


def context(prop) -> SeedContext:
    return SeedContext(today=prop.business_date, rng=random.Random(20260925), properties={"aurora": prop})


def test_writes_the_reports_of_the_last_thirty_days_from_the_history(hotel):
    departed(hotel, date(2026, 9, 20), date(2026, 9, 22), room=hotel.rooms["101"])
    missed = no_show(hotel, date(2026, 9, 25), date(2026, 9, 26))

    seed(context(hotel.prop))

    reports = list(NightAuditReport.objects.filter(property=hotel.prop).order_by("business_date"))
    assert [report.business_date for report in reports] == [
        oct_(1) - timedelta(days=n) for n in range(30, 0, -1)
    ]
    assert {report.status for report in reports} == {"completed"}
    by_day = {report.business_date: report.summary for report in reports}
    night = by_day[date(2026, 9, 20)]
    assert (night["figures"]["rooms_occupied"], night["figures"]["room_revenue"]) == (1, "320000.00")
    assert night["room_charges"]["nights"] == 1
    assert night["activity"]["arrivals"] == 1
    assert by_day[date(2026, 9, 22)]["activity"]["departures"] == 1
    assert [item["code"] for item in by_day[date(2026, 9, 25)]["no_shows"]] == [missed.reservation.code]
    report = reports[0]
    assert report.finished_at > report.started_at
    assert report.started_at.date() == report.business_date + timedelta(days=1)


def test_running_it_again_creates_nothing(hotel):
    seed(context(hotel.prop))
    seed(context(hotel.prop))

    assert NightAuditReport.objects.filter(property=hotel.prop).count() == 30
