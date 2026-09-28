"""Reservation groups (pilot plan P3): the figures of the groups list, the rooming list and the name of the
guest in each room, and deleting a group with its allotments."""

import unicodedata
from collections import Counter, defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Max, Min

from apps.bookings.models import GroupBlock, Reservation, ReservationGroup, Stay
from apps.bookings.services.blocks import release_block
from apps.bookings.services.inventory import PICKUP_STATUSES
from apps.bookings.services.pricing import money_str
from apps.bookings.services.queries import with_balance
from apps.bookings.types import BookingError, InvalidStateError
from apps.core import audit
from apps.core.dates import daterange

LIVE_STATUSES = ("tentative", "confirmed", "checked_in", "checked_out")  # rooms that count in a group


def _user(actor):
    return actor if getattr(actor, "is_authenticated", False) else None


def group_figures(groups, *, today=None) -> dict:
    """`{group_id: {...}}` for these groups of one property, in a constant number of queries:

    - `start` / `end`: first arrival and last departure of its live rooms and its allotments (ISO or None);
    - `reservations` (not cancelled / no-show), `rooms` (live stays: rooms, or beds in a dorm);
    - allotments: `blocks`, `blocked_units` (Σ units of its blocks, released or not), `picked_rooms` (stays
      picked up from them), `room_nights`, `picked_room_nights` (capped at the units per night), `pickup_pct`
      (None without blocks);
    - `balance`: Σ of the balance of its reservations (money string);
    - `state`: `upcoming | in_house | past | empty` against `today` (the business date)."""
    ids = [group.pk for group in groups]
    figures = {
        pk: {
            "start": None,
            "end": None,
            "reservations": 0,
            "rooms": 0,
            "blocks": 0,
            "blocked_units": 0,
            "picked_rooms": 0,
            "room_nights": 0,
            "picked_room_nights": 0,
            "pickup_pct": None,
            "balance": Decimal("0"),
            "state": "empty",
        }
        for pk in ids
    }
    if not ids:
        return figures
    spans = defaultdict(list)
    stays = (
        Stay.objects.filter(reservation__group_id__in=ids, status__in=LIVE_STATUSES)
        .values("reservation__group_id")
        .annotate(rooms=Count("id"), start=Min("checkin_date"), end=Max("checkout_date"))
    )
    for row in stays:
        pk = row["reservation__group_id"]
        figures[pk]["rooms"] = row["rooms"]
        spans[pk].append((row["start"], row["end"]))
    reservations = (
        Reservation.objects.filter(group_id__in=ids)
        .exclude(status__in=["cancelled", "no_show"])
        .values("group_id")
        .annotate(count=Count("id"))
    )
    for row in reservations:
        figures[row["group_id"]]["reservations"] = row["count"]
    for pk, balance in with_balance(Reservation.objects.filter(group_id__in=ids)).values_list(
        "group_id", "balance"
    ):
        figures[pk]["balance"] += balance or Decimal("0")

    blocks = list(GroupBlock.objects.filter(group_id__in=ids))
    picked: Counter = Counter()  # (block id, night) → stays picked up
    rooms_by_block: Counter = Counter()
    rows = Stay.objects.filter(group_block__in=blocks, status__in=PICKUP_STATUSES).values_list(
        "group_block_id", "checkin_date", "checkout_date"
    )
    for block_id, checkin, checkout in rows:
        rooms_by_block[block_id] += 1
        for night in daterange(checkin, checkout):
            picked[(block_id, night)] += 1
    for block in blocks:
        item = figures[block.group_id]
        nights = list(daterange(block.start, block.end))
        item["blocks"] += 1
        item["blocked_units"] += block.units
        item["picked_rooms"] += rooms_by_block[block.pk]
        item["room_nights"] += block.units * len(nights)
        item["picked_room_nights"] += sum(min(picked[(block.pk, night)], block.units) for night in nights)
        spans[block.group_id].append((block.start, block.end))
    for pk, item in figures.items():
        if item["room_nights"]:
            item["pickup_pct"] = round(100 * item["picked_room_nights"] / item["room_nights"], 1)
        if spans[pk]:
            start = min(span[0] for span in spans[pk])
            end = max(span[1] for span in spans[pk])
            item["start"], item["end"] = start.isoformat(), end.isoformat()
            if today is not None:
                item["state"] = "past" if end <= today else ("in_house" if start <= today else "upcoming")
        item["balance"] = money_str(item["balance"])
    return figures


