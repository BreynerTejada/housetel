"""Quote engine (plan B2a, normative algorithm): one test per rule.

Fixture `rates`: DBL (base occupancy 2) in the base plan FLEX, defaults 320.000 / extra adult 60.000 /
child 30.000 (≤ 12), IVA 19 % excluded and exempt for foreign non-residents. 2026-10-01 is a Thursday.
Expected values are computed by hand in the comments.
"""

from datetime import date
from decimal import Decimal

import pytest
from freezegun import freeze_time

from apps.inventory.tests.factories import DormRoomTypeFactory
from apps.rates.models import PromoCode, Season, SeasonRate
from apps.rates.services.quote import quote
from apps.rates.tests.conftest import oct_
from apps.rates.tests.factories import (
    DailyRateFactory,
    DerivedRatePlanFactory,
    RatePlanFactory,
    RoomTypeRateDefaultsFactory,
    TaxFactory,
)

pytestmark = pytest.mark.django_db

D = Decimal


def run(rates, *, plan=None, room_type=None, checkin=None, checkout=None, adults=2, **kwargs):
    return quote(
        property=rates.prop,
        room_type=room_type or rates.room_type,
        rate_plan=plan or rates.plan,
        checkin=checkin or oct_(1),
        checkout=checkout or oct_(3),
        adults=adults,
        **kwargs,
    )


def bases(result):
    return [night.base for night in result.nights]


def totals(result):
    return [night.total for night in result.nights]


def season(rates, *, start, end, price, priority=0, dow=None, room_type=None, name="Temporada"):
    item = Season.objects.create(
        property=rates.prop, name=name, start_date=start, end_date=end, priority=priority
    )
    SeasonRate.objects.create(
        season=item,
        room_type=room_type or rates.room_type,
        rate_plan=rates.plan,
        price=D(price),
        dow_adjustments=dow or {},
    )
    return item


def row(rates, day, **fields):
    fields.setdefault("price", D("320000"))
    return DailyRateFactory(room_type=rates.room_type, rate_plan=rates.plan, date=day, **fields)


def derived(rates, kind="percent", value="-12", **kwargs):
    return DerivedRatePlanFactory(
        property=rates.prop,
        parent=rates.plan,
        derivation_type=kind,
        derivation_value=D(value),
        room_types=[rates.room_type],
        **kwargs,
    )


# --- 3. base price per night: DailyRate → SeasonRate → defaults (+ weekday adjustments) → no_rate -------


class TestBasePrice:
    def test_defaults_price_every_night(self, rates):
        result = run(rates)
        assert [n.date for n in result.nights] == [oct_(1), oct_(2)]
        assert bases(result) == [D("320000"), D("320000")]
        assert (result.subtotal, result.restrictions_ok, result.violations) == (D("640000"), True, [])

    def test_weekday_adjustments_of_the_defaults(self, rates):
        rates.defaults.dow_adjustments = {"fri": 10, "sat": 15}
        rates.defaults.save()
        # Thu 320.000 · Fri 320.000 × 1.10 · Sat 320.000 × 1.15
        assert bases(run(rates, checkout=oct_(4))) == [D("320000"), D("352000"), D("368000")]

    def test_a_season_rate_wins_over_the_defaults(self, rates):
        season(rates, start=oct_(2), end=oct_(2), price="400000")
        assert bases(run(rates)) == [D("320000"), D("400000")]

    def test_season_end_date_is_inclusive(self, rates):
        season(rates, start=oct_(1), end=oct_(2), price="400000")
        assert bases(run(rates, checkout=oct_(4))) == [D("400000"), D("400000"), D("320000")]

    def test_the_active_season_with_the_highest_priority_wins(self, rates):
        season(rates, start=oct_(1), end=oct_(31), price="400000", priority=1, name="Octubre")
        season(rates, start=oct_(2), end=oct_(2), price="500000", priority=5, name="Puente")
        other = DormRoomTypeFactory(property=rates.prop)
        # a higher-priority season without a rate for DBL does not hide the others
        season(rates, start=oct_(1), end=oct_(1), price="999999", priority=9, room_type=other)
        assert bases(run(rates)) == [D("400000"), D("500000")]

    def test_weekday_adjustments_of_a_season_rate(self, rates):
        season(rates, start=oct_(1), end=oct_(31), price="400000", dow={"fri": 25})
        assert bases(run(rates)) == [D("400000"), D("500000")]  # Fri: 400.000 × 1.25

    def test_a_manual_daily_rate_wins_over_the_season(self, rates):
        season(rates, start=oct_(1), end=oct_(2), price="400000")
        row(rates, oct_(2), price=D("380000"))
        assert bases(run(rates)) == [D("400000"), D("380000")]

    def test_daily_rates_ignore_weekday_adjustments(self, rates):
        rates.defaults.dow_adjustments = {"fri": 10}
        rates.defaults.save()
        row(rates, oct_(2), price=D("300000"))
        assert bases(run(rates)) == [D("320000"), D("300000")]

    def test_without_any_price_the_night_is_zero_with_a_no_rate_warning(self, prop):
        room_type = DormRoomTypeFactory(property=prop)
        plan = RatePlanFactory(property=prop, room_types=[room_type])
        result = quote(
            property=prop, room_type=room_type, rate_plan=plan, checkin=oct_(1), checkout=oct_(2), adults=1
        )
        assert (totals(result), result.violations, result.restrictions_ok) == ([D("0")], ["no_rate"], True)

    def test_the_sum_of_several_nights_mixes_every_source(self, rates):
        rates.defaults.dow_adjustments = {"sat": 50}
        rates.defaults.save()
        season(rates, start=oct_(2), end=oct_(2), price="400000")
        row(rates, oct_(3), price=D("380000"))  # manual row: no weekday adjustment
        result = run(rates, checkout=oct_(4), adults=3)
        # Thu default 320.000, Fri season 400.000, Sat manual 380.000; + 1 extra adult × 60.000 each night
        assert totals(result) == [D("380000"), D("460000"), D("440000")]
        assert (result.subtotal, result.tax_total, result.total) == (D("1280000"), D("243200"), D("1523200"))


