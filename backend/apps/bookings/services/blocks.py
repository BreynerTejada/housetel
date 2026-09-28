"""Group allotments — cupos (pilot plan P3).

A `GroupBlock` holds `units` rooms (beds in a dorm) of one category for a group on the nights `[start, end)`.
Stays created "from the block" (`Stay.group_block`) consume it — the pickup — and whatever is not picked up
goes back to general inventory when the block is released: by hand or, on its `release_date`, by the daily
automation `bookings.release_group_blocks`.

The hold lives in `InventoryDay.held_units` (see `services.inventory`): per block and night
`max(0, units − picked)` while the block is not released. Every change computes the block's held units before
and after it and applies the difference with `adjust_inventory(held=…)`; an increase must fit in the night's
availability (409 `no_availability`, with `shortfalls`). A pickup moves a unit from held to sold, so a full
hotel still sells the block's rooms to its group.

Lock order: Reservation → Stay → GroupBlock (pk order) → InventoryDay, as everywhere in bookings.
"""

from collections import Counter, defaultdict
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.bookings.models import GroupBlock, Stay
from apps.bookings.services.inventory import ORIGIN, PICKUP_STATUSES, adjust_inventory, available_by_date
from apps.bookings.types import BookingError, InvalidStateError
from apps.core import audit, signals
from apps.core.dates import daterange
from apps.core.dates import nights as stay_nights
from apps.inventory.models import RoomType


def _user(actor):
    return actor if getattr(actor, "is_authenticated", False) else None


def _source(actor, source=None) -> str:
    return source or ("user" if _user(actor) else "system")


# --- the hold -----------------------------------------------------------------------------------------------


def lock_blocks(block_ids) -> dict:
    """Lock these blocks (in pk order, like every lock in bookings) and return them fresh: `{pk: block}`."""
    ids = sorted({pk for pk in block_ids if pk}, key=str)
    if not ids:
        return {}
    blocks = (
        GroupBlock.objects.select_for_update(of=("self",))
        .select_related("group__property", "room_type")
        .filter(pk__in=ids)
        .order_by("pk")
    )
    return {block.pk: block for block in blocks}


def picked_by_night(block) -> Counter:
    """{night: stays picked up from the block that cover it} (every night of those stays)."""
    picked: Counter = Counter()
    rows = Stay.objects.filter(group_block=block, status__in=PICKUP_STATUSES).values_list(
        "checkin_date", "checkout_date"
    )
    for checkin, checkout in rows:
        for night in daterange(checkin, checkout):
            picked[night] += 1
    return picked


def holds_for(room_type_id, start, end, units, picked) -> Counter:
    """{(room_type_id, night): held units} of a block with these values: `max(0, units − picked)` per
    night."""
    return Counter({(room_type_id, night): max(0, units - picked[night]) for night in daterange(start, end)})


def block_holds(block, picked=None) -> Counter:
    """What the block holds now (empty once released)."""
    if block.released_at is not None:
        return Counter()
    return holds_for(
        block.room_type_id,
        block.start,
        block.end,
        block.units,
        picked if picked is not None else picked_by_night(block),
    )


def difference(after, before) -> dict:
    """Signed `after − before` per key, zeros left out (Counter subtraction would drop the negatives)."""
    return {
        key: after.get(key, 0) - before.get(key, 0)
        for key in {*after, *before}
        if after.get(key, 0) != before.get(key, 0)
    }


def pickup_nights(stay) -> list[date]:
    """The nights the stay counts as picked up from its block (none when it is not from a block or no longer
    in a pickup status: cancelled, no-show)."""
    if not stay.group_block_id or stay.status not in PICKUP_STATUSES:
        return []
    return stay_nights(stay.checkin_date, stay.checkout_date)