def rooming_list(group) -> list[dict]:
    """Every room (stay) of the group's reservations, by arrival and reservation: who holds it and who sleeps
    in it (`guest` = the first occupant, the name the rooming list edits), where and when, and whether it was
    picked up from an allotment. Cancelled and no-show rooms are left out."""
    stays = (
        Stay.objects.filter(reservation__group=group)
        .exclude(status__in=["cancelled", "no_show"])
        .select_related("reservation__booker", "room_type", "room", "bed", "rate_plan")
        .order_by("checkin_date", "reservation__code", "created_at")
    )
    stays = list(stays)
    through = Stay.occupants.through
    first: dict = {}
    counts: Counter = Counter()
    for link in through.objects.filter(stay__in=stays).select_related("guest").order_by("id"):
        counts[link.stay_id] += 1
        first.setdefault(link.stay_id, link.guest)
    rows = []
    for stay in stays:
        guest = first.get(stay.pk)
        rows.append(
            {
                "stay_id": str(stay.pk),
                "reservation_id": str(stay.reservation_id),
                "code": stay.reservation.code,
                "status": stay.status,
                "booker_name": stay.reservation.booker.full_name,
                "room_type": {
                    "id": str(stay.room_type_id),
                    "code": stay.room_type.code,
                    "name": stay.room_type.name,
                    "kind": stay.room_type.kind,
                    "color": stay.room_type.color,
                },
                "rate_plan": {
                    "id": str(stay.rate_plan_id),
                    "code": stay.rate_plan.code,
                    "name": stay.rate_plan.name,
                },
                "room": (
                    {
                        "id": str(stay.room_id),
                        "number": stay.room.number,
                        "housekeeping_status": stay.room.housekeeping_status,
                    }
                    if stay.room_id
                    else None
                ),
                "bed": {"id": str(stay.bed_id), "label": stay.bed.label} if stay.bed_id else None,
                "checkin": stay.checkin_date.isoformat(),
                "checkout": stay.checkout_date.isoformat(),
                "nights": (stay.checkout_date - stay.checkin_date).days,
                "adults": stay.adults,
                "children": stay.children,
                "guest": (
                    {
                        "id": str(guest.pk),
                        "first_name": guest.first_name,
                        "last_name": guest.last_name,
                        "full_name": guest.full_name,
                    }
                    if guest is not None
                    else None
                ),
                "occupants": counts[stay.pk],
                "group_block_id": str(stay.group_block_id) if stay.group_block_id else None,
                "total_amount": money_str(stay.total_amount),
            }
        )
    return rows


def _first_link(stay):
    return Stay.occupants.through.objects.filter(stay=stay).select_related("guest").order_by("id").first()


def _is_placeholder(guest, stay) -> bool:
    """A guest made only of a name for this room (typed in the rooming list): no document, email or phone, not
    the booker of any reservation and in no other stay — safe to rename in place."""
    if guest.document_number or guest.email or guest.phone:
        return False
    if Reservation.objects.filter(booker=guest).exists():
        return False
    return not Stay.occupants.through.objects.filter(guest=guest).exclude(stay=stay).exists()


def _same_person(name, other) -> bool:
    """Two names are the same person's for the rooming list: equal ignoring case, accents and spacing."""

    def plain(value):
        value = unicodedata.normalize("NFKD", value or "")
        return " ".join("".join(ch for ch in value if not unicodedata.combining(ch)).casefold().split())

    return bool(plain(name)) and plain(name) == plain(other)


