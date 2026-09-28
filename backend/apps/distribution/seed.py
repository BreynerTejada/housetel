"""Distribution demo seed (plan C3 › Seed).

Per property with categories:
- BookSim (+15 %) and AirSim (+12 %) selling the plans FLEX, NR and BB, simulated and mapped category by
  category (`BS-DBL`, `AS-FLEX`…; a property without those plans maps its first public base plan), then the
  explicit first full sync (365 nights in `SimOtaInventory`). The receivers do nothing while seeding, so the
  thousands of historical signals of the bookings seed never reach the queue.
- The hostel also exports its calendars to Airbnb (iCal, one export URL per category).
- The OTA reservations of the bookings seed (`source="ota"`, `booksim`/`airsim`) are linked to their
  connection (`ExternalReservationMap`, with the payload hash of the booking the OTA would send) and appear as
  bookings of the OTA simulator (`SimOtaBooking`, already imported). Dorm parties are one channel room for all
  their beds.

Idempotent: a property that already has connections is skipped.
"""

from collections import defaultdict
from decimal import Decimal

from django.utils import timezone

from apps.bookings.models import Reservation
from apps.distribution.models import (
    ChannelConnection,
    ExternalReservationMap,
    RateMapping,
    RoomMapping,
    SimOtaBooking,
    SyncLog,
)
from apps.distribution.services.importer import booking_payload, payload_hash
from apps.distribution.services.logs import log
from apps.distribution.services.queue import full_sync
from apps.distribution.services.simulator import OTA_LABELS, to_inbound
from apps.inventory.models import RoomType
from apps.rates.models import RatePlan

OTAS = {
    "booksim": {"prefix": "BS", "plans": ("FLEX", "NR", "BB"), "markup": Decimal("15")},
    "airsim": {"prefix": "AS", "plans": ("FLEX", "NR", "BB"), "markup": Decimal("12")},
}
ICAL_PROPERTIES = ("andino_bog",)
LINKED_STATUSES = ["tentative", "confirmed", "checked_in", "checked_out", "cancelled", "no_show"]


def seed(ctx) -> None:
    for key, prop in ctx.properties.items():
        if ChannelConnection.objects.filter(property=prop).exists():
            continue
        room_types = list(
            RoomType.objects.filter(property=prop, is_active=True).order_by("sort_order", "code")
        )
        if not room_types:
            continue
        for channel, config in OTAS.items():
            connection = _connect(prop, channel, config, room_types)
            full_sync(connection)
            linked = _link_reservations(connection)
            ctx.log(f"    {prop.name} · {connection.name}: {len(room_types)} categorías, {linked} reservas")
        if key in ICAL_PROPERTIES:
            ical = ChannelConnection.objects.create(property=prop, channel_code="ical", name="Airbnb")
            RoomMapping.objects.bulk_create(RoomMapping(connection=ical, room_type=rt) for rt in room_types)
            ctx.log(f"    {prop.name} · Airbnb (iCal): {len(room_types)} calendarios exportados")


def _connect(prop, channel, config, room_types) -> ChannelConnection:
    connection = ChannelConnection.objects.create(
        property=prop, channel_code=channel, name=ChannelConnection.Channel(channel).label
    )
    RoomMapping.objects.bulk_create(
        RoomMapping(connection=connection, room_type=rt, external_room_id=f"{config['prefix']}-{rt.code}")
        for rt in room_types
    )
    RateMapping.objects.bulk_create(
        RateMapping(
            connection=connection,
            rate_plan=plan,
            external_rate_id=f"{config['prefix']}-{plan.code}",
            markup_percent=config["markup"],
        )
        for plan in _plans(prop, channel, config["plans"])
    )
    return connection


def _plans(prop, channel, codes) -> list:
    plans = RatePlan.objects.filter(property=prop, is_active=True, is_public=True)
    wanted = [plan for plan in plans.filter(code__in=codes) if not plan.channels or channel in plan.channels]
    if wanted:
        return sorted(wanted, key=lambda plan: codes.index(plan.code))
    fallback = plans.filter(kind=RatePlan.Kind.BASE).order_by("sort_order", "code").first()
    return [fallback] if fallback is not None else []


