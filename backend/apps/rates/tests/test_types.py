import json
import uuid
from datetime import date
from decimal import Decimal

from apps.rates.types import NightPrice, Quote, TaxLine


def make_quote(**overrides):
    values = {
        "room_type_id": uuid.UUID("11111111-1111-4111-8111-111111111111"),
        "rate_plan_id": uuid.UUID("22222222-2222-4222-8222-222222222222"),
        "checkin": date(2026, 10, 1),
        "checkout": date(2026, 10, 2),
        "adults": 2,
        "children": 0,
        "nights": [
            NightPrice(
                date(2026, 10, 1),
                Decimal("320000"),
                Decimal("0"),
                Decimal("0"),
                Decimal("0"),
                Decimal("320000"),
            )
        ],
        "subtotal": Decimal("320000"),
        "discount_total": Decimal("0"),
        "taxes": [TaxLine("IVA", "IVA 19%", Decimal("19.00"), Decimal("60800"), False)],
        "tax_total": Decimal("60800"),
        "total": Decimal("380800"),
        "currency": "COP",
        "restrictions_ok": True,
    }
    values.update(overrides)
    return Quote(**values)


def test_to_dict_is_json_safe_with_money_as_two_decimal_strings():
    data = make_quote().to_dict()
    json.dumps(data)
    assert data == {
        "room_type_id": "11111111-1111-4111-8111-111111111111",
        "rate_plan_id": "22222222-2222-4222-8222-222222222222",
        "checkin": "2026-10-01",
        "checkout": "2026-10-02",
        "adults": 2,
        "children": 0,
        "nights": [
            {
                "date": "2026-10-01",
                "base": "320000.00",
                "extra_adults": "0.00",
                "extra_children": "0.00",
                "discount": "0.00",
                "total": "320000.00",
            }
        ],
        "subtotal": "320000.00",
        "discount_total": "0.00",
        "taxes": [
            {
                "code": "IVA",
                "name": "IVA 19%",
                "rate": "19.00",
                "amount": "60800.00",
                "included": False,
                "exempt": False,
            }
        ],
        "tax_total": "60800.00",
        "total": "380800.00",
        "currency": "COP",
        "restrictions_ok": True,
        "violations": [],
        "promo_applied": None,
    }


def test_violations_default_is_not_shared_between_quotes():
    first, second = make_quote(), make_quote()
    assert first.violations == [] and first.violations is not second.violations
