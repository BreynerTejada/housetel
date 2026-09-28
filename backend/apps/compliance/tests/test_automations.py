"""Automations of compliance run through the core framework (AutomationRun + audit)."""

from datetime import date

import pytest

from apps.compliance.models import Invoice, SireReport
from apps.core import automation

pytestmark = pytest.mark.django_db


def test_the_three_automations_are_registered_with_their_schedules():
    codes = {item.code: item for item in automation.all() if item.app == "compliance"}

    assert set(codes) == {
        "compliance.issue_pending_invoices",
        "compliance.sire_daily_file",
        "compliance.tra_retry",
    }
    assert str(codes["compliance.issue_pending_invoices"].schedule._orig_minute) == "*/15"
    assert (
        codes["compliance.sire_daily_file"].schedule._orig_hour,
        codes["compliance.sire_daily_file"].schedule._orig_minute,
    ) == (8, 0)


def test_pending_invoices_runs_and_reports(hotel, resolution, make_finished_reservation):
    reservation = make_finished_reservation()

    run = automation.run("compliance.issue_pending_invoices", hotel)

    assert run.status == "success"
    assert run.details["auto_issued"] == 1
    assert Invoice.objects.get(reservation=reservation).status == "accepted"


def test_sire_daily_file_skips_a_day_without_movements(hotel):
    hotel.business_date = date(2026, 1, 2)
    hotel.save()

    run = automation.run("compliance.sire_daily_file", hotel)

    assert run.status == "skipped"
    assert not SireReport.objects.exists()


def test_tra_retry_runs(hotel):
    run = automation.run("compliance.tra_retry", hotel)

    assert run.status == "success"
    assert run.details == {"retried": 0, "registered": 0, "failed": 0}
