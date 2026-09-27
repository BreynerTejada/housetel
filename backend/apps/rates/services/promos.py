"""Promo codes (plan B2a, quote step 6).

A code is matched without case or surrounding spaces inside the property. It applies when it is active,
today (the property's calendar day) is inside the booking window `[valid_from, valid_to]`, the quoted plan
is allowed (`rate_plans` empty = every plan), uses are left (`uses < max_uses`) and at least one night of
the stay is inside the stay window `[stay_from, stay_to]`. Both windows are inclusive and open-ended when a
bound is empty. Only nights inside the stay window are discounted: percent of the night (base + extras) or
a fixed amount per night, never below zero.
"""

from datetime import date

from django.db.models import F

from apps.core.dates import property_now
from apps.core.money import D, quantize
from apps.rates.models import PromoCode


def normalize_code(code) -> str:
    return str(code or "").strip().upper()


def find_promo(property, code) -> PromoCode | None:
    code = normalize_code(code)
    if not code:
        return None
    return PromoCode.objects.filter(property=property, code__iexact=code).first()


def eligible_nights(promo: PromoCode | None, *, property, rate_plan, nights: list[date]) -> list[date]:
    """Nights of the stay that get the promo discount (empty when the promo does not apply)."""
    if promo is None or not promo.is_active:
        return []
    today = property_now(property).date()
    if (promo.valid_from and today < promo.valid_from) or (promo.valid_to and today > promo.valid_to):
        return []
    if promo.max_uses is not None and promo.uses >= promo.max_uses:
        return []
    allowed = set(promo.rate_plans.values_list("pk", flat=True))
    if allowed and rate_plan.pk not in allowed:
        return []
    return [
        night
        for night in nights
        if (promo.stay_from is None or night >= promo.stay_from)
        and (promo.stay_to is None or night <= promo.stay_to)
    ]


def night_discount(promo: PromoCode, gross, currency: str):
    """Discount of one night whose price (base + extras) is `gross`; never more than the night."""
    if promo.discount_type == PromoCode.DiscountType.AMOUNT:
        discount = quantize(promo.value, currency)
    else:
        discount = quantize(D(gross) * D(promo.value) / 100, currency)
    return max(min(discount, D(gross)), D(0))


def register_use(property, code) -> bool:
    """Counts one use of `code` in `property` (a reservation was created with it). True when one matched."""
    code = normalize_code(code)
    if not code:
        return False
    return bool(PromoCode.objects.filter(property=property, code__iexact=code).update(uses=F("uses") + 1))
