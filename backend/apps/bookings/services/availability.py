"""Availability and offers (spec §4.2, plan B2b › Servicios).

`availability` reads the materialized InventoryDay rows (see `services.inventory`); `search_offers` combines
them with the quote engine of `rates`.
"""

from datetime import date
from uuid import UUID

from apps.bookings.services.inventory import available_by_date
from apps.bookings.types import Offer
from apps.core.dates import nights as stay_nights
from apps.inventory.models import RoomType
from apps.rates.models import RatePlan
from apps.rates.services.quote import quote


def availability(*, property, checkin, checkout, room_type_ids=None) -> dict[UUID, int]:
    """Units still sellable per ACTIVE room type for every night of `[checkin, checkout)` (the minimum over
    the nights), read from InventoryDay (missing rows are materialized first). Negative when a category is
    overbooked; an empty or inverted range returns 0 for every category."""
    type_ids = _active_type_ids(property, room_type_ids)
    if not stay_nights(checkin, checkout):
        return {type_id: 0 for type_id in type_ids}
    by_date = available_by_date(property, type_ids, checkin, checkout)
    return {type_id: min(by_date[type_id].values()) for type_id in type_ids}


def availability_by_date(*, property, start, end, room_type_ids=None) -> dict[UUID, dict[date, int]]:
    """The range version of `availability` (one call for a grid of nights): `{room_type_id: {date: units}}`
    for every night of `[start, end)` and every ACTIVE room type (or only `room_type_ids`), in date order,
    read from InventoryDay (missing rows are materialized first). Negative when overbooked; an empty or
    inverted range gives `{}` for every category."""
    type_ids = _active_type_ids(property, room_type_ids)
    if not stay_nights(start, end):
        return {type_id: {} for type_id in type_ids}
    return available_by_date(property, type_ids, start, end)


def _active_type_ids(property, room_type_ids) -> list:
    room_types = RoomType.objects.filter(property=property, is_active=True)
    if room_type_ids is not None:
        room_types = room_types.filter(pk__in=list(room_type_ids))
    return list(room_types.values_list("pk", flat=True))


def search_offers(
    *,
    property,
    checkin,
    checkout,
    adults,
    children=0,
    children_ages=None,
    channel="direct",
    promo_code=None,
    guest_is_foreign_non_resident=False,
) -> list[Offer]:
    """Sellable offers (cheapest first): active categories with capacity ×
    applicable active plans (channel in plan.channels or channels empty; "direct" includes non-public plans,
    other channels only public ones) → quote → kept when `restrictions_ok` and availability ≥ units needed.

    Private categories need `adults ≤ max_adults`, `children ≤ max_children`, `adults + children ≤
    max_occupancy` (one room: `units_needed = 1`); dorms sell one bed per guest (`units_needed = adults +
    children`, children only where `max_children > 0`) and are quoted per bed (1 adult). Plans must include
    the category. Quotes without a configured price (`no_rate`) are left out as well."""
    if not stay_nights(checkin, checkout):
        return []
    adults, children = int(adults or 0), int(children or 0)
    room_types = [
        room_type
        for room_type in RoomType.objects.filter(property=property, is_active=True).order_by(
            "sort_order", "code"
        )
        if _party_fits(room_type, adults, children)
    ]
    if not room_types:
        return []
    available = availability(
        property=property, checkin=checkin, checkout=checkout, room_type_ids=[rt.pk for rt in room_types]
    )
    plans = list(
        RatePlan.objects.filter(property=property, is_active=True)
        .select_related("parent")
        .prefetch_related("room_types")
        .order_by("sort_order", "code")
    )
    offers = []
    for room_type in room_types:
        dorm = room_type.kind == RoomType.Kind.DORM
        units_needed = adults + children if dorm else 1
        if available.get(room_type.pk, 0) < units_needed:
            continue
        for plan in plans:
            if not plan_applies(plan, room_type, channel):
                continue
            unit_quote = quote(
                property=property,
                room_type=room_type,
                rate_plan=plan,
                checkin=checkin,
                checkout=checkout,
                adults=1 if dorm else adults,
                children=0 if dorm else children,
                children_ages=None if dorm else (list(children_ages) if children_ages else None),
                promo_code=promo_code or None,
                guest_is_foreign_non_resident=guest_is_foreign_non_resident,
            )
            if not unit_quote.restrictions_ok or "no_rate" in unit_quote.violations:
                continue
            offers.append(
                Offer(
                    room_type_id=room_type.pk,
                    rate_plan_id=plan.pk,
                    available_units=available[room_type.pk],
                    units_needed=units_needed,
                    quote=unit_quote,
                    total=unit_quote.total * units_needed,
                )
            )
    order = {room_type.pk: index for index, room_type in enumerate(room_types)}
    plan_order = {plan.pk: index for index, plan in enumerate(plans)}
    offers.sort(key=lambda offer: (offer.total, order[offer.room_type_id], plan_order[offer.rate_plan_id]))
    return offers


def plan_applies(plan, room_type, channel) -> bool:
    """The plan sells this category on this channel (`channels` empty = every channel; "direct" also sells
    non-public plans, any other channel only public ones)."""
    if room_type.pk not in {item.pk for item in plan.room_types.all()}:
        return False
    channels = plan.channels or []
    if channel == "direct":
        return not channels or "direct" in channels
    return bool(plan.is_public) and (not channels or channel in channels)


def _party_fits(room_type, adults, children) -> bool:
    if room_type.kind == RoomType.Kind.DORM:
        return adults + children >= 1 and (not children or room_type.max_children > 0)
    return (
        1 <= adults <= room_type.max_adults
        and children <= room_type.max_children
        and adults + children <= room_type.max_occupancy
    )
