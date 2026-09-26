"""Phase A quote engine (plan Step 5): DailyRate of the base plan → RoomTypeRateDefaults.price → 0; derived
%/amount; active room taxes (excluded add up, included are informative) with foreign non-resident exemption;
stop_sell is a violation. Seasons, DOW, occupancy extras and promos arrive with B2a."""

from datetime import date
from decimal import Decimal

import pytest

from apps.core.errors import DomainError
from apps.core.signals import rates_changed
from apps.inventory.tests.factories import RoomTypeFactory
from apps.rates.models import DailyRate
from apps.rates.services.quote import quote, resolve_daily, set_daily_rates
from apps.rates.tests.factories import (
    DailyRateFactory,
    DerivedRatePlanFactory,
    RatePlanFactory,
    RoomTypeRateDefaultsFactory,
    TaxFactory,
)

pytestmark = pytest.mark.django_db

OCT = lambda day: date(2026, 10, day)  # noqa: E731


@pytest.fixture
def setup(prop):
    room_type = RoomTypeFactory(property=prop, code="DBL")
    plan = RatePlanFactory(property=prop, code="FLEX", room_types=[room_type])
    RoomTypeRateDefaultsFactory(
        room_type=room_type,
        rate_plan=plan,
        price=Decimal("320000"),
        extra_adult_price=Decimal("60000"),
        extra_child_price=Decimal("30000"),
    )
    tax = TaxFactory(
        property=prop,
        code="IVA",
        rate=Decimal("19.00"),
        applies_to="room",
        included_in_price=False,
        exempt_foreign_non_residents=True,
    )
    return {"prop": prop, "room_type": room_type, "plan": plan, "tax": tax}


CHECKIN, CHECKOUT = OCT(1), OCT(3)


def run_quote(setup, *, plan=None, checkin=CHECKIN, checkout=CHECKOUT, **kwargs):
    return quote(
        property=setup["prop"],
        room_type=setup["room_type"],
        rate_plan=plan or setup["plan"],
        checkin=checkin,
        checkout=checkout,
        adults=2,
        **kwargs,
    )


