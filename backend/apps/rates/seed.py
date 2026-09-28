"""Demo data of `rates` (plan B2a), run after the inventory seed. Idempotent: what exists is never duplicated
or overwritten.

Per property: IVA 19 % on lodging (exempt for foreign non-residents) + IVA 19 % on extras, the policies
"Flexible 48h" and "No reembolsable", the plans Tarifa flexible (FLEX, base) / No reembolsable (NR, −12 %)
/ Con desayuno (BB, +35.000) via `provision_rates`, category prices (weekend = Friday and Saturday nights
+15 %), the seasons "Alta fin de año" (15 Dec–15 Jan, +30 %) and "Semana Santa" (Palm Sunday–Easter,
+25 %), four extras, the promo code BIENVENIDA10 and an example restriction: min LOS 2 on the Saturdays
of high season.

Categories are matched to the price list by code or name keywords (the inventory seed is written in
parallel); leftovers are paired in sort order.
"""

import unicodedata
from datetime import date, timedelta
from decimal import Decimal

from dateutil.easter import easter

from apps.core.money import quantize
from apps.inventory.models import RoomType
from apps.rates.models import (
    DailyRate,
    Extra,
    PromoCode,
    RatePlan,
    RoomTypeRateDefaults,
    Season,
    SeasonRate,
    Tax,
)
from apps.rates.services.provision import provision_rates
from apps.rates.services.quote import set_daily_rates

WEEKEND = 15
AURORA_EXTRAS = {"extra_adult_price": "60000", "extra_child_price": "30000"}
CITY_EXTRAS = {"extra_adult_price": "50000", "extra_child_price": "25000"}

# property key → [(keywords, price spec)] in the order of the spec (§10 / plan B1 & B2a)
PRICE_LISTS = {
    "aurora": [
        (("dbl", "estandar", "standard"), {"price": "320000", **AURORA_EXTRAS}),
        (("sup", "superior"), {"price": "420000", **AURORA_EXTRAS}),
        (("ste", "suite"), {"price": "650000", **AURORA_EXTRAS}),
    ],
    "andino_mde": [
        (("std", "est", "estandar", "standard"), {"price": "260000", **CITY_EXTRAS}),
        (("eje", "exe", "ejecutiva", "executive"), {"price": "340000", **CITY_EXTRAS}),
        (("fam", "familiar", "family"), {"price": "420000", **CITY_EXTRAS}),
    ],
    "andino_bog": [
        (("femenino", "female", "women"), {"price": "70000"}),
        (("8 camas", "8 beds", "8-bed"), {"price": "55000"}),
        (("6 camas", "6 beds", "6-bed"), {"price": "65000"}),
        (("privada doble", "private double", "doble", "double"), {"price": "180000", **CITY_EXTRAS}),
        (("privada familiar", "private family", "familiar", "family"), {"price": "260000", **CITY_EXTRAS}),
    ],
}
FALLBACK_PRICES = {RoomType.Kind.DORM: {"price": "60000"}, RoomType.Kind.PRIVATE: {"price": "250000"}}

SEASONS = [
    {"name": "Alta fin de año", "percent": 30, "priority": 10, "color": "#B98A2E"},
    {"name": "Semana Santa", "percent": 25, "priority": 20, "color": "#4E6C88"},
]

EXTRAS = [
    ("BREAKFAST", {"es": "Desayuno", "en": "Breakfast"}, "35000", Extra.ChargeType.PER_PERSON_NIGHT),
    ("PARKING", {"es": "Parqueadero", "en": "Parking"}, "25000", Extra.ChargeType.PER_NIGHT),
    ("LATE_CHECKOUT", {"es": "Late check-out", "en": "Late check-out"}, "80000", Extra.ChargeType.PER_STAY),
    (
        "AIRPORT_TRANSFER",
        {"es": "Traslado aeropuerto", "en": "Airport transfer"},
        "90000",
        Extra.ChargeType.PER_STAY,
    ),
]


