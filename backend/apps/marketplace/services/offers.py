"""Offers a guest can book online: `bookings.search_offers` for the channel, filtered by what the channel
may sell, with the exact price the reservation will have.

Exact price: `create_reservation` stores each night as `bookings.pricing.night_entry(price)` (the lodging tax
is rounded per night), which can differ by a peso from `Quote.total` (tax rounded on the subtotal). Offers and
the checkout use the same per-night entries, so what the guest sees is what the reservation charges.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from apps.bookings.services.availability import search_offers
from apps.bookings.services.pricing import lodging_tax, night_entry, tax_exempt
from apps.bookings.types import Offer
from apps.core.dates import nights as stay_nights
from apps.core.money import D, quantize
from apps.inventory.models import RoomType
from apps.marketplace.services.catalog import effective_policy, photo_payload, policy_payload
from apps.marketplace.services.engine import (
    BOOKING_ENGINE,
    allowed_plan_ids,
    check_stay_dates,
    engine_settings,
    online_payments_enabled,
)
from apps.rates.models import RatePlan

ZERO = Decimal("0")
CENTS = Decimal("0.01")


def money(value) -> str:
    return format(D(value).quantize(CENTS), "f")


@dataclass(frozen=True)
class UnitPrice:
    """What one unit (a room, or one dorm bed) costs: per-night entries as the reservation stores them."""

    entries: list = field(default_factory=list)

    @property
    def net(self) -> Decimal:
        return sum((D(entry["net"]) for entry in self.entries), ZERO)

    @property
    def tax(self) -> Decimal:
        return sum((D(entry["tax"]) for entry in self.entries), ZERO)

    @property
    def total(self) -> Decimal:
        return sum((D(entry["amount"]) for entry in self.entries), ZERO)


def unit_price(prop, quote, *, foreign: bool, tax=None) -> UnitPrice:
    """Per-night entries of a quote exactly as `create_reservation` prices each night."""
    tax = tax if tax is not None else lodging_tax(prop)
    currency = prop.currency or "COP"
    return UnitPrice([night_entry(night.date, night.total, tax, foreign, currency) for night in quote.nights])


@dataclass(frozen=True)
class SellableOffer:
    offer: Offer
    plan: RatePlan
    room_type: RoomType
    unit: UnitPrice
    tax_exempt: bool

    @property
    def total(self) -> Decimal:
        return self.unit.total * self.offer.units_needed


def sellable_offers(
    prop,
    *,
    via,
    checkin,
    checkout,
    adults,
    children=0,
    children_ages=None,
    promo_code=None,
    foreign=False,
    settings=None,
) -> list[SellableOffer]:
    """Offers of `prop` bookable online on `via`, cheapest first. Raises the booking-window errors
    (`invalid_dates`, `too_soon`, `too_far`, `stay_too_long`).

    On top of `search_offers(channel=via)` (public plans of the channel, availability, restrictions): the
    booking engine only sells its allowed plans (none selected = all), and plans that require a deposit are
    left out while the hotel's online payments are disabled (they could not be paid)."""
    settings = settings or engine_settings(prop)
    check_stay_dates(prop, checkin, checkout, settings)
    offers = search_offers(
        property=prop,
        checkin=checkin,
        checkout=checkout,
        adults=adults,
        children=children,
        children_ages=children_ages,
        channel=via,
        promo_code=promo_code or None,
        guest_is_foreign_non_resident=foreign,
    )
    if not offers:
        return []
    plans = {
        plan.pk: plan
        for plan in RatePlan.objects.filter(pk__in={offer.rate_plan_id for offer in offers}).select_related(
            "cancellation_policy", "parent__cancellation_policy"
        )
    }
    room_types = {
        room_type.pk: room_type
        for room_type in RoomType.objects.filter(
            pk__in={offer.room_type_id for offer in offers}
        ).prefetch_related("photos")
    }
    allowed = allowed_plan_ids(settings) if via == BOOKING_ENGINE else set()
    payments = online_payments_enabled(prop)
    tax = lodging_tax(prop)
    exempt = tax_exempt(tax, foreign)
    result = []
    for offer in offers:
        plan = plans[offer.rate_plan_id]
        if allowed and plan.pk not in allowed:
            continue
        if D(plan.deposit_percent) > 0 and not payments:
            continue
        result.append(
            SellableOffer(
                offer=offer,
                plan=plan,
                room_type=room_types[offer.room_type_id],
                unit=unit_price(prop, offer.quote, foreign=foreign, tax=tax),
                tax_exempt=exempt,
            )
        )
    result.sort(key=lambda item: item.total)
    return result


def offer_payload(item: SellableOffer, currency: str) -> dict:
    offer, plan, room_type = item.offer, item.plan, item.room_type
    nights = len(offer.quote.nights) or 1
    photos = [photo for photo in room_type.photos.all() if photo.room_id is None]
    return {
        "room_type_id": str(offer.room_type_id),
        "rate_plan_id": str(offer.rate_plan_id),
        "room_type": {
            "id": str(room_type.pk),
            "code": room_type.code,
            "name": room_type.name or {},
            "kind": room_type.kind,
            "max_adults": room_type.max_adults,
            "max_children": room_type.max_children,
            "max_occupancy": room_type.max_occupancy,
            "photo": photo_payload(photos[0])["url"] if photos else None,
        },
        "rate_plan": {
            "id": str(plan.pk),
            "code": plan.code,
            "name": plan.name or {},
            "meal_plan": plan.meal_plan,
            "deposit_percent": money(plan.deposit_percent),
            "requires_payment": D(plan.deposit_percent) > 0,
            "cancellation_policy": policy_payload(effective_policy(plan)),
        },
        "available_units": offer.available_units,
        "units_needed": offer.units_needed,
        "max_quantity": max(0, offer.available_units // max(1, offer.units_needed)),
        "quote": offer.quote.to_dict(),
        "net_total": money(item.unit.net * offer.units_needed),
        "tax_total": money(item.unit.tax * offer.units_needed),
        "total": money(item.total),
        "per_night": money(quantize(item.total / nights, currency)),
        "tax_exempt": item.tax_exempt,
        "promo_applied": offer.quote.promo_applied,
    }


def offers_response(
    prop, items: list[SellableOffer], *, checkin, checkout, adults, children, promo_code, foreign
):
    currency = prop.currency or "COP"
    promo = None
    if promo_code:
        promo = {
            "code": promo_code.strip().upper(),
            "applied": any(i.offer.quote.promo_applied for i in items),
        }
    return {
        "checkin": checkin.isoformat(),
        "checkout": checkout.isoformat(),
        "nights": len(stay_nights(checkin, checkout)),
        "adults": adults,
        "children": children,
        "currency": currency,
        "tax_exempt": tax_exempt(lodging_tax(prop), foreign),
        "online_payments": online_payments_enabled(prop),
        "promo": promo,
        "offers": [offer_payload(item, currency) for item in items],
    }