@pytest.mark.parametrize(("checkout"), [oct_(1), date(2026, 9, 30)])
def test_invalid_dates_have_no_nights(rates, checkout):
    result = run(rates, checkout=checkout)
    assert (result.nights, result.total, result.restrictions_ok, result.violations) == (
        [],
        D("0"),
        False,
        ["invalid_dates"],
    )


# --- 4. derived plans --------------------------------------------------------------------------------


class TestDerivedPlans:
    def test_percent_derivation_applies_to_the_base_plan_price(self, rates):
        season(rates, start=oct_(2), end=oct_(2), price="400000")
        result = run(rates, plan=derived(rates, "percent", "-12"))
        assert bases(result) == [D("281600"), D("352000")]  # 320.000 × 0.88 · 400.000 × 0.88
        assert result.rate_plan_id != rates.plan.pk

    def test_amount_derivation_adds_the_amount(self, rates):
        assert bases(run(rates, plan=derived(rates, "amount", "35000"))) == [D("355000"), D("355000")]

    def test_amount_derivation_never_goes_below_zero(self, rates):
        assert bases(run(rates, plan=derived(rates, "amount", "-500000"))) == [D("0"), D("0")]


# --- 5. occupancy --------------------------------------------------------------------------------------


class TestOccupancy:
    def test_base_occupancy_has_no_extras(self, rates):
        night = run(rates, adults=2).nights[0]
        assert (night.extra_adults, night.extra_children, night.total) == (D("0"), D("0"), D("320000"))

    def test_adults_above_base_occupancy_pay_the_extra_adult_price(self, rates):
        result = run(rates, adults=3)
        assert [n.extra_adults for n in result.nights] == [D("60000"), D("60000")]
        assert totals(result) == [D("380000"), D("380000")]

    def test_the_extra_adult_price_of_a_daily_rate_row_wins(self, rates):
        row(rates, oct_(2), price=D("320000"), extra_adult_price=D("70000"))
        assert [n.extra_adults for n in run(rates, adults=3).nights] == [D("60000"), D("70000")]

    def test_children_up_to_the_age_limit_pay_the_child_price_and_older_ones_count_as_adults(self, rates):
        night = run(rates, adults=2, children=3, children_ages=[5, 12, 13]).nights[0]
        # ages 5 and 12 → 2 × 30.000; the 13-year-old is the third adult → 1 × 60.000
        assert (night.extra_children, night.extra_adults, night.total) == (
            D("60000"),
            D("60000"),
            D("440000"),
        )

    def test_the_age_limit_comes_from_the_defaults(self, rates):
        rates.defaults.child_age_limit = 4
        rates.defaults.save()
        night = run(rates, adults=2, children=1, children_ages=[5]).nights[0]
        assert (night.extra_children, night.extra_adults) == (D("0"), D("60000"))

    def test_a_child_without_age_is_charged_as_a_child(self, rates):
        night = run(rates, adults=2, children=1).nights[0]
        assert (night.extra_children, night.extra_adults) == (D("30000"), D("0"))

    def test_single_occupancy_price_replaces_the_base_price(self, rates):
        rates.defaults.single_occupancy_price = D("250000")
        rates.defaults.save()
        assert bases(run(rates, adults=1)) == [D("250000"), D("250000")]
        assert bases(run(rates, adults=2)) == [D("320000"), D("320000")]

    def test_single_occupancy_follows_the_weekday_adjustments(self, rates):
        rates.defaults.single_occupancy_price = D("250000")
        rates.defaults.dow_adjustments = {"sat": 15}
        rates.defaults.save()
        # Fri 2 Oct: 250.000; Sat 3 Oct: 250.000 × 1.15 = 287.500 (a couple pays 320.000 × 1.15 = 368.000)
        assert bases(run(rates, checkin=oct_(2), checkout=oct_(4), adults=1)) == [D("250000"), D("287500")]

    def test_single_occupancy_keeps_its_proportion_on_season_and_manual_nights(self, rates):
        rates.defaults.single_occupancy_price = D("250000")
        rates.defaults.save()
        season(rates, start=oct_(1), end=oct_(1), price="400000")
        row(rates, oct_(2), price=D("200000"))
        # single / default = 250.000 / 320.000: 400.000 → 312.500 and 200.000 → 156.250 (never above a couple)
        assert bases(run(rates, adults=1)) == [D("312500"), D("156250")]

    def test_single_occupancy_is_derived_like_the_base_price(self, rates):
        rates.defaults.single_occupancy_price = D("250000")
        rates.defaults.save()
        assert bases(run(rates, plan=derived(rates, "percent", "-12"), adults=1)) == [D("220000")] * 2

    def test_without_single_occupancy_price_one_adult_pays_the_base_price(self, rates):
        assert bases(run(rates, adults=1)) == [D("320000"), D("320000")]

    def test_dorm_prices_one_person_per_bed_without_extras(self, prop):
        dorm = DormRoomTypeFactory(property=prop)
        plan = RatePlanFactory(property=prop, room_types=[dorm])
        RoomTypeRateDefaultsFactory(
            room_type=dorm,
            rate_plan=plan,
            price=D("65000"),
            extra_adult_price=D("60000"),
            extra_child_price=D("30000"),
            single_occupancy_price=D("50000"),
        )
        result = quote(
            property=prop,
            room_type=dorm,
            rate_plan=plan,
            checkin=oct_(1),
            checkout=oct_(3),
            adults=3,
            children=1,
        )
        assert [(n.base, n.extra_adults, n.extra_children, n.total) for n in result.nights] == [
            (D("65000"), D("0"), D("0"), D("65000"))
        ] * 2