class TestQuote:
    def test_defaults_price_every_night_and_taxes_add_up(self, setup):
        result = run_quote(setup)
        assert [n.total for n in result.nights] == [Decimal("320000"), Decimal("320000")]
        assert [n.date for n in result.nights] == [OCT(1), OCT(2)]
        assert result.subtotal == Decimal("640000")
        assert [(t.code, t.amount, t.included, t.exempt) for t in result.taxes] == [
            ("IVA", Decimal("121600"), False, False)
        ]
        assert (result.tax_total, result.total, result.currency) == (
            Decimal("121600"),
            Decimal("761600"),
            "COP",
        )
        assert (result.restrictions_ok, result.violations, result.promo_applied) == (True, [], None)
        assert (result.room_type_id, result.rate_plan_id) == (setup["room_type"].pk, setup["plan"].pk)
        assert (result.checkin, result.checkout, result.adults, result.children) == (OCT(1), OCT(3), 2, 0)

    def test_a_daily_rate_row_wins_over_the_default(self, setup):
        DailyRateFactory(
            room_type=setup["room_type"], rate_plan=setup["plan"], date=OCT(1), price=Decimal("350000")
        )
        result = run_quote(setup)
        assert [n.base for n in result.nights] == [Decimal("350000"), Decimal("320000")]

    def test_derived_percent_plan_uses_the_parent_prices(self, setup):
        derived = DerivedRatePlanFactory(
            property=setup["prop"],
            parent=setup["plan"],
            derivation_type="percent",
            derivation_value=Decimal("-12"),
        )
        DailyRateFactory(
            room_type=setup["room_type"], rate_plan=setup["plan"], date=OCT(2), price=Decimal("400000")
        )
        result = run_quote(setup, plan=derived)
        assert [n.total for n in result.nights] == [Decimal("281600"), Decimal("352000")]
        assert result.rate_plan_id == derived.pk

    def test_derived_amount_plan_never_goes_below_zero(self, setup):
        plus = DerivedRatePlanFactory(
            property=setup["prop"],
            parent=setup["plan"],
            derivation_type="amount",
            derivation_value=Decimal("35000"),
        )
        minus = DerivedRatePlanFactory(
            property=setup["prop"],
            parent=setup["plan"],
            derivation_type="amount",
            derivation_value=Decimal("-500000"),
        )
        assert run_quote(setup, plan=plus).nights[0].total == Decimal("355000")
        assert run_quote(setup, plan=minus).nights[0].total == Decimal("0")

    def test_prices_are_rounded_half_up_to_whole_pesos(self, setup):
        derived = DerivedRatePlanFactory(
            property=setup["prop"],
            parent=setup["plan"],
            derivation_type="percent",
            derivation_value=Decimal("-12"),
        )
        DailyRateFactory(
            room_type=setup["room_type"], rate_plan=setup["plan"], date=OCT(1), price=Decimal("333333")
        )
        DailyRateFactory(
            room_type=setup["room_type"], rate_plan=setup["plan"], date=OCT(2), price=Decimal("100000.50")
        )
        assert [n.total for n in run_quote(setup, plan=derived).nights] == [
            Decimal("293333"),  # 333333 × 0.88 = 293333.04
            Decimal("88000"),  # 100000.50 × 0.88 = 88000.44
        ]
        assert [n.total for n in run_quote(setup).nights] == [Decimal("333333"), Decimal("100001")]
        assert run_quote(setup).nights[1].total.as_tuple().exponent == 0

    def test_missing_price_is_zero_with_a_no_rate_warning(self, prop):
        room_type = RoomTypeFactory(property=prop)
        plan = RatePlanFactory(property=prop)
        result = quote(
            property=prop, room_type=room_type, rate_plan=plan, checkin=OCT(1), checkout=OCT(2), adults=1
        )
        assert result.nights[0].total == Decimal("0")
        assert result.violations == ["no_rate"]

    def test_stop_sell_on_any_night_is_a_restriction_violation(self, setup):
        DailyRateFactory(
            room_type=setup["room_type"],
            rate_plan=setup["plan"],
            date=OCT(2),
            price=Decimal("320000"),
            stop_sell=True,
        )
        result = run_quote(setup)
        assert (result.restrictions_ok, result.violations) == (False, ["stop_sell"])

    def test_foreign_non_resident_is_exempt_from_room_iva(self, setup):
        result = run_quote(setup, guest_is_foreign_non_resident=True)
        assert [(t.amount, t.exempt) for t in result.taxes] == [(Decimal("0"), True)]
        assert (result.tax_total, result.total) == (Decimal("0"), Decimal("640000"))

    def test_foreigners_pay_taxes_without_the_exemption_flag(self, setup):
        setup["tax"].exempt_foreign_non_residents = False
        setup["tax"].save()
        assert run_quote(setup, guest_is_foreign_non_resident=True).tax_total == Decimal("121600")

    def test_included_taxes_are_informative_and_do_not_add_up(self, setup):
        setup["tax"].included_in_price = True
        setup["tax"].save()
        result = run_quote(setup)
        assert [(t.amount, t.included) for t in result.taxes] == [
            (Decimal("102185"), True)
        ]  # 640000 − 640000/1.19
        assert (result.tax_total, result.total) == (Decimal("0"), Decimal("640000"))

    def test_only_active_room_taxes_apply(self, setup):
        TaxFactory(property=setup["prop"], code="EXTRAS", applies_to="extras")
        TaxFactory(property=setup["prop"], code="OLD", is_active=False)
        TaxFactory(
            property=setup["prop"],
            code="ALL",
            applies_to="all",
            rate=Decimal("1.00"),
            exempt_foreign_non_residents=False,
        )
        TaxFactory(code="OTHER_HOTEL")
        assert [t.code for t in run_quote(setup).taxes] == ["ALL", "IVA"]

    @pytest.mark.parametrize("checkout", [OCT(1), date(2026, 9, 30)])
    def test_invalid_dates(self, setup, checkout):
        result = run_quote(setup, checkout=checkout)
        assert (result.nights, result.total, result.restrictions_ok, result.violations) == (
            [],
            Decimal("0"),
            False,
            ["invalid_dates"],
        )


class TestResolveDaily:
    def test_one_day_rate_per_night_from_row_or_defaults(self, setup):
        DailyRateFactory(
            room_type=setup["room_type"],
            rate_plan=setup["plan"],
            date=OCT(2),
            price=Decimal("350000"),
            min_los=2,
            closed_to_arrival=True,
            extra_adult_price=Decimal("70000"),
        )
        days = resolve_daily(setup["room_type"], setup["plan"], OCT(1), OCT(4))
        assert [(d.date, d.price, d.source) for d in days] == [
            (OCT(1), Decimal("320000"), "default"),
            (OCT(2), Decimal("350000"), "manual"),
            (OCT(3), Decimal("320000"), "default"),
        ]
        assert (days[1].min_los, days[1].closed_to_arrival, days[1].stop_sell) == (2, True, False)
        assert (days[1].extra_adult_price, days[1].extra_child_price) == (Decimal("70000"), Decimal("30000"))
        assert (days[0].min_los, days[0].max_los, days[0].extra_adult_price) == (None, None, Decimal("60000"))

    def test_without_any_price_the_source_is_none(self, prop):
        days = resolve_daily(RoomTypeFactory(property=prop), RatePlanFactory(property=prop), OCT(1), OCT(2))
        assert [(d.price, d.source) for d in days] == [(Decimal("0"), "none")]