def pickup_hold_deltas(changes) -> dict:
    """Held-unit deltas `{(room_type_id, night): ±n}` when stays picked up from blocks change.

    `changes` = `[(block_id, nights_before, nights_after)]`: the nights each stay counts as picked up before
    and after the operation (`pickup_nights`; empty for a new stay before, or for a cancelled one after).
    Locks the blocks; released blocks hold nothing, so they give no delta. Call it before writing the stays:
    the current pickup is read from the database."""
    per_block: defaultdict = defaultdict(lambda: (Counter(), Counter()))
    for block_id, before, after in changes:
        if block_id:
            per_block[block_id][0].update(before)
            per_block[block_id][1].update(after)
    blocks = lock_blocks(per_block)
    deltas: dict = {}
    for block_id, (before, after) in per_block.items():
        block = blocks.get(block_id)
        if block is None or block.released_at is not None:
            continue
        picked_now = picked_by_night(block)
        picked_after = Counter(picked_now)
        picked_after.subtract(before)
        picked_after.update(after)
        current = holds_for(block.room_type_id, block.start, block.end, block.units, picked_now)
        new = holds_for(block.room_type_id, block.start, block.end, block.units, picked_after)
        for key, delta in difference(new, current).items():
            deltas[key] = deltas.get(key, 0) + delta
    return deltas


def remaining_by_night(block) -> dict[date, int]:
    """{night: units still held for the group} over the block's nights (0 once released)."""
    held = block_holds(block)
    return {night: held.get((block.room_type_id, night), 0) for night in daterange(block.start, block.end)}


def pickup_summary(block) -> dict:
    """The block's pickup: per night `{date, units, picked, remaining}` and the totals — room nights held and
    picked (picked capped at `units`), the percentage, the stays picked up (rooms) and whether it is
    released."""
    picked = picked_by_night(block)
    released = block.released_at is not None
    nights = []
    for night in daterange(block.start, block.end):
        count = picked[night]
        nights.append(
            {
                "date": night.isoformat(),
                "units": block.units,
                "picked": count,
                "remaining": 0 if released else max(0, block.units - count),
            }
        )
    room_nights = block.units * len(nights)
    picked_nights = sum(min(item["picked"], block.units) for item in nights)
    rooms = Stay.objects.filter(group_block=block, status__in=PICKUP_STATUSES).count()
    return {
        "nights": nights,
        "room_nights": room_nights,
        "picked_room_nights": picked_nights,
        "pickup_pct": round(100 * picked_nights / room_nights, 1) if room_nights else 0.0,
        "picked_rooms": rooms,
        "remaining_min": min((item["remaining"] for item in nights), default=0),
        "released": released,
    }


def availability_with_block(block, checkin, checkout) -> int:
    """Units a pickup from the block can take for `[checkin, checkout)`: per night the general availability of
    the category plus what the block still holds on it (nights outside the block count only the general one);
    the minimum over the nights."""
    type_id = block.room_type_id
    general = available_by_date(block.group.property, [type_id], checkin, checkout).get(type_id, {})
    remaining = remaining_by_night(block)
    values = [general.get(night, 0) + remaining.get(night, 0) for night in daterange(checkin, checkout)]
    return min(values) if values else 0


# --- allotments ---------------------------------------------------------------------------------------------


def _emit(prop, room_type_ids, start, end) -> None:
    signals.send_on_commit(
        signals.inventory_changed,
        property=prop,
        room_type_ids=list(dict.fromkeys(room_type_ids)),
        start=start,
        end=end,
        origin=ORIGIN,
    )


def _validate_values(prop, room_type, start, end, units) -> None:
    if room_type is None or room_type.property_id != prop.pk or not room_type.is_active:
        raise BookingError(
            "La categoría no existe o no está activa en esta propiedad", code="invalid_room_type"
        )
    if not start or not end or end <= start:
        raise BookingError("El fin del cupo debe ser posterior al inicio", code="invalid_dates")
    if units is None or int(units) < 1:
        raise BookingError("El cupo debe tener al menos una unidad", code="invalid_units")
    capacity = (
        sum(room.beds.filter(is_active=True).count() for room in room_type.rooms.filter(is_active=True))
        if room_type.kind == RoomType.Kind.DORM
        else room_type.rooms.filter(is_active=True).count()
    )
    if int(units) > capacity:
        raise BookingError(
            f"La categoría {room_type.code} solo tiene {capacity} unidades", code="invalid_units"
        )


