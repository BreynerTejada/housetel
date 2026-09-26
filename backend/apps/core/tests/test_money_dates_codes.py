import re
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db.models import JSONField
from freezegun import freeze_time

from apps.core.codes import generate_code
from apps.core.dates import daterange, nights, overlaps, property_now
from apps.core.i18n import i18n_field, t
from apps.core.money import D, apply_percent, percent_of, quantize


class TestMoney:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("1234.5", Decimal("1235")),
            ("1234.49", Decimal("1234")),
            ("-0.5", Decimal("-1")),
            (Decimal("350000.00"), Decimal("350000")),
            (19000.19, Decimal("19000")),
        ],
    )
    def test_quantize_cop_rounds_half_up_to_whole_pesos(self, raw, expected):
        result = quantize(raw)
        assert result == expected
        assert result.as_tuple().exponent == 0

    def test_quantize_other_currencies_keep_cents(self):
        assert quantize("10.005", "USD") == Decimal("10.01")
        assert quantize("10.004", "USD").as_tuple().exponent == -2

    def test_D_converts_without_float_noise(self):
        assert D(0.1) == Decimal("0.1")
        assert D("320000") == Decimal("320000")
        assert D(5) == Decimal("5")
        assert D(None) == Decimal("0")
        assert D("") == Decimal("0")

    def test_apply_percent_adjusts_the_amount(self):
        assert apply_percent(Decimal("100000"), 15) == Decimal("115000")
        assert apply_percent("320000", -12) == Decimal("281600")

    def test_percent_of_returns_the_portion(self):
        assert percent_of("640000", "19") == Decimal("121600")


class TestDates:
    def test_nights_include_checkin_and_exclude_checkout(self):
        assert nights(date(2026, 10, 1), date(2026, 10, 4)) == [
            date(2026, 10, 1),
            date(2026, 10, 2),
            date(2026, 10, 3),
        ]

    @pytest.mark.parametrize("checkout", [date(2026, 10, 1), date(2026, 9, 28)])
    def test_nights_are_empty_for_same_day_or_reversed_ranges(self, checkout):
        assert nights(date(2026, 10, 1), checkout) == []

    def test_daterange_is_half_open_and_crosses_years(self):
        assert list(daterange(date(2026, 12, 30), date(2027, 1, 2))) == [
            date(2026, 12, 30),
            date(2026, 12, 31),
            date(2027, 1, 1),
        ]

    @pytest.mark.parametrize(
        ("a", "b", "expected"),
        [
            ((1, 3), (3, 5), False),  # checkout day == next checkin: no overlap
            ((1, 4), (3, 5), True),
            ((3, 5), (1, 4), True),
            ((1, 10), (4, 5), True),
            ((1, 2), (5, 6), False),
        ],
    )
    def test_overlaps_uses_half_open_ranges(self, a, b, expected):
        day = lambda n: date(2026, 10, n)  # noqa: E731
        assert overlaps(day(a[0]), day(a[1]), day(b[0]), day(b[1])) is expected

    def test_property_now_is_expressed_in_the_property_timezone(self):
        prop = SimpleNamespace(timezone="America/Bogota")
        with freeze_time("2026-09-26T03:30:00Z"):
            now = property_now(prop)
        assert (now.date(), now.hour, now.minute) == (date(2026, 9, 25), 22, 30)
        assert now.utcoffset().total_seconds() == -5 * 3600


class TestCodes:
    AMBIGUOUS = set("01ILO")

    def test_default_code_has_prefix_and_six_unambiguous_chars(self):
        code = generate_code()
        assert re.fullmatch(r"HT-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{6}", code)

    def test_custom_prefix_and_length(self):
        assert re.fullmatch(r"INV-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{8}", generate_code("INV", 8))

    def test_empty_prefix_returns_bare_code(self):
        assert re.fullmatch(r"[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}", generate_code("", 4))

    def test_codes_never_contain_ambiguous_characters(self):
        chars = set("".join(generate_code("", 12) for _ in range(300)))
        assert chars.isdisjoint(self.AMBIGUOUS)


class TestI18n:
    @pytest.mark.parametrize(
        ("value", "lang", "expected"),
        [
            ({"es": "Hola", "en": "Hello"}, "en", "Hello"),
            ({"es": "Hola", "en": "Hello"}, "es", "Hola"),
            ({"es": "Hola"}, "en", "Hola"),
            ({"es": "", "en": "Hello"}, "es", "Hello"),
            ({"fr": "Salut"}, "en", "Salut"),
            ("plain text", "en", "plain text"),
            (None, "es", ""),
            ({}, "es", ""),
        ],
    )
    def test_t_picks_language_then_spanish_then_first_non_empty(self, value, lang, expected):
        assert t(value, lang) == expected

    def test_i18n_field_is_an_optional_json_dict(self):
        field = i18n_field()
        assert isinstance(field, JSONField)
        assert field.default is dict
        assert field.blank is True
