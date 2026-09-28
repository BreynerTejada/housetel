"""`rates_changed` → pending recommendations whose current price is no longer the price of the night expire
(someone changed it by hand: approving them would overwrite that decision with stale figures)."""

from decimal import Decimal

import pytest

from apps.core import signals
from apps.core.signals import seeding
from apps.rates.services.quote import set_daily_rates
from apps.revenue.models import RateRecommendation
from apps.revenue.services.decisions import approve
from apps.revenue.services.runs import run_revenue
from apps.revenue.tests.conftest import make_rule, oct_

pytestmark = pytest.mark.django_db

Status = RateRecommendation.Status


@pytest.fixture
def recs(hotel):
    make_rule(hotel.prop, "holiday", {"adjust": 12})
    run_revenue(hotel.prop)
    return {rec.date: rec for rec in RateRecommendation.objects.filter(status=Status.PENDING)}


def status_of(rec) -> str:
    rec.refresh_from_db()
    return rec.status


def test_a_manual_price_change_expires_the_pending_recommendation_of_that_night(
    hotel, recs, owner, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        set_daily_rates(
            property=hotel.prop,
            room_type=hotel.room_type,
            rate_plan=hotel.plan,
            start=oct_(12),
            end=oct_(13),
            price=Decimal("350000"),
            source="manual",
            actor=owner,
        )
    assert status_of(recs[oct_(12)]) == Status.EXPIRED
    assert status_of(recs[oct_(11)]) == Status.PENDING


def test_a_change_that_leaves_the_price_as_it_was_keeps_them(hotel, recs, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):  # e.g. a plan renamed: B2a announces 365 days
        signals.send_on_commit(
            signals.rates_changed,
            property=hotel.prop,
            room_type_ids=[hotel.room_type.pk],
            rate_plan_ids=[hotel.plan.pk, hotel.derived.pk],
            start=oct_(1),
            end=oct_(1).replace(year=2027),
        )
    assert {status_of(rec) for rec in recs.values()} == {Status.PENDING}


def test_applying_recommendations_does_not_expire_the_others(
    hotel, recs, owner, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        approve(hotel.prop, [recs[oct_(10)].pk, recs[oct_(11)].pk], actor=owner)
    assert status_of(recs[oct_(12)]) == Status.PENDING


def test_seeding_is_ignored(hotel, recs, owner, django_capture_on_commit_callbacks):
    with seeding(), django_capture_on_commit_callbacks(execute=True):
        set_daily_rates(
            property=hotel.prop,
            room_type=hotel.room_type,
            rate_plan=hotel.plan,
            start=oct_(12),
            end=oct_(13),
            price=Decimal("350000"),
            source="manual",
            actor=owner,
        )
    assert status_of(recs[oct_(12)]) == Status.PENDING
