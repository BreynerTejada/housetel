"""Rule params (validation + normalization) and the evaluation of each rule kind for one night.

Pure functions: no database. 2026-10-12 is a Monday holiday in Colombia (Día de la Raza), so the nights of
Saturday 10 and Sunday 11 are the "puente" (long weekend)."""

from datetime import date
from decimal import Decimal

import pytest

from apps.core.errors import DomainError
from apps.revenue.rules import NightFacts, clean_params, evaluate, holiday_facts

D = Decimal


def night(day=date(2026, 10, 14), *, lead=13, occupancy=None, holiday=None, bridge=None):
    return NightFacts(date=day, lead_days=lead, occupancy=occupancy, holiday=holiday, bridge=bridge)


def invalid(kind, params) -> str:
    with pytest.raises(DomainError) as exc:
        clean_params(kind, params)
    assert exc.value.code == "invalid_rule_params"
    return exc.value.message


class TestOccupancy:
    PARAMS = {
        "tiers": [
            {"min": 85, "max": 100, "adjust": 15},
            {"min": 0, "max": 40, "adjust": -8},
            {"min": 70, "max": 85, "adjust": "8"},
        ]
    }

    def test_tiers_are_sorted_and_numbers_normalized(self):
        assert clean_params("occupancy", self.PARAMS) == {
            "tiers": [
                {"min": 0, "max": 40, "adjust": -8},
                {"min": 70, "max": 85, "adjust": 8},
                {"min": 85, "max": 100, "adjust": 15},
            ]
        }

    @pytest.mark.parametrize(
        ("occupancy", "adjust"),
        [
            (D("0"), D("-8")),
            (D("39.99"), D("-8")),
            (D("40"), None),  # max is exclusive
            (D("69.99"), None),
            (D("70"), D("8")),
            (D("84.99"), D("8")),
            (D("85"), D("15")),  # a boundary belongs to the upper tier
            (D("100"), D("15")),  # the top tier includes 100 %
            (None, None),  # nothing to sell that night
        ],
    )
    def test_the_tier_of_the_night_occupancy_applies(self, occupancy, adjust):
        params = clean_params("occupancy", self.PARAMS)
        hit = evaluate("occupancy", params, night(occupancy=occupancy))
        assert (hit.adjust if hit else None) == adjust
        if hit:
            assert hit.detail == {"occupancy": format(occupancy, "f")}

    @pytest.mark.parametrize(
        "params",
        [
            {},
            {"tiers": []},
            {"tiers": [{"min": 40, "max": 30, "adjust": 5}]},  # min ≥ max
            {"tiers": [{"min": 0, "max": 101, "adjust": 5}]},  # out of 0–100
            {"tiers": [{"min": 0, "max": 50, "adjust": 5}, {"min": 40, "max": 80, "adjust": 9}]},  # overlap
            {"tiers": [{"min": 0, "max": 50, "adjust": -95}]},  # below −90 %
            {"tiers": [{"min": 0, "max": 50, "adjust": "mucho"}]},
            {"tiers": [{"min": 0, "max": 50}]},
        ],
    )
    def test_invalid_tiers_are_rejected(self, params):
        invalid("occupancy", params)


class TestLeadTime:
    PARAMS = {
        "last_minute": [{"max_days": 3, "adjust": -5}, {"max_days": 0, "adjust": -10}],
        "early_bird": [{"min_days": 60, "adjust": 4}, {"min_days": 90, "adjust": 7.5}],
    }

    @pytest.mark.parametrize(
        ("lead", "adjust", "detail"),
        [
            (0, D("-10"), {"lead_days": 0, "window": "last_minute", "days": 0}),  # the tightest window
            (1, D("-5"), {"lead_days": 1, "window": "last_minute", "days": 3}),
            (3, D("-5"), {"lead_days": 3, "window": "last_minute", "days": 3}),
            (4, None, None),
            (59, None, None),
            (60, D("4"), {"lead_days": 60, "window": "early_bird", "days": 60}),
            (120, D("7.5"), {"lead_days": 120, "window": "early_bird", "days": 90}),  # the widest window
        ],
    )
    def test_last_minute_and_early_bird_windows(self, lead, adjust, detail):
        params = clean_params("lead_time", self.PARAMS)
        hit = evaluate("lead_time", params, night(lead=lead))
        assert (hit.adjust if hit else None) == adjust
        assert (hit.detail if hit else None) == detail

    def test_one_window_alone_is_enough(self):
        assert clean_params("lead_time", {"last_minute": [{"max_days": 3, "adjust": -5}]}) == {
            "last_minute": [{"max_days": 3, "adjust": -5}],
            "early_bird": [],
        }

    @pytest.mark.parametrize(
        "params",
        [
            {},
            {"last_minute": [], "early_bird": []},
            {"last_minute": [{"max_days": -1, "adjust": -5}]},
            {"early_bird": [{"min_days": 0, "adjust": 5}]},  # early bird starts tomorrow at the earliest
            {
                "last_minute": [{"max_days": 3, "adjust": -5}, {"max_days": 3, "adjust": -9}]
            },  # repeated window
            {"last_minute": [{"max_days": 30, "adjust": -5}], "early_bird": [{"min_days": 30, "adjust": 5}]},
        ],
    )
    def test_invalid_windows_are_rejected(self, params):
        invalid("lead_time", params)


