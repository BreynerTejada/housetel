"""`set_daily_rates` (plan B2a) and the multi-category bulk write behind `POST grid/bulk/`.

Rows are completed with the resolved price, `dow` filters weekdays (Monday = 0), relative deltas apply to the
resolved price, derived plans are read-only, every write is one reversible audit event whose undo restores the
previous rows, and `rates_changed` lists the base plan and its derived plans.
"""

from decimal import Decimal

import pytest

from apps.core import audit
from apps.core.errors import DomainError
from apps.core.models import AuditEvent
from apps.core.signals import rates_changed
from apps.inventory.tests.factories import RoomTypeFactory
from apps.rates.models import DailyRate, Season, SeasonRate
from apps.rates.services.quote import quote, set_daily_rates
from apps.rates.services.writes import bulk_update_rates
from apps.rates.tests.conftest import oct_
from apps.rates.tests.factories import DailyRateFactory, DerivedRatePlanFactory, RoomTypeRateDefaultsFactory

pytestmark = pytest.mark.django_db

D = Decimal


def write(rates, *, start=None, end=None, **kwargs):
    return set_daily_rates(
        property=rates.prop,
        room_type=rates.room_type,
        rate_plan=rates.plan,
        start=start or oct_(1),
        end=end or oct_(3),
        **kwargs,
    )


def rows(rates, room_type=None):
    return {
        r.date: r
        for r in DailyRate.objects.filter(room_type=room_type or rates.room_type, rate_plan=rates.plan)
    }


@pytest.fixture
def capture_rates_changed():
    received = []

    def receiver(sender, **kwargs):
        kwargs.pop("signal")
        received.append(kwargs)

    rates_changed.connect(receiver)
    yield received
    rates_changed.disconnect(receiver)