def _put_first(stay, guest, *, drop=None) -> None:
    """Make `guest` the room's first occupant (the rooming list reads the first one), keeping the others after
    it; `drop` (the first occupant it replaces) leaves the room."""
    through = Stay.occupants.through
    skip = {guest.pk, drop.pk if drop is not None else None}
    links = through.objects.filter(stay=stay).order_by("id")
    others = [link.guest_id for link in links if link.guest_id not in skip]
    stay.occupants.clear()
    stay.occupants.add(guest)
    for guest_id in others:
        stay.occupants.add(guest_id)


def set_rooming_name(stay, *, first_name, last_name="", actor=None) -> Stay:
    """Name of the guest in this room (the rooming list): the stay's first occupant.

    - the booker's own name links the booker to the room (no namesake guest is created);
    - a name-only guest typed here before is renamed in place;
    - any other first occupant (a real guest) stays in the organization and is replaced on this room by a new
      guest with that name, kept first;
    - an empty name removes a name-only first occupant.

    Audits `bookings.rooming_updated`."""
    from apps.guests.services import update_guest, upsert_guest
    from apps.guests.types import GuestInput

    first_name, last_name = (first_name or "").strip(), (last_name or "").strip()
    with transaction.atomic():
        Reservation.objects.select_for_update().filter(pk=stay.reservation_id).values_list(
            "pk", flat=True
        ).first()
        stay = (
            Stay.objects.select_for_update(of=("self",))
            .select_related("reservation__property", "reservation__booker", "room", "bed", "room_type")
            .get(pk=stay.pk)
        )
        if stay.status in ("cancelled", "no_show"):
            raise InvalidStateError("La habitación está cancelada")
        prop = stay.reservation.property
        booker = stay.reservation.booker
        link = _first_link(stay)
        current = link.guest if link else None
        placeholder = current if current is not None and _is_placeholder(current, stay) else None
        old_name = current.full_name if current else ""
        typed = f"{first_name} {last_name}".strip()
        if not typed:
            if placeholder is None:
                return stay
            stay.occupants.remove(placeholder)
            new_name = ""
        elif _same_person(typed, booker.full_name):
            if current is not None and current.pk == booker.pk:
                return stay
            _put_first(stay, booker, drop=current)
            new_name = booker.full_name
        elif placeholder is not None:
            update_guest(
                placeholder, {"first_name": first_name, "last_name": last_name}, source="user", actor=actor
            )
            new_name = typed
        else:
            if not first_name:
                raise BookingError(
                    "Escribe al menos el nombre",
                    code="validation_error",
                    fields={"first_name": ["Requerido"]},
                )
            guest = upsert_guest(
                prop.organization, GuestInput(first_name=first_name, last_name=last_name), actor=actor
            )
            _put_first(stay, guest, drop=current)
            new_name = guest.full_name
        where = (
            f"la cama {stay.room.number}-{stay.bed.label}"
            if stay.bed_id
            else (f"la habitación {stay.room.number}" if stay.room_id else f"una {stay.room_type.code}")
        )
        audit.record(
            action="bookings.rooming_updated",
            target=stay,
            summary=f"Rooming list de {stay.reservation.code}: {new_name or 'sin nombre'} en {where}",
            actor=actor,
            source="user" if _user(actor) else "system",
            property=prop,
            changes={"guest": [old_name or None, new_name or None]},
        )
    return stay


def delete_group(group, *, actor=None) -> None:
    """Delete a group: its unreleased allotments give their rooms back to general inventory first, its
    reservations stay (without group) and the rooms picked up keep their reservations. Audits
    `bookings.group_deleted`."""
    with transaction.atomic():
        group = ReservationGroup.objects.select_for_update().select_related("property").get(pk=group.pk)
        for block in GroupBlock.objects.filter(group=group, released_at__isnull=True):
            release_block(block, actor=actor)
        audit.record(
            action="bookings.group_deleted",
            target=group.property,
            summary=f"Borró el grupo {group.name}",
            actor=actor,
            source="user" if _user(actor) else "system",
            property=group.property,
            changes={"group_id": [str(group.pk), None], "name": [group.name, None]},
        )
        group.delete()
