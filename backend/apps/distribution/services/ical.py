"""iCal channel (plan C3 › iCal): export calendars for listing sites and import theirs.

Export — `GET /api/v1/public/distribution/ical/<token>.ics` (secret token per `RoomMapping`), all-day events
whose DTEND is the exclusive checkout date, stable UIDs and no guest data:

- a private room (or a category with a single room): one event per stay (`stay-<id>@housetel.co`, "Reservado")
  and per active block (`block-<id>@housetel.co`, "Bloqueado");
- a category with several units, a dorm category or a dorm room: the nights it cannot sell anything, merged
  into ranges (`closed-<mapping>-<YYYYMMDD>@housetel.co`, "No disponible").

The window goes from a week before the business date to a year after it. Cancelled and no-show stays are
never exported.

Import — `pull_ical(property)` (automation `distribution.pull_ical`, every 15 minutes) downloads the
`ical_import_url` of every mapping through the `channel_ical` provider of the configured mode and turns each
reservation event into an OTA reservation (`importer.import_booking`: `external_id` = UID, placeholder guest
"Huésped <canal>", PMS prices). Blocks ("Not available") and events that already ended are ignored. An event
that disappears cancels its reservation, only if the reservation is still pending (not started) and the
calendar was not empty: an empty or unreachable calendar never cancels anything. A URL that is a Housetel
export is read locally in every mode (and a property never imports its own calendars back).
"""

import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import icalendar
from django.db.models import Q
from django.utils import timezone

from apps.bookings.models import Reservation, Stay
from apps.bookings.services.availability import availability_by_date
from apps.core import alerts, integrations
from apps.core.dates import daterange
from apps.core.runtime import public_base_url
from apps.distribution.errors import CalendarSkipped, ChannelError
from apps.distribution.models import ChannelConnection, ExternalReservationMap, RoomMapping, SyncLog
from apps.distribution.services.importer import import_booking
from apps.distribution.services.logs import log
from apps.distribution.types import InboundBooking, InboundRoom
from apps.inventory.models import RoomBlock, RoomType

logger = logging.getLogger("housetel.distribution")

EXPORT_PAST_DAYS = 7
EXPORT_FUTURE_DAYS = 365
EXPORTED_STAY_STATUSES = ["tentative", "confirmed", "checked_in", "checked_out"]
EXPORT_PATH = "/api/v1/public/distribution/ical/{token}.ics"
TOKEN_IN_URL = re.compile(r"/api/v1/public/distribution/ical/(?P<token>[A-Za-z0-9_-]{8,64})\.ics$")
BLOCK_MARKERS = ("not available", "unavailable", "blocked", "closed", "no disponible", "bloquead")
PENDING_STATUSES = (Reservation.Status.TENTATIVE, Reservation.Status.CONFIRMED)
EMPTY_CALENDAR = "El calendario llegó vacío: no se canceló ninguna reserva"
OWN_CALENDAR = "Esta URL es un calendario exportado por este mismo hotel: no se importa"


# --- export -------------------------------------------------------------------------------------------------


def export_url(mapping) -> str:
    """Public URL of the mapping's calendar (what the listing site imports): `core.runtime.public_base_url()`,
    so behind a tunnel (PUBLIC_BASE_URL) Airbnb or Booking.com can reach it from outside."""
    return public_base_url() + EXPORT_PATH.format(token=mapping.ical_export_token)


def export_window(prop) -> tuple[date, date]:
    today = prop.business_date
    return today - timedelta(days=EXPORT_PAST_DAYS), today + timedelta(days=EXPORT_FUTURE_DAYS)


def export_calendar(mapping) -> bytes:
    """The VCALENDAR of one mapping (see the module docstring)."""
    prop = mapping.connection.property
    calendar = icalendar.Calendar()
    calendar.add("prodid", "-//Housetel//Channel manager//ES")
    calendar.add("version", "2.0")
    calendar.add("calscale", "GREGORIAN")
    calendar.add("method", "PUBLISH")
    calendar.add("x-wr-calname", f"{prop.name} · {_unit_label(mapping)}")
    stamp = timezone.now()
    for uid, start, end, summary in export_events(mapping):
        event = icalendar.Event()
        event.add("uid", uid)
        event.add("dtstamp", stamp)
        event.add("dtstart", start)
        event.add("dtend", end)
        event.add("summary", summary)
        event.add("transp", "OPAQUE")
        calendar.add_component(event)
    return calendar.to_ical()