class TestDayOfWeek:
    def test_the_weekday_of_the_night_applies(self):
        params = clean_params("day_of_week", {"fri": 5, "sat": "10"})
        assert params == {"fri": 5, "sat": 10}
        saturday, sunday = date(2026, 10, 17), date(2026, 10, 18)
        hit = evaluate("day_of_week", params, night(saturday))
        assert (hit.adjust, hit.detail) == (D("10"), {"weekday": "sat"})
        assert evaluate("day_of_week", params, night(sunday)) is None

    def test_a_zero_adjustment_is_no_reason(self):
        params = clean_params("day_of_week", {"sat": 0, "fri": 5})
        assert evaluate("day_of_week", params, night(date(2026, 10, 17))) is None

    @pytest.mark.parametrize("params", [{}, {"sab": 10}, {"sat": 400}, {"sat": None}])
    def test_invalid_weekdays_are_rejected(self, params):
        invalid("day_of_week", params)


class TestHoliday:
    def test_holiday_facts_mark_the_holiday_and_its_long_weekend(self):
        facts = holiday_facts(date(2026, 10, 9), date(2026, 10, 14))
        raza = {"name_es": "Día de la Raza", "name_en": "Columbus Day"}
        assert facts.holidays == {date(2026, 10, 12): raza}
        assert facts.bridges == {date(2026, 10, 10): raza, date(2026, 10, 11): raza}

    def test_a_long_weekend_at_the_edge_of_the_range_is_still_found(self):
        # the Monday holiday itself is outside the range: its Saturday and Sunday are still a bridge
        facts = holiday_facts(date(2026, 10, 10), date(2026, 10, 12))
        assert set(facts.bridges) == {date(2026, 10, 10), date(2026, 10, 11)}

    def test_holiday_and_bridge_nights_get_the_adjustment(self):
        params = clean_params("holiday", {"adjust": 12})
        assert params == {"adjust": 12, "include_bridges": True}
        raza = {"name_es": "Día de la Raza", "name_en": "Columbus Day"}
        holiday = evaluate("holiday", params, night(date(2026, 10, 12), holiday=raza))
        bridge = evaluate("holiday", params, night(date(2026, 10, 10), bridge=raza))
        assert (holiday.adjust, holiday.detail) == (D("12"), {**raza, "bridge": False})
        assert (bridge.adjust, bridge.detail) == (D("12"), {**raza, "bridge": True})
        assert evaluate("holiday", params, night(date(2026, 10, 14))) is None

    def test_bridges_can_be_left_out(self):
        params = clean_params("holiday", {"adjust": 12, "include_bridges": False})
        raza = {"name_es": "Día de la Raza", "name_en": "Columbus Day"}
        assert evaluate("holiday", params, night(date(2026, 10, 10), bridge=raza)) is None

    @pytest.mark.parametrize("params", [{}, {"adjust": 12, "include_bridges": "sí"}, {"adjust": 301}])
    def test_invalid_params_are_rejected(self, params):
        invalid("holiday", params)


class TestEvent:
    PARAMS = {"name": "Festival de Música", "start": "2027-01-08", "end": "2027-01-12", "adjust": 20}

    @pytest.mark.parametrize(
        ("day", "applies"),
        [
            (date(2027, 1, 7), False),
            (date(2027, 1, 8), True),
            (date(2027, 1, 12), True),  # the last day is included
            (date(2027, 1, 13), False),
        ],
    )
    def test_nights_between_start_and_end_inclusive(self, day, applies):
        params = clean_params("event", self.PARAMS)
        hit = evaluate("event", params, night(day))
        assert (hit is not None) == applies
        if hit:
            assert (hit.adjust, hit.detail) == (D("20"), {"name": "Festival de Música"})

    @pytest.mark.parametrize(
        "params",
        [
            {"start": "2027-01-08", "adjust": 20},
            {"start": "2027-01-12", "end": "2027-01-08", "adjust": 20},
            {"start": "08/01/2027", "end": "2027-01-12", "adjust": 20},
            {"start": "2027-01-08", "end": "2028-02-12", "adjust": 20},  # longer than a year
        ],
    )
    def test_invalid_events_are_rejected(self, params):
        invalid("event", params)


def test_an_unknown_kind_is_rejected():
    invalid("weather", {"adjust": 5})


def test_params_must_be_an_object():
    invalid("holiday", ["adjust", 5])
