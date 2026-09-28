"""The deterministic explanation of a recommendation, in Spanish and English (pure function)."""

from decimal import Decimal

from apps.revenue.services.explain import explain, money

D = Decimal


def test_money_puts_the_sign_before_the_currency():
    assert money(D("4767200"), "es") == "$ 4.767.200"
    assert money(D("-4767200"), "es") == "−$ 4.767.200"
    assert money(D("-4767200"), "en") == "−$4,767,200"
    assert money(D("-1234.5"), "en", "USD") == "−$1,234.50"


def rule(kind, adjust, detail, *, name="Regla", applied=True, combine="stack"):
    return {
        "type": "rule",
        "rule_id": None,
        "name": name,
        "kind": kind,
        "combine": combine,
        "adjust": adjust,
        "applied": applied,
        "detail": detail,
    }


def test_a_raise_with_its_rules():
    text = explain(
        current=D("300000"),
        recommended=D("360000"),
        change=D("20.00"),
        anchor=D("300000"),
        anchor_source="default",
        reasons=[
            rule("occupancy", "15.00", {"occupancy": "88.50"}),
            rule("day_of_week", "8.00", {"weekday": "sat"}),
            rule(
                "holiday",
                "12.00",
                {"name_es": "Día de la Raza", "name_en": "Columbus Day", "bridge": True},
                combine="max",
                applied=False,
            ),
            {"type": "limit", "kind": "max_daily_change", "percent": "20.00", "price": "360000.00"},
        ],
        currency="COP",
    )
    assert text == {
        "es": "Sube 20 % (de $ 300.000 a $ 360.000): ocupación del 88,5 % (+15 %); sábado (+8 %); "
        "limitado al cambio máximo de 20 %.",
        "en": "Up 20% (from $300,000 to $360,000): 88.5% occupancy (+15%); Saturday (+8%); "
        "capped at the 20% maximum change.",
    }


def test_a_drop_back_to_the_reference_price():
    text = explain(
        current=D("345000"),
        recommended=D("300000"),
        change=D("-13.04"),
        anchor=D("300000"),
        anchor_source="season",
        reasons=[],
        currency="COP",
    )
    assert text == {
        "es": "Baja 13,04 % (de $ 345.000 a $ 300.000): vuelve al precio de referencia. "
        "Referencia: $ 300.000 (temporada).",
        "en": "Down 13.04% (from $345,000 to $300,000): back to the reference price. "
        "Reference: $300,000 (season).",
    }


def test_every_reason_kind_has_words():
    text = explain(
        current=D("400000"),
        recommended=D("290000"),
        change=D("-27.50"),
        anchor=D("400000"),
        anchor_source="manual",
        reasons=[
            rule("lead_time", "-5.00", {"lead_days": 0, "window": "last_minute", "days": 3}),
            rule("lead_time", "-5.00", {"lead_days": 1, "window": "last_minute", "days": 3}),
            rule("lead_time", "4.00", {"lead_days": 75, "window": "early_bird", "days": 60}),
            rule("holiday", "12.00", {"name_es": "Navidad", "name_en": "Christmas Day", "bridge": False}),
            rule(
                "holiday", "12.00", {"name_es": "Día de la Raza", "name_en": "Columbus Day", "bridge": True}
            ),
            rule("event", "20.00", {"name": "Festival"}),
            rule("event", "20.00", {"name": ""}, name="Congreso"),
            {"type": "limit", "kind": "min_price", "price": "290000.00"},
            {"type": "limit", "kind": "max_price", "price": "500000.00"},
        ],
        currency="COP",
    )
    assert text["es"] == (
        "Baja 27,5 % (de $ 400.000 a $ 290.000): última hora (es hoy) (−5 %); "
        "última hora (falta 1 día) (−5 %); anticipación (75 días antes) (+4 %); festivo Navidad (+12 %); "
        "puente de Día de la Raza (+12 %); "
        "evento Festival (+20 %); evento Congreso (+20 %); sube al mínimo de $ 290.000; "
        "baja al máximo de $ 500.000."
    )
    assert text["en"] == (
        "Down 27.5% (from $400,000 to $290,000): last minute (today) (−5%); last minute (1 day to go) (−5%); "
        "booked early (75 days ahead) (+4%); holiday: Christmas Day (+12%); "
        "long weekend: Columbus Day (+12%); "
        "event: Festival (+20%); event: Congreso (+20%); raised to the $290,000 floor; "
        "lowered to the $500,000 ceiling."
    )


def test_last_minute_with_several_days_to_go():
    text = explain(
        current=D("300000"),
        recommended=D("285000"),
        change=D("-5.00"),
        anchor=D("300000"),
        anchor_source="default",
        reasons=[rule("lead_time", "-5.00", {"lead_days": 3, "window": "last_minute", "days": 3})],
        currency="COP",
    )
    assert "última hora (faltan 3 días) (−5 %)" in text["es"]
    assert "last minute (3 days to go) (−5%)" in text["en"]