def export_events(mapping) -> list[tuple[str, date, date, str]]:
    """(uid, start, end exclusive, summary) of what the mapping's calendar shows."""
    prop = mapping.connection.property
    room_type = mapping.room_type
    room = mapping.room
    if room is not None:
        if room.room_type.kind == RoomType.Kind.DORM:
            return _closed_events(mapping, _dorm_room_closed_nights(prop, room))
        return _stay_and_block_events(prop, stays=Q(room=room), blocks=Q(room=room))
    units = list(room_type.rooms.filter(is_active=True).values_list("pk", flat=True)[:2])
    if room_type.kind == RoomType.Kind.PRIVATE and len(units) == 1:
        unit = units[0]
        return _stay_and_block_events(
            prop, stays=Q(room_id=unit) | Q(room__isnull=True, room_type=room_type), blocks=Q(room_id=unit)
        )
    return _closed_events(mapping, _category_closed_nights(prop, room_type))


def _unit_label(mapping) -> str:
    from apps.core.i18n import t

    if mapping.room is not None:
        return f"{t(mapping.room_type.name)} {mapping.room.number}"
    return t(mapping.room_type.name) or mapping.room_type.code


def _stay_and_block_events(prop, *, stays: Q, blocks: Q) -> list[tuple]:
    start, end = export_window(prop)
    events = [
        (f"stay-{stay_id}@housetel.co", checkin, checkout, "Reservado")
        for stay_id, checkin, checkout in Stay.objects.filter(
            stays,
            reservation__property=prop,
            status__in=EXPORTED_STAY_STATUSES,
            checkout_date__gt=start,
            checkin_date__lt=end,
        )
        .order_by("checkin_date", "pk")
        .values_list("pk", "checkin_date", "checkout_date")
    ]
    events += [
        (f"block-{block_id}@housetel.co", block_start, block_end, "Bloqueado")
        for block_id, block_start, block_end in RoomBlock.objects.filter(
            blocks, released_at__isnull=True, end_date__gt=start, start_date__lt=end
        )
        .order_by("start_date", "pk")
        .values_list("pk", "start_date", "end_date")
    ]
    return events


def _category_closed_nights(prop, room_type) -> list[date]:
    """Nights from the business date on where the category has no unit left (InventoryDay)."""
    _start, end = export_window(prop)
    by_date = availability_by_date(
        property=prop, start=prop.business_date, end=end, room_type_ids=[room_type.pk]
    )
    units = by_date.get(room_type.pk)
    if units is None:  # inactive category: it sells nothing
        return list(daterange(prop.business_date, end))
    return [night for night, available in units.items() if available <= 0]


def _dorm_room_closed_nights(prop, room) -> list[date]:
    """Nights from the business date on where every active bed of the dorm room is taken or blocked."""
    _start, end = export_window(prop)
    today = prop.business_date
    beds = set(room.beds.filter(is_active=True).values_list("pk", flat=True))
    if not beds or not room.is_active:
        return list(daterange(today, end))
    taken: dict[date, set] = {}
    for bed_id, checkin, checkout in Stay.objects.filter(
        room=room,
        bed__isnull=False,
        status__in=["tentative", "confirmed", "checked_in"],
        checkout_date__gt=today,
        checkin_date__lt=end,
    ).values_list("bed_id", "checkin_date", "checkout_date"):
        for night in daterange(max(checkin, today), min(checkout, end)):
            taken.setdefault(night, set()).add(bed_id)
    for bed_id, block_start, block_end in RoomBlock.objects.filter(
        room=room, released_at__isnull=True, end_date__gt=today, start_date__lt=end
    ).values_list("bed_id", "start_date", "end_date"):
        for night in daterange(max(block_start, today), min(block_end, end)):
            taken.setdefault(night, set()).update(beds if bed_id is None else {bed_id})
    return sorted(night for night, occupied in taken.items() if beds <= occupied)


def _closed_events(mapping, nights: list[date]) -> list[tuple]:
    events = []
    for start, end in _ranges(nights):
        events.append((f"closed-{mapping.pk}-{start:%Y%m%d}@housetel.co", start, end, "No disponible"))
    return events


def _ranges(nights: list[date]) -> list[tuple[date, date]]:
    """Consecutive nights merged into half-open ranges."""
    ranges: list[list[date]] = []
    for night in sorted(set(nights)):
        if ranges and ranges[-1][1] == night:
            ranges[-1][1] = night + timedelta(days=1)
        else:
            ranges.append([night, night + timedelta(days=1)])
    return [(start, end) for start, end in ranges]


def mapping_for_token(token: str):
    return (
        RoomMapping.objects.select_related("connection__property", "room_type", "room__room_type")
        .filter(ical_export_token=token, connection__channel_code=ChannelConnection.Channel.ICAL)
        .first()
    )


def local_export_mapping(url: str):
    """The Housetel mapping a URL exports (any host), or None when the URL is not one of our exports."""
    match = TOKEN_IN_URL.search(urlsplit(url).path or "")
    return mapping_for_token(match.group("token")) if match else None


