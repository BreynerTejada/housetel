"""The automation `revenue.run_rules` (spec §6: daily at 05:00 + every 6 hours)."""

import pytest

from apps.core import automation
from apps.revenue.models import RateRecommendation, RevenueRun
from apps.revenue.tests.conftest import make_rule

pytestmark = pytest.mark.django_db


def test_it_is_registered_at_five_and_every_six_hours():
    item = automation.get("revenue.run_rules")
    assert (item.app, item.scope, item.default_enabled) == ("revenue", "property", True)
    assert item.schedule.hour == {5, 11, 17, 23}
    assert item.schedule.minute == {0}


def test_a_scheduled_run_stores_recommendations(hotel):
    make_rule(hotel.prop, "holiday", {"adjust": 12})
    run = automation.run("revenue.run_rules", hotel.prop)
    assert run.status == "success"
    revenue_run = RevenueRun.objects.get(pk=run.details["run_id"])
    assert (revenue_run.trigger, revenue_run.triggered_by) == ("automation", None)
    assert run.details["recommendations"] == 15
    assert RateRecommendation.objects.filter(status="pending").count() == 15
    assert run.summary.startswith("Se revisaron las noches")


def test_it_is_skipped_while_revenue_management_is_disabled(hotel):
    hotel.settings.enabled = False
    hotel.settings.save()
    run = automation.run("revenue.run_rules", hotel.prop)
    assert run.status == "skipped"
    assert not RevenueRun.objects.exists()