# --- 6. promo codes ------------------------------------------------------------------------------------


def promo(rates, code="BIENVENIDA10", **fields):
    fields.setdefault("discount_type", "percent")
    fields.setdefault("value", D("10"))
    plans = fields.pop("rate_plans", None)
    item = PromoCode.objects.create(property=rates.prop, code=code, **fields)
    if plans:
        item.rate_plans.set(plans)
    return item


@freeze_time("2026-09-25 12:00:00-05:00")
class TestPromoCodes:
    def test_a_valid_percent_promo_discounts_every_night(self, rates):
        promo(rates, valid_from=date(2026, 9, 1), valid_to=date(2026, 12, 31))
        result = run(rates, promo_code="BIENVENIDA10")
        assert [n.discount for n in result.nights] == [D("32000"), D("32000")]
        assert totals(result) == [D("288000"), D("288000")]
        assert (result.subtotal, result.discount_total, result.tax_total, result.total) == (
            D("576000"),
            D("64000"),
            D("109440"),  # 576.000 × 19 %
            D("685440"),
        )
        assert (result.promo_applied, result.violations, result.restrictions_ok) == ("BIENVENIDA10", [], True)

    def test_an_amount_promo_discounts_each_night_without_going_below_zero(self, rates):
        promo(rates, code="MENOS50", discount_type="amount", value=D("50000"))
        promo(rates, code="GRATIS", discount_type="amount", value=D("400000"))
        assert totals(run(rates, promo_code="MENOS50")) == [D("270000"), D("270000")]
        result = run(rates, promo_code="GRATIS")
        assert ([n.discount for n in result.nights], result.subtotal) == ([D("320000")] * 2, D("0"))

    def test_the_code_is_matched_without_case_or_spaces(self, rates):
        promo(rates)
        assert run(rates, promo_code="  bienvenida10 ").promo_applied == "BIENVENIDA10"

    def test_an_expired_promo_is_reported_without_blocking(self, rates):
        promo(rates, valid_to=date(2026, 9, 24))
        result = run(rates, promo_code="BIENVENIDA10")
        assert (result.promo_applied, result.discount_total, result.subtotal) == (None, D("0"), D("640000"))
        assert (result.violations, result.restrictions_ok) == (["promo_invalid"], True)

    def test_a_promo_whose_booking_window_has_not_started_is_invalid(self, rates):
        promo(rates, valid_from=date(2026, 9, 26))
        assert run(rates, promo_code="BIENVENIDA10").violations == ["promo_invalid"]

    def test_only_nights_inside_the_stay_window_get_the_discount(self, rates):
        promo(rates, stay_from=oct_(2), stay_to=oct_(31))
        result = run(rates, promo_code="BIENVENIDA10")
        assert ([n.discount for n in result.nights], result.promo_applied) == (
            [D("0"), D("32000")],
            "BIENVENIDA10",
        )

    def test_a_promo_without_any_night_in_its_stay_window_is_invalid(self, rates):
        promo(rates, stay_from=date(2026, 11, 1), stay_to=date(2026, 11, 30))
        result = run(rates, promo_code="BIENVENIDA10")
        assert (result.violations, result.discount_total) == (["promo_invalid"], D("0"))

    def test_a_promo_limited_to_other_plans_is_invalid(self, rates):
        non_refundable = derived(rates)
        promo(rates, rate_plans=[non_refundable])
        assert run(rates, promo_code="BIENVENIDA10").violations == ["promo_invalid"]
        assert run(rates, plan=non_refundable, promo_code="BIENVENIDA10").promo_applied == "BIENVENIDA10"

    @pytest.mark.parametrize(("uses", "applied"), [(5, None), (4, "BIENVENIDA10")])
    def test_a_promo_with_its_uses_exhausted_is_invalid(self, rates, uses, applied):
        promo(rates, max_uses=5, uses=uses)
        assert run(rates, promo_code="BIENVENIDA10").promo_applied == applied

    def test_inactive_unknown_or_foreign_promos_are_invalid(self, rates):
        promo(rates, code="VIEJA", is_active=False)
        PromoCode.objects.create(
            property=RatePlanFactory().property, code="OTROHOTEL", discount_type="percent", value=D("50")
        )
        for code in ("VIEJA", "NOEXISTE", "OTROHOTEL"):
            result = run(rates, promo_code=code)
            assert (result.violations, result.promo_applied, result.subtotal) == (
                ["promo_invalid"],
                None,
                D("640000"),
            ), code