class TestSetDailyRates:
    def test_sets_the_price_for_every_night_of_the_half_open_range(self, setup, owner):
        count = set_daily_rates(
            property=setup["prop"],
            room_type=setup["room_type"],
            rate_plan=setup["plan"],
            start=OCT(1),
            end=OCT(4),
            price=Decimal("300000"),
            actor=owner,
        )
        assert count == 3
        rows = DailyRate.objects.filter(room_type=setup["room_type"], rate_plan=setup["plan"]).order_by(
            "date"
        )
        assert [(r.date, r.price, r.source, r.updated_by) for r in rows] == [
            (OCT(d), Decimal("300000"), "manual", owner) for d in (1, 2, 3)
        ]

    def test_weekday_filter_uses_monday_zero(self, setup):
        # 2026-10-03 is a Saturday, 2026-10-04 a Sunday
        count = set_daily_rates(
            property=setup["prop"],
            room_type=setup["room_type"],
            rate_plan=setup["plan"],
            start=OCT(1),
            end=OCT(8),
            price=Decimal("380000"),
            dow=[5, 6],
            source="bulk",
        )
        assert count == 2
        assert sorted(DailyRate.objects.values_list("date", "source")) == [(OCT(3), "bulk"), (OCT(4), "bulk")]

    def test_restrictions_keep_the_resolved_price(self, setup):
        DailyRateFactory(
            room_type=setup["room_type"], rate_plan=setup["plan"], date=OCT(1), price=Decimal("350000")
        )
        set_daily_rates(
            property=setup["prop"],
            room_type=setup["room_type"],
            rate_plan=setup["plan"],
            start=OCT(1),
            end=OCT(3),
            restrictions={"min_los": 2, "stop_sell": True},
        )
        rows = {r.date: r for r in DailyRate.objects.all()}
        assert (rows[OCT(1)].price, rows[OCT(1)].min_los, rows[OCT(1)].stop_sell) == (
            Decimal("350000"),
            2,
            True,
        )
        assert (rows[OCT(2)].price, rows[OCT(2)].min_los) == (Decimal("320000"), 2)

    def test_relative_price_changes(self, setup):
        set_daily_rates(
            property=setup["prop"],
            room_type=setup["room_type"],
            rate_plan=setup["plan"],
            start=OCT(1),
            end=OCT(2),
            restrictions={"price_delta_percent": 10},
        )
        set_daily_rates(
            property=setup["prop"],
            room_type=setup["room_type"],
            rate_plan=setup["plan"],
            start=OCT(1),
            end=OCT(2),
            restrictions={"price_delta_amount": -2000},
        )
        assert DailyRate.objects.get(date=OCT(1)).price == Decimal("350000")

    def test_derived_plans_are_not_editable(self, setup):
        derived = DerivedRatePlanFactory(property=setup["prop"], parent=setup["plan"])
        with pytest.raises(DomainError) as exc:
            set_daily_rates(
                property=setup["prop"],
                room_type=setup["room_type"],
                rate_plan=derived,
                start=OCT(1),
                end=OCT(2),
                price=Decimal("1"),
            )
        assert exc.value.code == "derived_plan_not_editable"

    def test_unknown_restriction_keys_are_rejected(self, setup):
        with pytest.raises(DomainError) as exc:
            set_daily_rates(
                property=setup["prop"],
                room_type=setup["room_type"],
                rate_plan=setup["plan"],
                start=OCT(1),
                end=OCT(2),
                restrictions={"cta": True},
            )
        assert exc.value.code == "invalid_restriction"

    def test_emits_rates_changed_after_commit(self, setup, django_capture_on_commit_callbacks):
        received = []

        def receiver(sender, **kwargs):
            received.append(kwargs)

        rates_changed.connect(receiver)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                set_daily_rates(
                    property=setup["prop"],
                    room_type=setup["room_type"],
                    rate_plan=setup["plan"],
                    start=OCT(1),
                    end=OCT(3),
                    price=Decimal("1"),
                )
        finally:
            rates_changed.disconnect(receiver)
        assert received == [
            {
                "signal": rates_changed,
                "property": setup["prop"],
                "room_type_ids": [setup["room_type"].pk],
                "rate_plan_ids": [setup["plan"].pk],
                "start": OCT(1),
                "end": OCT(3),
            }
        ]
