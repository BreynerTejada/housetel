"""Money helpers. DB: Decimal(14,2); JSON: strings; COP rounds to whole pesos (ROUND_HALF_UP)."""

from decimal import ROUND_HALF_UP, Decimal

from django.db import models

ZERO = Decimal("0")
_EXPONENTS = {"COP": Decimal("1")}
_DEFAULT_EXPONENT = Decimal("0.01")


def D(value) -> Decimal:
    """Coerce to Decimal. Floats go through str() to avoid binary noise; None/"" → 0."""
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return ZERO
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)


def quantize(amount, currency: str = "COP") -> Decimal:
    """Round to the currency unit: COP → whole pesos, others → cents. Always ROUND_HALF_UP."""
    return D(amount).quantize(_EXPONENTS.get(currency, _DEFAULT_EXPONENT), rounding=ROUND_HALF_UP)


def apply_percent(amount, percent) -> Decimal:
    """Adjust `amount` by `percent` (15 → +15 %, -12 → -12 %). Not rounded."""
    return D(amount) * (1 + D(percent) / 100)


def percent_of(amount, percent) -> Decimal:
    """`percent` % of `amount` (e.g. tax amount). Not rounded."""
    return D(amount) * D(percent) / 100


def money_field(**kwargs) -> models.DecimalField:
    """Standard money column: Decimal(14,2)."""
    kwargs.setdefault("max_digits", 14)
    kwargs.setdefault("decimal_places", 2)
    return models.DecimalField(**kwargs)