# --- 7. restrictions (rows of the base plan) -------------------------------------------------------------


class TestRestrictions:
    def test_stop_sell_on_any_night(self, rates):
        row(rates, oct_(2), stop_sell=True)
        result = run(rates)
        assert (result.restrictions_ok, result.violations) == (False, ["stop_sell"])

    def test_closed_to_arrival_on_the_checkin_night(self, rates):
        row(rates, oct_(1), closed_to_arrival=True)
        assert (run(rates).restrictions_ok, run(rates).violations) == (False, ["cta"])

    def test_closed_to_arrival_on_a_later_night_does_not_apply(self, rates):
        row(rates, oct_(2), closed_to_arrival=True)
        assert run(rates).restrictions_ok is True

    def test_closed_to_departure_on_the_checkout_date(self, rates):
        row(rates, oct_(3), price=D("999999"), closed_to_departure=True)
        result = run(rates)
        assert (result.restrictions_ok, result.violations) == (False, ["ctd"])
        assert result.subtotal == D("640000")  # the checkout date is not a night of the stay

    def test_closed_to_departure_on_a_night_of_the_stay_does_not_apply(self, rates):
        row(rates, oct_(2), closed_to_departure=True)
        assert run(rates).restrictions_ok is True

    def test_min_los_of_the_arrival_night(self, rates):
        row(rates, oct_(1), min_los=3)
        assert run(rates).violations == ["min_los"]
        assert run(rates, checkout=oct_(4)).restrictions_ok is True

    def test_min_los_of_a_later_night_does_not_apply(self, rates):
        row(rates, oct_(2), min_los=5)
        assert run(rates).restrictions_ok is True

    def test_min_los_default_of_the_plan_applies_without_a_row_value(self, rates):
        rates.plan.min_los_default = 2
        rates.plan.save()
        assert run(rates, checkout=oct_(2)).violations == ["min_los"]
        row(rates, oct_(1), min_los=1)  # the row wins over the plan default
        assert run(rates, checkout=oct_(2)).restrictions_ok is True

    def test_max_los_of_the_arrival_night(self, rates):
        row(rates, oct_(1), max_los=2)
        assert run(rates, checkout=oct_(4)).violations == ["max_los"]
        assert run(rates, checkout=oct_(3)).restrictions_ok is True

    def test_derived_plans_use_the_restrictions_of_their_base_plan(self, rates):
        row(rates, oct_(1), closed_to_arrival=True)
        assert run(rates, plan=derived(rates)).violations == ["cta"]

    def test_several_violations_are_reported_in_a_stable_order(self, rates):
        row(rates, oct_(1), closed_to_arrival=True, min_los=4, stop_sell=True)
        row(rates, oct_(3), closed_to_departure=True)
        assert run(rates).violations == ["stop_sell", "cta", "ctd", "min_los"]


