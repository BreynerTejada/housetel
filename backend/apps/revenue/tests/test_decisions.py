"""Approve / reject / apply recommendations: approving writes the grid with
`set_daily_rates(source="revenue")` (contiguous nights with the same price in one write), rejecting only
records the decision."""

from decimal import Decimal

import pytest

from apps.core.errors import DomainError
from apps.core.models import AuditEvent
from apps.rates.models import DailyRate
from apps.rates.services.quote import resolve_daily
from apps.revenue.models import RateRecommendation
from apps.revenue.services.decisions import apply, approve, reject
from apps.revenue.services.runs import run_revenue
from apps.revenue.tests.conftest import make_rule, oct_

pytestmark = pytest.mark.django_db

D = Decimal
Status = RateRecommendation.Status


@pytest.fixture
def recs(hotel):
    """Pending: 10–12 Oct (+12 %, 336.000) and 14 Oct (Wednesday +5 %, 315.000)."""
    make_rule(hotel.prop, "holiday", {"adjust": 12})
    make_rule(hotel.prop, "day_of_week", {"wed": 5})
    run_revenue(hotel.prop)
    pending = RateRecommendation.objects.filter(property=hotel.prop, status=Status.PENDING)
    return {rec.date: rec for rec in pending}


def ids(recs, *days):
    return [recs[oct_(day)].pk for day in days]


def test_approving_writes_the_recommended_prices_with_source_revenue(hotel, recs, owner):
    result = approve(hotel.prop, ids(recs, 10, 11, 12, 14), actor=owner)
    assert (len(result.recommendations), result.skipped, result.errors) == (4, [], [])
    for rec in RateRecommendation.objects.filter(pk__in=ids(recs, 10, 11, 12, 14)):
        assert rec.status == Status.APPLIED
        assert rec.decided_by == owner and rec.decided_at and rec.applied_at
    prices = dict(DailyRate.objects.filter(rate_plan=hotel.plan).values_list("date", "price"))
    assert prices == {
        oct_(10): D("336000"),
        oct_(11): D("336000"),
        oct_(12): D("336000"),
        oct_(14): D("315000"),
    }
    assert set(DailyRate.objects.values_list("source", flat=True)) == {"revenue"}
    # the derived plan (−12 %) follows its base plan
    assert resolve_daily(hotel.room_type, hotel.derived, oct_(12), oct_(13))[0].price == D("295680")


def test_contiguous_nights_with_the_same_price_are_written_together(hotel, recs, owner):
    approve(hotel.prop, ids(recs, 10, 11, 12, 14), actor=owner)
    events = AuditEvent.objects.filter(action="rates.bulk_update").order_by("created_at")
    assert [(e.changes["start"], e.changes["end"], e.source, e.actor) for e in events] == [
        ("2026-10-10", "2026-10-13", "user", owner),
        ("2026-10-14", "2026-10-15", "user", owner),
    ]
    decision = AuditEvent.objects.get(action="revenue.recommendations_approved")
    assert decision.changes["count"] == 4


def test_rejecting_only_records_the_decision(hotel, recs, owner):
    result = reject(hotel.prop, ids(recs, 12), actor=owner)
    rec = result.recommendations[0]
    assert (rec.status, rec.decided_by, rec.applied_at) == (Status.REJECTED, owner, None)
    assert not DailyRate.objects.exists()
    assert AuditEvent.objects.filter(action="revenue.recommendations_rejected").exists()


def test_only_pending_recommendations_of_the_property_are_decided(hotel, recs, owner, make_member):
    from apps.core.tests.factories import PropertyFactory

    other = PropertyFactory(organization=hotel.prop.organization)
    foreign = RateRecommendation.objects.create(
        property=other,
        room_type=hotel.room_type,
        rate_plan=hotel.plan,
        date=oct_(20),
        current_price=D("1"),
        anchor_price=D("1"),
        recommended_price=D("2"),
        change_percent=D("100"),
    )
    approve(hotel.prop, ids(recs, 10), actor=owner)
    result = approve(hotel.prop, [*ids(recs, 10), foreign.pk], actor=owner)
    assert result.recommendations == []
    assert result.skipped == [
        {"id": str(recs[oct_(10)].pk), "reason": "not_pending"},
        {"id": str(foreign.pk), "reason": "not_found"},
    ]
    foreign.refresh_from_db()
    assert foreign.status == Status.PENDING


def test_a_recommendation_for_a_past_night_expires_instead_of_being_applied(hotel, recs, owner):
    hotel.prop.business_date = oct_(11)
    hotel.prop.save(update_fields=["business_date"])
    result = approve(hotel.prop, ids(recs, 10, 11), actor=owner)
    assert [rec.date for rec in result.recommendations] == [oct_(11)]
    assert result.skipped == [{"id": str(recs[oct_(10)].pk), "reason": "expired"}]
    assert RateRecommendation.objects.get(pk=recs[oct_(10)].pk).status == Status.EXPIRED
    assert not DailyRate.objects.filter(date=oct_(10)).exists()


def test_an_approval_that_cannot_be_written_stays_approved_and_can_be_applied_later(
    hotel, recs, owner, monkeypatch
):
    def refuse(**kwargs):
        raise DomainError(
            "Los planes derivados se calculan desde su plan base", code="derived_plan_not_editable"
        )

    monkeypatch.setattr("apps.revenue.services.decisions.set_daily_rates", refuse)
    result = approve(hotel.prop, ids(recs, 14), actor=owner)
    assert result.errors == [
        {
            "id": str(recs[oct_(14)].pk),
            "code": "derived_plan_not_editable",
            "detail": "Los planes derivados se calculan desde su plan base",
        }
    ]
    rec = RateRecommendation.objects.get(pk=recs[oct_(14)].pk)
    assert (rec.status, rec.apply_error) == (
        Status.APPROVED,
        "Los planes derivados se calculan desde su plan base",
    )
    monkeypatch.undo()
    apply(hotel.prop, ids(recs, 14), actor=owner)
    rec.refresh_from_db()
    assert (rec.status, rec.apply_error) == (Status.APPLIED, "")
    assert DailyRate.objects.get(date=oct_(14)).price == D("315000")


def test_apply_takes_pending_recommendations_too(hotel, recs, owner):
    result = apply(hotel.prop, ids(recs, 12), actor=owner)
    assert result.recommendations[0].status == Status.APPLIED
    assert result.recommendations[0].decided_by == owner
