"""A revenue run: stores one pending recommendation per night, refreshes/supersedes/expires the previous ones,
respects rejections, auto-applies when the property asks for it, and writes its summaries."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.models import AuditEvent
from apps.rates.models import DailyRate
from apps.revenue.models import RateRecommendation, RevenueRun
from apps.revenue.services.runs import run_revenue
from apps.revenue.tests.conftest import FakeLLM, make_rule, oct_

pytestmark = pytest.mark.django_db

D = Decimal
Status = RateRecommendation.Status


def pending(prop):
    return {rec.date: rec for rec in RateRecommendation.objects.filter(property=prop, status=Status.PENDING)}


def statuses(prop):
    return sorted(RateRecommendation.objects.filter(property=prop).values_list("date", "status"))


def test_a_run_stores_its_recommendations_and_a_summary(hotel):
    make_rule(hotel.prop, "holiday", {"adjust": 12}, name="Festivos")
    run = run_revenue(hotel.prop, trigger="manual")
    assert (run.status, run.trigger, run.start_date, run.end_date) == (
        "success",
        "manual",
        oct_(1),
        oct_(1) + timedelta(days=120),
    )
    # 10–12 Oct (Día de la Raza), 31 Oct–2 Nov, 14–16 Nov, 8 Dec, 25 Dec, 1 Jan, 9–11 Jan
    recs = pending(hotel.prop)
    assert len(recs) == run.recommendations_count == 15
    assert {rec.run_id for rec in recs.values()} == {run.pk}
    assert recs[oct_(12)].recommended_price == D("336000")
    assert run.details["up"] == 15 and run.details["down"] == 0
    assert run.details["estimated_impact"] == "5400000.00"  # 15 nights × 10 free rooms × 36.000
    assert (run.details["impact_up"], run.details["impact_down"]) == ("5400000.00", "0.00")
    assert run.summary["es"].startswith(
        "Se revisaron las noches del 01/10/2026 al 28/01/2027: 15 recomendaciones"
    )
    assert run.summary["en"].startswith(
        "Nights from Oct 1, 2026 to Jan 28, 2027 reviewed: 15 recommendations"
    )
    assert "Festivos (15)" in run.summary["es"]


def test_the_summary_reports_raises_and_drops_separately(hotel):
    make_rule(hotel.prop, "event", {"start": "2026-10-20", "end": "2026-10-20", "adjust": 10})
    make_rule(hotel.prop, "event", {"start": "2026-10-21", "end": "2026-10-21", "adjust": -5})
    run = run_revenue(hotel.prop)
    assert run.summary["es"].endswith(
        "Impacto estimado si se venden las unidades libres: $ 150.000 "
        "(subidas +$ 300.000; bajadas −$ 150.000)."
    )
    assert run.summary["en"].endswith(
        "Estimated impact if the free units sell: $150,000 (raises +$300,000; drops −$150,000)."
    )


def test_the_ai_summary_falls_back_to_the_template_when_the_llm_is_simulated(
    hotel, fake_llm, django_capture_on_commit_callbacks
):
    make_rule(hotel.prop, "holiday", {"adjust": 12})
    with django_capture_on_commit_callbacks(execute=True):
        run = run_revenue(hotel.prop)
    run.refresh_from_db()
    assert len(fake_llm.calls) == 1
    assert (run.ai_summary, run.ai_provider) == (run.summary, "")


def test_the_ai_summary_comes_from_the_llm(hotel, monkeypatch, django_capture_on_commit_callbacks):
    llm = FakeLLM(data={"es": "Suben los festivos.", "en": "Holidays go up."}, provider="gemini")
    monkeypatch.setattr("apps.revenue.services.summary.get_llm", lambda property=None: llm)
    make_rule(hotel.prop, "holiday", {"adjust": 12})
    with django_capture_on_commit_callbacks(execute=True):
        run = run_revenue(hotel.prop)
    run.refresh_from_db()
    assert (run.ai_summary, run.ai_provider) == (
        {"es": "Suben los festivos.", "en": "Holidays go up."},
        "gemini",
    )
    call = llm.calls[0]
    assert set(call["response_schema"]["properties"]) == {"es", "en"}
    assert '"count": 15' in call["messages"][0]["content"]  # the prompt carries the run figures


def test_a_failing_llm_never_breaks_the_run(hotel, monkeypatch, django_capture_on_commit_callbacks):
    llm = FakeLLM(error=RuntimeError("429 quota exceeded"))
    monkeypatch.setattr("apps.revenue.services.summary.get_llm", lambda property=None: llm)
    make_rule(hotel.prop, "holiday", {"adjust": 12})
    with django_capture_on_commit_callbacks(execute=True):
        run = run_revenue(hotel.prop)
    run.refresh_from_db()
    assert run.status == "success"
    assert (run.ai_summary, run.ai_provider) == (run.summary, "")


def test_the_llm_is_asked_only_after_the_run_is_committed(
    hotel, monkeypatch, django_capture_on_commit_callbacks
):
    """A slow or failing provider never holds the run's transaction (and its row locks) open."""
    llm = FakeLLM(data={"es": "Suben los festivos.", "en": "Holidays go up."}, provider="gemini")
    monkeypatch.setattr("apps.revenue.services.summary.get_llm", lambda property=None: llm)
    make_rule(hotel.prop, "holiday", {"adjust": 12})
    with django_capture_on_commit_callbacks() as callbacks:  # the run's transaction has not committed yet
        run = run_revenue(hotel.prop)
    assert llm.calls == []
    assert (run.ai_summary, run.ai_provider) == (run.summary, "")  # the template until the LLM answers
    for callback in callbacks:
        callback()
    run.refresh_from_db()
    assert run.ai_provider == "gemini"
    assert '"count": 15' in llm.calls[0]["messages"][0]["content"]