# --- import -------------------------------------------------------------------------------------------------


def parse_events(text) -> list[dict]:
    """VEVENTs of an iCal document as `{uid, start, end, summary, description, cancelled}` (dates; DTEND
    exclusive). Raises ChannelError when the document is not iCal."""
    try:
        calendar = icalendar.Calendar.from_ical(text)
    except (ValueError, IndexError, KeyError) as exc:
        raise ChannelError(f"El calendario no es un archivo iCal válido ({exc})", retryable=False) from exc
    tz = ZoneInfo("America/Bogota")
    events = []
    for component in calendar.walk("VEVENT"):
        uid = str(component.get("uid") or "").strip()
        if not uid or component.get("dtstart") is None:
            continue
        start = _as_date(component.decoded("dtstart"), tz)
        if component.get("dtend") is not None:
            end = _as_date(component.decoded("dtend"), tz)
        elif component.get("duration") is not None:
            end = start + max(component.decoded("duration").days, 1) * timedelta(days=1)
        else:
            end = start + timedelta(days=1)
        if end <= start:
            end = start + timedelta(days=1)
        events.append(
            {
                "uid": uid[:120],
                "start": start,
                "end": end,
                "summary": str(component.get("summary") or "").strip(),
                "description": str(component.get("description") or "").strip(),
                "cancelled": str(component.get("status") or "").upper() == "CANCELLED",
            }
        )
    return events


def _as_date(value, tz) -> date:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(tz)
        return value.date()
    return value


def is_block(event: dict) -> bool:
    summary = event["summary"].lower()
    return any(marker in summary for marker in BLOCK_MARKERS)


def pull_ical(property, *, connection=None) -> dict:
    """Import the remote calendars of the property's iCal connections (or only `connection`); returns the
    counts `created, modified, cancelled, unchanged, failed, skipped, calendars`."""
    summary = Counter(
        {key: 0 for key in ("created", "modified", "cancelled", "unchanged", "failed", "skipped")}
    )
    connections = ChannelConnection.objects.filter(
        property=property, channel_code=ChannelConnection.Channel.ICAL
    ).exclude(status=ChannelConnection.Status.PAUSED)
    if connection is not None:
        connections = connections.filter(pk=connection.pk)
    connections = list(connections)
    if not connections:
        return dict(summary, calendars=0)
    setting = integrations.get_setting(property, "channel_ical")
    if not setting.enabled:
        return dict(summary, calendars=0, disabled=True)
    provider = integrations.get_provider(property, "channel_ical")
    calendars = 0
    for conn in connections:
        mappings = conn.room_mappings.select_related("room_type", "room").exclude(ical_import_url="")
        pulled = False
        for mapping in mappings:
            calendars += 1
            pulled |= _pull_mapping(conn, mapping, provider, summary)
        if pulled:
            conn.last_sync_at = timezone.now()
            conn.save(update_fields=["last_sync_at", "updated_at"])
    return dict(summary, calendars=calendars)


def _pull_mapping(connection, mapping, provider, summary) -> bool:
    """Import one calendar; True when it could be read."""
    prop = connection.property
    local = local_export_mapping(mapping.ical_import_url)
    try:
        if local is not None:
            if local.connection.property_id == prop.pk:
                _set_state(connection, mapping, OWN_CALENDAR, SyncLog.Status.WARNING)
                summary["skipped"] += 1
                return False
            text = export_calendar(local)
        else:
            text = provider.fetch_calendar(connection, mapping)
        events = parse_events(text)
    except CalendarSkipped as exc:
        _set_state(connection, mapping, exc.message, SyncLog.Status.SKIPPED)
        summary["skipped"] += 1
        return False
    except ChannelError as exc:
        _calendar_failed(connection, mapping, exc.message)
        summary["failed"] += 1
        return False

    today = prop.business_date
    # Booking.com-style calendars mark every booking "CLOSED - Not available": the connection opts in
    import_all = bool((connection.settings or {}).get("import_all_events"))
    counts = Counter()
    seen = set()
    for event in events:
        if event["cancelled"] or (is_block(event) and not import_all):
            continue
        seen.add(event["uid"])
        if event["end"] <= today:  # already over: history is never rewritten from a calendar
            continue
        result = import_booking(connection, _inbound(connection, mapping, event), quiet_unchanged=True)
        counts[result.action] += 1
    if events:
        stale = ExternalReservationMap.objects.select_related("reservation").filter(
            connection=connection, room_mapping=mapping
        )
        for item in stale.exclude(external_id__in=seen):
            reservation = item.reservation
            if reservation.status not in PENDING_STATUSES or reservation.checkin_date < today:
                continue
            result = import_booking(connection, _cancellation(connection, mapping, item.external_id))
            counts[result.action] += 1
    for action in ("created", "modified", "cancelled", "unchanged", "failed"):
        summary[action] += counts[action]

    mapping.ical_last_sync_at = timezone.now()
    if not events:
        _set_state(connection, mapping, EMPTY_CALENDAR, SyncLog.Status.WARNING, synced=True)
    else:
        _set_state(connection, mapping, "", SyncLog.Status.SUCCESS, synced=True)
        changed = {key: counts[key] for key in ("created", "modified", "cancelled", "failed") if counts[key]}
        if changed:
            log(
                connection,
                SyncLog.Direction.IN,
                "ical_import",
                SyncLog.Status.ERROR if counts["failed"] else SyncLog.Status.SUCCESS,
                f"Calendario de {_unit_label(mapping)}: " + _describe(counts),
                payload={"mapping_id": str(mapping.pk), **dict(counts)},
            )
    alerts.resolve_alert(prop, f"distribution:ical:{mapping.pk}")
    return True