def seed(ctx) -> None:
    ctx.data.setdefault("rates", {})
    for key, prop in ctx.properties.items():
        room_types = list(
            RoomType.objects.filter(property=prop, is_active=True).order_by("sort_order", "code")
        )
        if not room_types:
            ctx.log(f"  rates: {prop.name} sin categorías, se omite")
            continue
        prices = match_prices(room_types, PRICE_LISTS.get(key, []))
        if not RatePlan.objects.filter(property=prop, code="FLEX").exists():
            # Provisioning is idempotent on data but always audits "Tarifas iniciales" and re-adds every
            # category to the plans: only the first run provisions (a re-run keeps the demo user's edits).
            provision_rates(prop, room_type_prices=prices)
        flex = RatePlan.objects.get(property=prop, code="FLEX")
        high_season = _seasons(prop, flex, ctx.today)
        _extras(prop)
        _promo(prop, ctx.today)
        _saturday_min_stay(prop, flex, high_season)
        ctx.data["rates"][key] = {
            "plans": {plan.code: plan for plan in RatePlan.objects.filter(property=prop)},
            "flex": flex,
        }
        ctx.log(f"  rates: {prop.name} · {len(prices)} categorías con precio")


def match_prices(room_types, price_list) -> dict[str, dict]:
    """{room type code: price spec}: keyword matches first (code or name), then leftovers in order."""
    specs = list(price_list)
    matched: dict[str, dict] = {}
    unmatched = []
    for room_type in room_types:
        haystack = _normalize(" ".join([room_type.name.get("es", ""), room_type.name.get("en", "")]))
        code = room_type.code.lower()
        hit = next(
            (
                index
                for index, (keywords, _spec) in enumerate(specs)
                if any(code == word or (len(word) > 3 and word in haystack) for word in keywords)
            ),
            None,
        )
        if hit is None:
            unmatched.append(room_type)
            continue
        matched[room_type.code] = dict(specs.pop(hit)[1])
    for room_type in unmatched:
        spec = specs.pop(0)[1] if specs else FALLBACK_PRICES[room_type.kind]
        matched[room_type.code] = dict(spec)
    for spec in matched.values():
        spec.setdefault("weekend_adjust_percent", WEEKEND)
    return {room_type.code: matched[room_type.code] for room_type in room_types}


def season_dates(name: str, today: date) -> tuple[date, date]:
    """Next occurrence (still running or upcoming) of a demo season, end inclusive."""
    if name == "Semana Santa":
        sunday = easter(today.year)
        if sunday < today:
            sunday = easter(today.year + 1)
        return sunday - timedelta(days=7), sunday
    start = date(today.year - 1, 12, 15)
    if date(today.year, 1, 15) < today:
        start = date(today.year, 12, 15)
    return start, date(start.year + 1, 1, 15)


def _seasons(prop, flex, today) -> Season | None:
    defaults = RoomTypeRateDefaults.objects.filter(rate_plan=flex).select_related("room_type")
    high_season = None
    for spec in SEASONS:
        start, end = season_dates(spec["name"], today)
        season, created = Season.objects.get_or_create(
            property=prop,
            name=spec["name"],
            start_date=start,
            defaults={"end_date": end, "priority": spec["priority"], "color": spec["color"]},
        )
        if spec["name"] == "Alta fin de año":
            high_season = season
        if not created:
            continue
        factor = 1 + Decimal(spec["percent"]) / 100
        for item in defaults:
            SeasonRate.objects.get_or_create(
                season=season,
                room_type=item.room_type,
                rate_plan=flex,
                defaults={
                    "price": quantize(item.price * factor, prop.currency),
                    "dow_adjustments": dict(item.dow_adjustments or {}),
                },
            )
    return high_season


def _extras(prop) -> None:
    tax = Tax.objects.filter(property=prop, code="IVA-EXTRAS").first()
    for code, name, price, charge_type in EXTRAS:
        Extra.objects.get_or_create(
            property=prop,
            code=code,
            defaults={"name": name, "price": Decimal(price), "charge_type": charge_type, "tax": tax},
        )


def _promo(prop, today) -> None:
    PromoCode.objects.get_or_create(
        property=prop,
        code="BIENVENIDA10",
        defaults={
            "discount_type": PromoCode.DiscountType.PERCENT,
            "value": Decimal("10"),
            "valid_from": today,
            "valid_to": today + timedelta(days=365),
        },
    )


def _saturday_min_stay(prop, flex, season) -> None:
    if season is None:
        return
    end = season.end_date + timedelta(days=1)
    if DailyRate.objects.filter(rate_plan=flex, date__gte=season.start_date, date__lt=end).exists():
        return
    for room_type in flex.room_types.filter(is_active=True):
        set_daily_rates(
            property=prop,
            room_type=room_type,
            rate_plan=flex,
            start=season.start_date,
            end=end,
            restrictions={"min_los": 2},
            dow=[5],
        )


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))