class TestRows:
    def test_missing_rows_are_created_with_the_resolved_price_and_source(self, rates):
        rates.defaults.dow_adjustments = {"sat": 15}
        rates.defaults.save()
        season = Season.objects.create(
            property=rates.prop, name="Puente", start_date=oct_(2), end_date=oct_(2)
        )
        SeasonRate.objects.create(
            season=season, room_type=rates.room_type, rate_plan=rates.plan, price=D("400000")
        )
        assert write(rates, end=oct_(4), restrictions={"min_los": 2}) == 3
        assert [(r.date, r.price, r.source, r.min_los) for r in rows(rates).values()] == [
            (oct_(1), D("320000.00"), "default", 2),
            (oct_(2), D("400000.00"), "season", 2),
            (oct_(3), D("368000.00"), "default", 2),
        ]

    def test_existing_rows_keep_their_source_when_only_restrictions_change(self, rates):
        DailyRateFactory(room_type=rates.room_type, rate_plan=rates.plan, date=oct_(1), source="revenue")
        write(rates, end=oct_(2), restrictions={"stop_sell": True})
        assert (rows(rates)[oct_(1)].source, rows(rates)[oct_(1)].stop_sell) == ("revenue", True)

    def test_a_price_change_marks_the_rows_with_the_given_source(self, rates, owner):
        DailyRateFactory(room_type=rates.room_type, rate_plan=rates.plan, date=oct_(1), source="revenue")
        write(rates, price=D("300000"), source="bulk", actor=owner)
        assert [(r.price, r.source, r.updated_by) for r in rows(rates).values()] == [
            (D("300000.00"), "bulk", owner)
        ] * 2

    def test_percent_delta_applies_to_the_resolved_price(self, rates):
        season = Season.objects.create(
            property=rates.prop, name="Puente", start_date=oct_(2), end_date=oct_(2)
        )
        SeasonRate.objects.create(
            season=season, room_type=rates.room_type, rate_plan=rates.plan, price=D("400000")
        )
        write(rates, restrictions={"price_delta_percent": 10})
        assert [r.price for r in rows(rates).values()] == [D("352000.00"), D("440000.00")]

    def test_a_relative_change_on_nights_holding_only_restrictions_uses_their_current_price(self, rates):
        write(rates, restrictions={"min_los": 2})  # rows keep following the defaults
        rates.defaults.price = D("350000")
        rates.defaults.save()
        write(rates, restrictions={"price_delta_percent": 10})
        assert [(r.price, r.source, r.min_los) for r in rows(rates).values()] == [
            (D("385000.00"), "manual", 2)
        ] * 2

    def test_the_weekday_filter_uses_monday_zero(self, rates):
        # 2026-10-03 is a Saturday and 2026-10-04 a Sunday
        assert write(rates, end=oct_(8), price=D("380000"), dow=[5, 6]) == 2
        assert list(rows(rates)) == [oct_(3), oct_(4)]

    @pytest.mark.parametrize(
        "kwargs",
        [{"restrictions": {"stop_sell": True}}, {"restrictions": {"price_delta_percent": 10}}],
    )
    def test_nights_without_any_price_need_an_exact_price(self, rates, kwargs):
        """A restriction or a relative change on a night with no configured price would sell it at 0."""
        rates.defaults.delete()
        with pytest.raises(DomainError) as exc:
            write(rates, **kwargs)
        assert (exc.value.code, exc.value.extra["room_type"]) == ("no_rate", "DBL")
        assert not DailyRate.objects.exists()

    def test_an_exact_price_prices_nights_that_had_none(self, rates):
        rates.defaults.delete()
        assert write(rates, price=D("250000"), restrictions={"min_los": 2}) == 2
        assert [(r.price, r.source, r.min_los) for r in rows(rates).values()] == [
            (D("250000.00"), "manual", 2)
        ] * 2

    def test_existing_rows_of_a_category_without_defaults_keep_accepting_restrictions(self, rates):
        rates.defaults.delete()
        DailyRateFactory(room_type=rates.room_type, rate_plan=rates.plan, date=oct_(1), price=D("300000"))
        assert write(rates, end=oct_(2), restrictions={"closed_to_arrival": True}) == 1
        assert (rows(rates)[oct_(1)].price, rows(rates)[oct_(1)].closed_to_arrival) == (D("300000.00"), True)

    def test_restrictions_can_be_cleared(self, rates):
        DailyRateFactory(room_type=rates.room_type, rate_plan=rates.plan, date=oct_(1), min_los=3, max_los=5)
        write(rates, end=oct_(2), restrictions={"min_los": None, "max_los": None})
        assert (rows(rates)[oct_(1)].min_los, rows(rates)[oct_(1)].max_los) == (None, None)

    def test_derived_plans_are_not_editable(self, rates):
        derived = DerivedRatePlanFactory(property=rates.prop, parent=rates.plan)
        with pytest.raises(DomainError) as exc:
            set_daily_rates(
                property=rates.prop,
                room_type=rates.room_type,
                rate_plan=derived,
                start=oct_(1),
                end=oct_(2),
                price=D("1"),
            )
        assert exc.value.code == "derived_plan_not_editable"

    @pytest.mark.parametrize(
        ("kwargs", "code"),
        [
            ({"price": D("-1")}, "invalid_price"),
            ({"dow": [7]}, "invalid_dow"),
            ({"restrictions": {"min_los": 0}}, "invalid_restriction"),
            ({"restrictions": {"max_los": -2}}, "invalid_restriction"),
            ({"restrictions": {"stop_sell": "sí"}}, "invalid_restriction"),
            ({"restrictions": {"cta": True}}, "invalid_restriction"),
        ],
    )
    def test_invalid_values_are_rejected(self, rates, kwargs, code):
        with pytest.raises(DomainError) as exc:
            write(rates, **kwargs)
        assert exc.value.code == code
        assert not DailyRate.objects.exists()

    def test_nothing_matching_the_filter_writes_nothing(
        self, rates, capture_rates_changed, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            assert write(rates, price=D("1"), dow=[6]) == 0  # 1–2 Oct are Thursday and Friday
        assert (DailyRate.objects.count(), AuditEvent.objects.count(), capture_rates_changed) == (0, 0, [])


class TestRatesChanged:
    def test_lists_the_base_plan_and_its_derived_plans_with_the_range(
        self, rates, capture_rates_changed, django_capture_on_commit_callbacks
    ):
        non_refundable = DerivedRatePlanFactory(property=rates.prop, parent=rates.plan)
        with django_capture_on_commit_callbacks(execute=True):
            write(rates, start=oct_(1), end=oct_(8), price=D("300000"))
        assert capture_rates_changed == [
            {
                "property": rates.prop,
                "room_type_ids": [rates.room_type.pk],
                "rate_plan_ids": [rates.plan.pk, non_refundable.pk],
                "start": oct_(1),
                "end": oct_(8),
            }
        ]


class TestAuditAndUndo:
    def test_each_write_is_one_reversible_audit_event(self, rates, owner):
        DailyRateFactory(room_type=rates.room_type, rate_plan=rates.plan, date=oct_(1), price=D("350000"))
        write(rates, price=D("300000"), actor=owner)
        event = AuditEvent.objects.get(action="rates.bulk_update")
        assert (event.reversible, event.actor, event.source, event.property) == (
            True,
            owner,
            "user",
            rates.prop,
        )
        assert (event.target_type, event.target_id) == ("rates.rateplan", str(rates.plan.pk))
        assert event.summary
        before = {item["date"]: item["before"] for item in event.undo_data["rows"]}
        assert before["2026-10-02"] is None  # created by this write
        assert before["2026-10-01"]["price"] == "350000.00"
        assert {item["after"]["price"] for item in event.undo_data["rows"]} == {"300000.00"}

    @pytest.mark.parametrize(("source", "audit_source"), [("revenue", "automation"), ("channel", "channel")])
    def test_writes_without_a_user_are_attributed_to_their_origin(self, rates, source, audit_source):
        write(rates, price=D("300000"), source=source)
        assert AuditEvent.objects.get(action="rates.bulk_update").source == audit_source

    def test_undo_restores_the_previous_rows_and_removes_the_created_ones(self, rates, owner):
        DailyRateFactory(
            room_type=rates.room_type,
            rate_plan=rates.plan,
            date=oct_(1),
            price=D("350000"),
            min_los=2,
            source="manual",
        )
        write(rates, price=D("300000"), restrictions={"min_los": 4, "stop_sell": True}, source="bulk")
        audit.undo(AuditEvent.objects.get(action="rates.bulk_update"), actor=owner)
        restored = rows(rates)
        assert list(restored) == [oct_(1)]
        first = restored[oct_(1)]
        assert (first.price, first.min_los, first.stop_sell, first.source) == (
            D("350000.00"),
            2,
            False,
            "manual",
        )
        result = quote(
            property=rates.prop,
            room_type=rates.room_type,
            rate_plan=rates.plan,
            checkin=oct_(2),
            checkout=oct_(3),
            adults=2,
        )
        assert (result.subtotal, result.restrictions_ok) == (D("320000"), True)

    def test_undo_emits_rates_changed(
        self, rates, owner, capture_rates_changed, django_capture_on_commit_callbacks
    ):
        write(rates, price=D("300000"))
        with django_capture_on_commit_callbacks(execute=True):
            audit.undo(AuditEvent.objects.get(action="rates.bulk_update"), actor=owner)
        assert capture_rates_changed == [
            {
                "property": rates.prop,
                "room_type_ids": [rates.room_type.pk],
                "rate_plan_ids": [rates.plan.pk],
                "start": oct_(1),
                "end": oct_(3),
            }
        ]

    def test_undo_is_refused_when_the_rows_changed_afterwards(self, rates, owner):
        write(rates, price=D("300000"))
        first = AuditEvent.objects.get(action="rates.bulk_update")
        write(rates, start=oct_(2), end=oct_(3), price=D("310000"))
        with pytest.raises(audit.UndoError) as exc:
            audit.undo(first, actor=owner)
        assert exc.value.code == "undo_conflict"
        first.refresh_from_db()
        assert first.undone_at is None
        assert [r.price for r in rows(rates).values()] == [D("300000.00"), D("310000.00")]


class TestBulkUpdate:
    def test_several_categories_share_one_audit_event_and_one_undo(self, rates, owner):
        suite = RoomTypeFactory(property=rates.prop, code="STE")
        rates.plan.room_types.add(suite)
        RoomTypeRateDefaultsFactory(room_type=suite, rate_plan=rates.plan, price=D("650000"))
        result = bulk_update_rates(
            property=rates.prop,
            room_types=[rates.room_type, suite],
            rate_plan=rates.plan,
            start=oct_(1),
            end=oct_(3),
            restrictions={"price_delta_percent": 10},
            actor=owner,
        )
        assert result.updated == 4
        assert AuditEvent.objects.filter(action="rates.bulk_update").get() == result.event
        assert [r.price for r in rows(rates, suite).values()] == [D("715000.00")] * 2
        assert {r.source for r in DailyRate.objects.all()} == {"bulk"}
        audit.undo(result.event, actor=owner)
        assert not DailyRate.objects.exists()