def _link_reservations(connection) -> int:
    """Link the seeded reservations of this channel and show them as OTA bookings (already imported)."""
    rooms = {mapping.room_type_id: mapping.external_room_id for mapping in connection.room_mappings.all()}
    rates = list(connection.rate_mappings.all())
    reservations = (
        Reservation.objects.filter(
            property=connection.property,
            source=Reservation.Source.OTA,
            channel_code=connection.channel_code,
            status__in=LINKED_STATUSES,
        )
        .exclude(external_id="")
        .select_related("booker")
        .prefetch_related("stays__room_type")
        .order_by("created_at")
    )
    sims, links = [], []
    for reservation in reservations:
        payload = _payload(connection, reservation, rooms, rates)
        if payload is None:
            continue
        cancelled = reservation.status == Reservation.Status.CANCELLED
        sim = SimOtaBooking(
            connection=connection,
            external_id=reservation.external_id,
            status=SimOtaBooking.Status.CANCELLED if cancelled else SimOtaBooking.Status.NEW,
            revision=2 if cancelled else 1,
            payload=payload,
            pms_status=SimOtaBooking.PmsStatus.IMPORTED,
            pms_message=f"Reserva {reservation.code} en el PMS",
        )
        inbound = to_inbound(sim)
        sims.append(sim)
        links.append(
            ExternalReservationMap(
                connection=connection,
                external_id=reservation.external_id,
                reservation=reservation,
                last_payload_hash=payload_hash(inbound),
                last_status=inbound.status,
                last_payload=booking_payload(inbound),
            )
        )
    SimOtaBooking.objects.bulk_create(sims, batch_size=500, ignore_conflicts=True)
    ExternalReservationMap.objects.bulk_create(links, batch_size=500, ignore_conflicts=True)
    if links:
        log(
            connection,
            SyncLog.Direction.IN,
            "booking_history",
            SyncLog.Status.SUCCESS,
            f"{len(links)} reservas del canal vinculadas (historial del demo)",
            payload={"reservations": len(links)},
        )
        ChannelConnection.objects.filter(pk=connection.pk).update(last_sync_at=timezone.now())
    return len(links)


def _payload(connection, reservation, rooms, rates) -> dict | None:
    """The booking as the OTA holds it: one channel room per private stay, one for all the beds of a dorm
    category (nightly totals = Σ nets of its beds)."""
    groups: dict = defaultdict(list)
    for stay in sorted(reservation.stays.all(), key=lambda item: (item.created_at, item.pk)):
        if stay.room_type_id not in rooms:
            return None
        if stay.bed_id or _is_dorm_stay(stay):
            groups[
                ("dorm", stay.room_type_id, stay.rate_plan_id, stay.checkin_date, stay.checkout_date)
            ].append(stay)
        else:
            groups[("room", stay.pk)].append(stay)
    channel_rooms = []
    for stays in groups.values():
        first = stays[0]
        nightly = defaultdict(Decimal)
        for stay in stays:
            for night in stay.nightly_rates or []:
                nightly[night["date"]] += Decimal(str(night.get("net") or night.get("amount") or 0))
        channel_rooms.append(
            {
                "external_room_id": rooms[first.room_type_id],
                "external_rate_id": _rate_for(first, rates),
                "checkin": first.checkin_date.isoformat(),
                "checkout": first.checkout_date.isoformat(),
                "adults": sum(stay.adults for stay in stays) if len(stays) > 1 else first.adults,
                "children": sum(stay.children for stay in stays) if len(stays) > 1 else first.children,
                "nightly_rates": [
                    {"date": day, "amount": f"{amount:.2f}"} for day, amount in sorted(nightly.items())
                ]
                or None,
            }
        )
    booker = reservation.booker
    total = sum(
        (Decimal(night["amount"]) for room in channel_rooms for night in room["nightly_rates"] or []),
        Decimal("0"),
    )
    return {
        "ota": OTA_LABELS.get(connection.channel_code, connection.name),
        "guest": {
            "first_name": booker.first_name,
            "last_name": booker.last_name,
            "email": booker.email,
            "phone": booker.phone,
            "country": booker.nationality,
            "language": reservation.language,
        },
        "rooms": channel_rooms,
        "currency": connection.property.currency or "COP",
        "total": f"{total:.2f}",
        "notes": reservation.special_requests or "",
        "forced": False,
    }


def _is_dorm_stay(stay) -> bool:
    return stay.room_type.kind == RoomType.Kind.DORM


def _rate_for(stay, rates) -> str:
    for mapping in rates:
        if mapping.rate_plan_id == stay.rate_plan_id and mapping.room_type_id in (None, stay.room_type_id):
            return mapping.external_rate_id
    return rates[0].external_rate_id if rates else ""