def _inbound(connection, mapping, event) -> InboundBooking:
    room_type = mapping.room_type
    if room_type.kind == RoomType.Kind.DORM:
        adults = 1
    else:
        adults = max(1, min(room_type.base_occupancy or 1, room_type.max_adults or 1))
    notes = f"Importada del calendario iCal de {connection.name}."
    if event["description"]:
        notes += f"\n{event['description'][:1500]}"
    return InboundBooking(
        external_id=event["uid"],
        status="new",
        guest=_placeholder_guest(connection),
        rooms=[
            InboundRoom(
                checkin=event["start"],
                checkout=event["end"],
                adults=adults,
                room_type_id=room_type.pk,
                room_id=mapping.room_id,
            )
        ],
        notes=notes,
        raw={
            "source": "ical",
            "uid": event["uid"],
            "summary": event["summary"],
            "description": event["description"][:1500],
            "start": event["start"].isoformat(),
            "end": event["end"].isoformat(),
        },
        room_mapping_id=mapping.pk,
    )


def _cancellation(connection, mapping, external_id) -> InboundBooking:
    return InboundBooking(
        external_id=external_id,
        status="cancelled",
        guest=_placeholder_guest(connection),
        notes="El evento desapareció del calendario iCal",
        raw={"source": "ical", "uid": external_id, "disappeared": True},
        room_mapping_id=mapping.pk,
    )


def _placeholder_guest(connection) -> dict:
    return {"first_name": "Huésped", "last_name": connection.name[:100]}


def _describe(counts: Counter) -> str:
    labels = (
        ("created", "nueva", "nuevas"),
        ("modified", "modificada", "modificadas"),
        ("cancelled", "cancelada", "canceladas"),
        ("failed", "con error", "con error"),
    )
    parts = [f"{counts[key]} {one if counts[key] == 1 else many}" for key, one, many in labels if counts[key]]
    return ", ".join(parts) or "sin cambios"


def _set_state(connection, mapping, message: str, status: str, *, synced: bool = False) -> None:
    """Store the calendar's state; a changed warning or skip reason leaves one log line (not one per pull)."""
    changed = mapping.ical_last_error != message
    mapping.ical_last_error = message
    fields = ["ical_last_error", "updated_at"]
    if synced:
        fields.append("ical_last_sync_at")
    mapping.save(update_fields=fields)
    if message and changed:
        log(
            connection,
            SyncLog.Direction.IN,
            "ical_import",
            status,
            f"Calendario de {_unit_label(mapping)}: {message}",
            payload={"mapping_id": str(mapping.pk)},
        )


def _calendar_failed(connection, mapping, message: str) -> None:
    prop = connection.property
    text = f"No se pudo leer el calendario: {message}"
    changed = mapping.ical_last_error != text
    mapping.ical_last_error = text
    mapping.save(update_fields=["ical_last_error", "updated_at"])
    if changed:
        log(
            connection,
            SyncLog.Direction.IN,
            "ical_import",
            SyncLog.Status.ERROR,
            f"Calendario de {_unit_label(mapping)}: {text}",
            payload={"mapping_id": str(mapping.pk)},
        )
    alerts.raise_alert(
        property=prop,
        kind="ical_import_failed",
        severity="warning",
        title=f"No se pudo leer el calendario iCal de {connection.name}",
        message=(
            f"{text}. Las reservas nuevas de ese calendario no están llegando al PMS: revisa la URL en "
            "Canales."
        ),
        link="/app/channels",
        dedupe_key=f"distribution:ical:{mapping.pk}",
        data={
            "connection_id": str(connection.pk),
            "connection": connection.name,
            "mapping_id": str(mapping.pk),
            "error": message,
        },
        source="distribution",
    )
