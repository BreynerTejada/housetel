"""Marketplace search: listed hotels of a city, each with its cheapest online offer (cached 60 s per search).

Without dates the search lists the city's hotels without prices (the page asks for dates to show them).
With dates only hotels with at least one bookable offer come back (listed, available, within the hotel's
booking window). Price filters and price sorting use the price per night of that cheapest offer.
"""

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Q

from apps.core.dates import nights as stay_nights
from apps.core.errors import DomainError
from apps.core.money import D, quantize
from apps.marketplace.services.catalog import amenity_codes, property_card, resolve_amenities
from apps.marketplace.services.engine import MARKETPLACE, listed_properties
from apps.marketplace.services.offers import money, sellable_offers

CACHE_SECONDS = 60
CACHE_PREFIX = "marketplace:search:"
CACHE_VERSION_KEY = "marketplace:search:version"
MAX_RESULTS = 60
MAX_AMENITY_FACETS = 12
SORTS = ("recommended", "price", "-price", "stars")


@dataclass
class SearchQuery:
    city: str = ""
    checkin: date | None = None
    checkout: date | None = None
    adults: int = 2
    children: int = 0
    children_ages: list[int] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    stars: list[int] = field(default_factory=list)
    amenities: list[str] = field(default_factory=list)
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    sort: str = "recommended"

    @property
    def has_dates(self) -> bool:
        return bool(self.checkin and self.checkout)

    def cache_key(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True, default=str)
        return f"{CACHE_PREFIX}v{cache_version()}:{hashlib.sha256(raw.encode()).hexdigest()}"


def cache_version() -> int:
    return cache.get_or_set(CACHE_VERSION_KEY, 1, None) or 1


def invalidate_search_cache() -> None:
    """Every cached search answers again from the database (a hotel was listed, hidden or changed its booking
    window): the version in the keys moves on and the old entries expire on their own."""
    try:
        cache.incr(CACHE_VERSION_KEY)
    except ValueError:  # no version yet
        cache.set(CACHE_VERSION_KEY, 2, None)


def search(query: SearchQuery) -> dict:
    key = query.cache_key()
    cached = cache.get(key)
    if cached is not None:
        return cached
    result = _search(query)
    cache.set(key, result, CACHE_SECONDS)
    return result


def _search(query: SearchQuery) -> dict:
    properties = listed_properties()
    if query.city:
        properties = properties.filter(Q(city__unaccent__iexact=query.city.strip()))
    city_properties = list(properties.order_by("name"))
    rows = []
    for prop in city_properties:
        if query.types and prop.property_type not in query.types:
            continue
        if query.stars and prop.star_rating not in query.stars:
            continue
        card = property_card(prop)
        if query.amenities and not set(query.amenities) <= set(card["amenity_codes"]):
            continue
        card["offer"] = None
        if query.has_dates:
            offer = _cheapest(prop, query)
            if offer is None:
                continue
            per_night = D(offer["per_night"])
            if query.min_price is not None and per_night < query.min_price:
                continue
            if query.max_price is not None and per_night > query.max_price:
                continue
            card["offer"] = offer
        card.pop("amenity_codes", None)
        rows.append(card)
    rows.sort(key=_sort_key(query.sort))
    return {
        "count": len(rows),
        "city": query.city,
        "checkin": query.checkin.isoformat() if query.checkin else None,
        "checkout": query.checkout.isoformat() if query.checkout else None,
        "nights": len(stay_nights(query.checkin, query.checkout)) if query.has_dates else 0,
        "adults": query.adults,
        "children": query.children,
        "results": rows[:MAX_RESULTS],
        "facets": _facets(city_properties),
    }


def _facets(properties) -> dict:
    """What the filters can offer: types, stars and amenities of the destination's listed hotels, with how
    many hotels have each (the other filters and the dates do not change them)."""
    types = Counter(prop.property_type for prop in properties)
    stars = Counter(prop.star_rating for prop in properties if prop.star_rating)
    amenity_counts: Counter = Counter()
    payloads: dict[str, dict] = {}
    for prop in properties:
        resolved = resolve_amenities(prop.organization, amenity_codes(prop))
        for amenity in resolved:
            payloads.setdefault(amenity["code"], amenity)
        amenity_counts.update({amenity["code"] for amenity in resolved})
    amenities = sorted(amenity_counts, key=lambda code: (-amenity_counts[code], code))[:MAX_AMENITY_FACETS]
    return {
        "types": [
            {"value": value, "count": count}
            for value, count in sorted(types.items(), key=lambda item: (-item[1], item[0]))
        ],
        "stars": [{"value": value, "count": count} for value, count in sorted(stars.items(), reverse=True)],
        "amenities": [{**payloads[code], "count": amenity_counts[code]} for code in amenities],
    }


def _cheapest(prop, query: SearchQuery) -> dict | None:
    try:
        offers = sellable_offers(
            prop,
            via=MARKETPLACE,
            checkin=query.checkin,
            checkout=query.checkout,
            adults=query.adults,
            children=query.children,
            children_ages=query.children_ages or None,
        )
    except DomainError:  # outside this hotel's booking window: it simply has nothing to sell
        return None
    if not offers:
        return None
    best = offers[0]
    currency = prop.currency or "COP"
    nights = len(best.offer.quote.nights) or 1
    return {
        "room_type": {
            "id": str(best.room_type.pk),
            "code": best.room_type.code,
            "name": best.room_type.name or {},
        },
        "rate_plan": {
            "id": str(best.plan.pk),
            "code": best.plan.code,
            "name": best.plan.name or {},
            "meal_plan": best.plan.meal_plan,
        },
        "total": money(best.total),
        "per_night": money(quantize(best.total / nights, currency)),
        "currency": currency,
        "available_units": best.offer.available_units,
        "units_needed": best.offer.units_needed,
        "taxes_included": True,
    }


def _sort_key(sort: str):
    def price(row):
        offer = row.get("offer")
        return D(offer["per_night"]) if offer else None

    def stars(row):
        return -(row.get("star_rating") or 0)

    if sort == "price":
        return lambda row: (price(row) is None, price(row) or 0, row["name"])
    if sort == "-price":
        return lambda row: (price(row) is None, -(price(row) or 0), row["name"])
    # recommended and stars: more stars first, then the cheaper one
    return lambda row: (stars(row), price(row) is None, price(row) or 0, row["name"])
