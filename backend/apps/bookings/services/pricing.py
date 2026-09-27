"""Stay pricing: quote (rates contract) → the per-night breakdown stored in `Stay.nightly_rates`.

Each entry is `{"date": "YYYY-MM-DD", "amount": "…", "net": "…", "tax": "…"}` (money as 2-decimal strings):

- `price` of the night = the quote's night total (`NightPrice.total`, after occupancy extras and promo) or the
  price imposed by a channel (`StayRequest.nightly_rates`, same meaning: before any tax that is not included).
- The lodging tax is the first active `Tax` with `applies_to` room/all by code — the one `post_room_charges`
  posts on each room charge. Without it, or when the booker is a foreign non-resident and the tax exempts
  them: `net = price, tax = 0`.
- Tax not included: `net = price`, `tax = quantize(net × rate / 100)`.
- Tax included: `net = quantize(price / (1 + rate / 100))`, `tax = quantize(net × rate / 100)`.
- `amount = net + tax` (what the guest pays for the night). The stay total is `Σ amount`.

The tax is rounded per night exactly as `finance.post_charge` rounds a room charge, so the room charges posted
night by night add up to the stay total. (The quote rounds taxes on the subtotal, so `Σ amount` may differ
from `Quote.total` by rounding.) Only one lodging tax is supported per night.
"""

from dataclasses import dataclass
from decimal import Decimal

from apps.core.dates import nights as stay_nights
from apps.core.money import D, quantize
from apps.rates.models import Tax
from apps.rates.services.quote import quote
from apps.rates.types import Quote

LODGING_TAX_SCOPES = ("room", "all")
CENTS = Decimal("0.01")
UNITS = {"COP": Decimal("1")}
# quote() violations that never block a sale (the rest are restriction violations)
QUOTE_WARNINGS = frozenset({"no_rate", "promo_invalid"})


@dataclass
class PricedStay:
    quote: Quote
    entries: list[dict]
    total: Decimal


def money_str(value) -> str:
    return format(D(value).quantize(CENTS), "f")


def make_entry(day, amount, net, tax) -> dict:
    return {
        "date": day.isoformat(),
        "amount": money_str(amount),
        "net": money_str(net),
        "tax": money_str(tax),
    }


def entries_total(entries) -> Decimal:
    return sum((D(item["amount"]) for item in entries), Decimal("0"))


def lodging_tax(property):
    return (
        Tax.objects.filter(property=property, is_active=True, applies_to__in=LODGING_TAX_SCOPES)
        .order_by("code")
        .first()
    )


def tax_exempt(tax, foreign_non_resident: bool) -> bool:
    """True when the lodging tax exists but this guest does not pay it (ET art. 481 lit. d)."""
    return tax is not None and bool(tax.exempt_foreign_non_residents and foreign_non_resident)


def night_entry(day, price, tax, foreign_non_resident, currency) -> dict:
    price = quantize(price, currency)
    if tax is None or tax_exempt(tax, foreign_non_resident):
        return make_entry(day, price, price, 0)
    rate = D(tax.rate)
    net = quantize(price / (1 + rate / 100), currency) if tax.included_in_price else price
    tax_amount = quantize(net * rate / 100, currency)
    return make_entry(day, net + tax_amount, net, tax_amount)


def split_amount(amount, parts: int, currency: str) -> list[Decimal]:
    """Split `amount` in `parts` shares of the currency unit; the first shares take the remainder."""
    unit = UNITS.get(currency, CENTS)
    units = int(quantize(amount, currency) / unit)
    base, remainder = divmod(units, parts)
    return [(base + (1 if index < remainder else 0)) * unit for index in range(parts)]


def price_stay(
    *,
    property,
    room_type,
    rate_plan,
    checkin,
    checkout,
    adults,
    children=0,
    children_ages=None,
    promo_code=None,
    foreign_non_resident=False,
    nightly_prices=None,
    keep=None,
) -> PricedStay:
    """Quote the stay and build its entries.

    `nightly_prices` ({date: price}) replaces the quoted price of those nights (channel prices); `keep`
    ({"YYYY-MM-DD": entry}) keeps existing entries untouched (nights already charged, `reprice=False`).
    """
    currency = property.currency or "COP"
    stay_quote = quote(
        property=property,
        room_type=room_type,
        rate_plan=rate_plan,
        checkin=checkin,
        checkout=checkout,
        adults=adults,
        children=children,
        children_ages=list(children_ages) if children_ages else None,
        promo_code=promo_code or None,
        guest_is_foreign_non_resident=foreign_non_resident,
    )
    quoted = {night.date: night.total for night in stay_quote.nights}
    tax = lodging_tax(property)
    entries = []
    for day in stay_nights(checkin, checkout):
        if keep and day.isoformat() in keep:
            entries.append(dict(keep[day.isoformat()]))
            continue
        price = (
            nightly_prices[day] if nightly_prices and day in nightly_prices else quoted.get(day, Decimal("0"))
        )
        entries.append(night_entry(day, price, tax, foreign_non_resident, currency))
    return PricedStay(quote=stay_quote, entries=entries, total=entries_total(entries))