def create_block(
    group, *, room_type, start, end, units, release_date, actor=None, allow_overbooking=False
) -> GroupBlock:
    """Hold `units` of `room_type` for the group on `[start, end)` until `release_date` (from today to the
    first night). Every night must have those units available (409 `no_availability` + `shortfalls`, unless
    `allow_overbooking`). Audits `bookings.group_block_created`; emits `inventory_changed`."""
    prop = group.property
    _validate_values(prop, room_type, start, end, units)
    if start < prop.business_date:
        raise BookingError("El cupo debe empezar hoy o más adelante", code="invalid_dates")
    if not release_date or release_date < prop.business_date or release_date > start:
        raise BookingError(
            "La fecha de liberación debe estar entre hoy y la primera noche del cupo",
            code="invalid_release_date",
        )
    units = int(units)
    with transaction.atomic():
        holds = holds_for(room_type.pk, start, end, units, Counter())
        adjust_inventory(prop, {}, held=holds, allow_overbooking=allow_overbooking)
        block = GroupBlock.objects.create(
            group=group, room_type=room_type, start=start, end=end, units=units, release_date=release_date
        )
        audit.record(
            action="bookings.group_block_created",
            target=block,
            summary=(
                f"Creó un cupo de {units} {room_type.code} para el grupo {group.name} "
                f"({start.isoformat()} → {end.isoformat()}, se libera el {release_date.isoformat()})"
            ),
            actor=actor,
            source=_source(actor),
            property=prop,
            changes={
                "room_type": [None, room_type.code],
                "units": [None, units],
                "start": [None, start.isoformat()],
                "end": [None, end.isoformat()],
                "release_date": [None, release_date.isoformat()],
            },
        )
        _emit(prop, [room_type.pk], start, end)
    return block


def update_block(
    block, *, units=None, start=None, end=None, release_date=None, actor=None, allow_overbooking=False
) -> GroupBlock:
    """Change the units, the nights or the release date of an unreleased block. The units can't go below what
    was already picked up on some night (400 `block_below_pickup`); new held units must be available (409).
    Audits `bookings.group_block_updated`; emits `inventory_changed` when the hold moved."""
    with transaction.atomic():
        block = lock_blocks([block.pk])[block.pk]
        prop = block.group.property
        if block.released_at is not None:
            raise InvalidStateError("El cupo ya se liberó; crea otro si el grupo necesita más habitaciones")
        new_start, new_end = start or block.start, end or block.end
        new_units = block.units if units is None else int(units)
        new_release = release_date or block.release_date
        _validate_values(prop, block.room_type, new_start, new_end, new_units)
        if release_date and release_date != block.release_date:
            if release_date < prop.business_date or release_date >= new_end:
                raise BookingError(
                    "La fecha de liberación debe estar entre hoy y la última noche del cupo",
                    code="invalid_release_date",
                )
        picked = picked_by_night(block)
        most = max((picked[night] for night in daterange(new_start, new_end)), default=0)
        if new_units < most:
            raise BookingError(
                f"El grupo ya tomó {most} unidades de este cupo en una de sus noches; "
                f"no puede quedar en {new_units}",
                code="block_below_pickup",
                picked=most,
            )
        before = holds_for(block.room_type_id, block.start, block.end, block.units, picked)
        after = holds_for(block.room_type_id, new_start, new_end, new_units, picked)
        deltas = difference(after, before)
        adjust_inventory(prop, {}, held=deltas, allow_overbooking=allow_overbooking)
        old = {
            "units": block.units,
            "start": block.start.isoformat(),
            "end": block.end.isoformat(),
            "release_date": block.release_date.isoformat(),
        }
        old_start, old_end = block.start, block.end
        block.units, block.start, block.end, block.release_date = new_units, new_start, new_end, new_release
        block.save(update_fields=["units", "start", "end", "release_date", "updated_at"])
        new = {
            "units": block.units,
            "start": block.start.isoformat(),
            "end": block.end.isoformat(),
            "release_date": block.release_date.isoformat(),
        }
        changes = audit.diff(old, new)
        if changes:
            audit.record(
                action="bookings.group_block_updated",
                target=block,
                summary=f"Actualizó el cupo {block.room_type.code} del grupo {block.group.name}",
                actor=actor,
                source=_source(actor),
                property=prop,
                changes={name: list(pair) for name, pair in changes.items()},
            )
        if deltas:
            _emit(prop, [block.room_type_id], min(old_start, new_start), max(old_end, new_end))
    return block