# --- 8. taxes ----------------------------------------------------------------------------------------


class TestTaxes:
    def test_excluded_taxes_add_up(self, rates):
        result = run(rates)
        assert [(t.code, t.rate, t.amount, t.included, t.exempt) for t in result.taxes] == [
            ("IVA", D("19.00"), D("121600"), False, False)  # 640.000 × 19 %
        ]
        assert (result.tax_total, result.total, result.currency) == (D("121600"), D("761600"), "COP")

    def test_included_taxes_are_informative(self, rates):
        rates.tax.included_in_price = True
        rates.tax.save()
        result = run(rates)
        # 640.000 − 640.000 / 1.19 = 102.184,87 → 102.185
        assert [(t.amount, t.included) for t in result.taxes] == [(D("102185"), True)]
        assert (result.tax_total, result.total) == (D("0"), D("640000"))

    def test_foreign_non_residents_are_exempt(self, rates):
        result = run(rates, guest_is_foreign_non_resident=True)
        assert [(t.amount, t.exempt) for t in result.taxes] == [(D("0"), True)]
        assert (result.tax_total, result.total) == (D("0"), D("640000"))

    def test_the_exemption_needs_the_tax_flag(self, rates):
        rates.tax.exempt_foreign_non_residents = False
        rates.tax.save()
        assert run(rates, guest_is_foreign_non_resident=True).tax_total == D("121600")

    def test_only_active_lodging_taxes_apply(self, rates):
        TaxFactory(property=rates.prop, code="EXTRAS", applies_to="extras")
        TaxFactory(property=rates.prop, code="OLD", is_active=False)
        TaxFactory(property=rates.prop, code="ALL", applies_to="all", rate=D("1.00"))
        TaxFactory(code="OTHER_HOTEL")
        assert [t.code for t in run(rates).taxes] == ["ALL", "IVA"]


# --- 9. rounding ------------------------------------------------------------------------------------


class TestRounding:
    def test_nights_and_taxes_round_half_up_to_whole_pesos(self, rates):
        rates.defaults.price = D("333333")
        rates.defaults.save()
        result = run(rates, plan=derived(rates, "percent", "-12"), checkout=oct_(2))
        # 333.333 × 0.88 = 293.333,04 → 293.333 · IVA 293.333 × 19 % = 55.733,27 → 55.733
        assert (result.subtotal, result.tax_total, result.total) == (D("293333"), D("55733"), D("349066"))

    def test_exact_halves_round_up(self, rates):
        rates.defaults.price = D("100001")
        rates.defaults.save()
        assert bases(run(rates, plan=derived(rates, "percent", "-50"), checkout=oct_(2))) == [D("50001")]

    def test_every_amount_is_a_whole_peso(self, rates):
        rates.defaults.price = D("333333")
        rates.defaults.dow_adjustments = {"thu": 7.5}
        rates.defaults.save()
        night = run(rates, checkout=oct_(2), adults=3, children=1).nights[0]
        assert night.base == D("358333")  # 333.333 × 1.075 = 358.332,975
        assert all(
            value.as_tuple().exponent == 0
            for value in (night.base, night.extra_adults, night.extra_children, night.discount, night.total)
        )