def test_the_seed_run_skips_the_llm(hotel, fake_llm, django_capture_on_commit_callbacks):
    make_rule(hotel.prop, "holiday", {"adjust": 12})
    with django_capture_on_commit_callbacks(execute=True):
        run_revenue(hotel.prop, trigger="seed", use_ai=False)
    assert fake_llm.calls == []


def queries_of_a_second_run(prop) -> int:
    run_revenue(prop)
    with CaptureQueriesContext(connection) as queries:
        run_revenue(prop)  # every pending recommendation is refreshed
    return len(queries.captured_queries)


def test_the_queries_of_a_run_do_not_grow_with_its_recommendations(hotel):
    make_rule(hotel.prop, "holiday", {"adjust": 12})  # 15 nights
    few = queries_of_a_second_run(hotel.prop)
    make_rule(hotel.prop, "day_of_week", {"mon": 5, "tue": 5, "wed": 5, "thu": 5})  # + ~70 nights
    many = queries_of_a_second_run(hotel.prop)
    assert RateRecommendation.objects.filter(status=Status.PENDING).count() > 60
    assert many == few


def test_running_again_with_the_same_inputs_creates_nothing_new(hotel):
    make_rule(hotel.prop, "holiday", {"adjust": 12})
    first = run_revenue(hotel.prop)
    ids = set(RateRecommendation.objects.values_list("pk", flat=True))
    second = run_revenue(hotel.prop)
    assert set(RateRecommendation.objects.values_list("pk", flat=True)) == ids
    assert second.recommendations_count == first.recommendations_count == 15
    assert {rec.run_id for rec in pending(hotel.prop).values()} == {second.pk}
    assert second.details["created"] == 0 and second.details["refreshed"] == 15


def test_a_different_proposal_supersedes_the_pending_one(hotel):
    rule = make_rule(hotel.prop, "holiday", {"adjust": 12})
    run_revenue(hotel.prop)
    old = pending(hotel.prop)[oct_(12)]
    rule.params = {"adjust": 15, "include_bridges": True}
    rule.save()
    run = run_revenue(hotel.prop)
    old.refresh_from_db()
    assert old.status == Status.EXPIRED
    assert pending(hotel.prop)[oct_(12)].recommended_price == D("345000")
    assert run.details["superseded"] == 15


def test_pending_recommendations_that_are_no_longer_proposed_expire(hotel):
    rule = make_rule(hotel.prop, "holiday", {"adjust": 12})
    run_revenue(hotel.prop)
    rule.is_active = False
    rule.save()
    run = run_revenue(hotel.prop)
    assert pending(hotel.prop) == {}
    assert run.recommendations_count == 0
    assert run.summary["es"].endswith("no hay cambios de precio que recomendar.")


def test_a_rejected_recommendation_is_not_proposed_again_until_it_changes(hotel, owner):
    from apps.revenue.services.decisions import reject

    rule = make_rule(hotel.prop, "holiday", {"adjust": 12})
    run_revenue(hotel.prop)
    reject(hotel.prop, [pending(hotel.prop)[oct_(12)].pk], actor=owner)
    run = run_revenue(hotel.prop)
    assert oct_(12) not in pending(hotel.prop)
    assert run.details["kept_rejected"] == 1
    rule.params = {"adjust": 15, "include_bridges": True}
    rule.save()
    run_revenue(hotel.prop)
    assert pending(hotel.prop)[oct_(12)].recommended_price == D("345000")


def test_recommendations_of_past_nights_expire(hotel):
    make_rule(hotel.prop, "holiday", {"adjust": 12})
    run_revenue(hotel.prop)
    hotel.prop.business_date = oct_(12)  # the night audit moved on: 10 and 11 Oct are past
    hotel.prop.save(update_fields=["business_date"])
    run = run_revenue(hotel.prop)
    assert RateRecommendation.objects.get(date=oct_(10)).status == Status.EXPIRED
    assert RateRecommendation.objects.get(date=oct_(11)).status == Status.EXPIRED
    assert run.expired_count == 2
    assert run.start_date == oct_(12)


def test_auto_apply_writes_the_prices_with_source_revenue(hotel, django_capture_on_commit_callbacks):
    hotel.settings.auto_apply = True
    hotel.settings.save()
    make_rule(hotel.prop, "holiday", {"adjust": 12})
    with django_capture_on_commit_callbacks(execute=True):
        run = run_revenue(hotel.prop)
    recs = RateRecommendation.objects.filter(property=hotel.prop)
    assert set(recs.values_list("status", flat=True)) == {Status.AUTO_APPLIED}
    assert run.auto_applied_count == 15
    assert all(rec.applied_at is not None and rec.decided_by is None for rec in recs)
    rows = DailyRate.objects.filter(rate_plan=hotel.plan, date__in=[oct_(10), oct_(11), oct_(12)])
    assert sorted(rows.values_list("price", "source")) == [(D("336000.00"), "revenue")] * 3
    events = AuditEvent.objects.filter(action="rates.bulk_update")
    assert set(events.values_list("source", flat=True)) == {"automation"}
    # contiguous nights with the same price are written together: 7 blocks for 15 nights
    assert events.count() == 7
    assert run_revenue(hotel.prop).recommendations_count == 0  # the prices already are the recommended ones


def test_runs_are_listed_newest_first(hotel):
    first = run_revenue(hotel.prop)
    second = run_revenue(hotel.prop)
    assert list(RevenueRun.objects.filter(property=hotel.prop)) == [second, first]