def release_block(block, *, actor=None, source=None) -> GroupBlock:
    """Give back to general inventory what the block still holds (idempotent: a released block is returned as
    it is). The pickup stays keep their rooms. Audits `bookings.group_block_released`; emits
    `inventory_changed`."""
    with transaction.atomic():
        block = lock_blocks([block.pk])[block.pk]
        if block.released_at is not None:
            return block
        prop = block.group.property
        current = block_holds(block)
        freed = sum(current.values())
        adjust_inventory(prop, {}, held={key: -value for key, value in current.items() if value})
        block.released_at = timezone.now()
        block.save(update_fields=["released_at", "updated_at"])
        audit.record(
            action="bookings.group_block_released",
            target=block,
            summary=(
                f"Liberó el cupo {block.room_type.code} del grupo {block.group.name}: "
                f"{freed} noche(s)-habitación sin tomar vuelven a la venta"
            ),
            actor=actor,
            source=_source(actor, source),
            property=prop,
            changes={
                "released_at": [None, block.released_at.isoformat()],
                "freed_room_nights": [None, freed],
            },
        )
        if freed:
            _emit(prop, [block.room_type_id], block.start, block.end)
    return block


def delete_block(block, *, actor=None) -> None:
    """Delete a block nobody picked up (409 `block_has_pickups` otherwise: release it instead). What it held
    goes back to general inventory."""
    with transaction.atomic():
        block = lock_blocks([block.pk])[block.pk]
        prop = block.group.property
        if Stay.objects.filter(group_block=block, status__in=PICKUP_STATUSES).exists():
            raise InvalidStateError(
                "El grupo ya tomó habitaciones de este cupo: libéralo en lugar de borrarlo",
                code="block_has_pickups",
            )
        current = block_holds(block)
        adjust_inventory(prop, {}, held={key: -value for key, value in current.items() if value})
        audit.record(
            action="bookings.group_block_deleted",
            target=block.group,
            summary=(
                f"Borró el cupo de {block.units} {block.room_type.code} del grupo {block.group.name} "
                f"({block.start.isoformat()} → {block.end.isoformat()})"
            ),
            actor=actor,
            source=_source(actor),
            property=prop,
            changes={"block_id": [str(block.pk), None], "units": [block.units, None]},
        )
        room_type_id, start, end = block.room_type_id, block.start, block.end
        block.delete()
        if current:
            _emit(prop, [room_type_id], start, end)


def release_due_blocks(property, *, actor=None) -> list[dict]:
    """Release every unreleased block of the property whose `release_date` arrived (≤ business date). Returns
    `[{block_id, group, room_type, freed}]`; each block goes in its own transaction."""
    due = (
        GroupBlock.objects.filter(
            group__property=property, released_at__isnull=True, release_date__lte=property.business_date
        )
        .select_related("group", "room_type")
        .order_by("release_date", "created_at")
    )
    released = []
    for block in list(due):
        freed = sum(block_holds(block).values())
        release_block(block, actor=actor, source="automation")
        released.append(
            {
                "block_id": str(block.pk),
                "group": block.group.name,
                "room_type": block.room_type.code,
                "freed": freed,
            }
        )
    return released
