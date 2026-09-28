"""Maintenance tickets (plan C2): a reported problem, optionally blocking its room.

- `blocks_room` → `inventory.block_room(kind="out_of_order")` from the business date to `blocked_until`
  (exclusive; one night by default) and the room goes `out_of_service`. Bookings assigned to the room in
  those dates → 409 `room_has_reservations` unless `force` (they are not moved: that is front desk work).
- Resolving releases the block (`inventory.release_block`) and sends the room to cleaning (`dirty`, which
  creates its clean through the receiver); cancelling or deleting releases it and restores the status the
  room had before the ticket.
- Photos are private (apps/housekeeping/storage.py): JPEG/PNG/WebP/HEIC recognized by their content,
  ≤ 10 MB, at most 6 per ticket.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.bookings.models import ACTIVE_STAY_STATUSES, Stay
from apps.core import audit
from apps.core.errors import ConflictError, DomainError
from apps.core.permissions import has_perm
from apps.housekeeping.models import MaintenanceTicket, Priority, TicketPhoto
from apps.housekeeping.services.common import user_or_none
from apps.inventory.models import Room, RoomBlock
from apps.inventory.services import block_room, release_block, set_housekeeping_status

Status = MaintenanceTicket.Status
OPEN_STATUSES = (Status.OPEN, Status.IN_PROGRESS)
OUT_OF_SERVICE = Room.HousekeepingStatus.OUT_OF_SERVICE
DIRTY = Room.HousekeepingStatus.DIRTY
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_PHOTOS = 6
HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}


def can_maintain(user, property) -> bool:
    return bool(user and user.is_active and has_perm(user, property, "housekeeping.maintenance"))


def _closed() -> ConflictError:
    return ConflictError("El ticket ya está cerrado", code="ticket_closed")


def _field_error(message: str, code: str, field: str) -> DomainError:
    return DomainError(message, code=code, fields={field: [message]})


def _record(ticket, action, *, actor, summary, changes=None) -> None:
    audit.record(
        action=action,
        target=ticket,
        actor=actor,
        source="user" if user_or_none(actor) else "system",
        property=ticket.property,
        summary=f"Mantenimiento «{ticket.title}»: {summary}",
        changes=changes or {},
    )


def _lock(ticket) -> MaintenanceTicket:
    return (
        MaintenanceTicket.objects.select_for_update(of=("self",))
        .select_related("property", "room", "block")
        .get(pk=ticket.pk)
    )


def _check_assignee(user, property) -> None:
    if user is not None and not can_maintain(user, property):
        raise _field_error(
            "Esa persona no atiende mantenimiento en este hotel", "invalid_assignee", "assigned_to"
        )


def _block(ticket, *, until, actor, force) -> None:
    room = Room.objects.select_related("property").get(pk=ticket.room_id)
    today = ticket.property.business_date
    until = until or today + timedelta(days=1)
    if until <= today:
        raise _field_error("El bloqueo debe terminar después de hoy", "invalid_dates", "blocked_until")
    codes = sorted(
        set(
            Stay.objects.filter(
                room=room, status__in=ACTIVE_STAY_STATUSES, checkin_date__lt=until, checkout_date__gt=today
            ).values_list("reservation__code", flat=True)
        )
    )
    if codes and not force:
        raise ConflictError(
            f"La habitación {room.number} tiene reservas en esas fechas: {', '.join(codes)}",
            code="room_has_reservations",
            reservations=codes,
        )
    block = block_room(
        room,
        start=today,
        end=until,
        kind=RoomBlock.Kind.OUT_OF_ORDER,
        reason=f"Mantenimiento: {ticket.title}",
        actor=actor,
    )
    if room.housekeeping_status != OUT_OF_SERVICE:
        ticket.room_status_before = room.housekeeping_status
    ticket.block, ticket.blocks_room, ticket.blocked_until = block, True, until
    ticket.save(update_fields=["block", "blocks_room", "blocked_until", "room_status_before", "updated_at"])
    set_housekeeping_status(room, OUT_OF_SERVICE, actor=actor, source="user")


def _unblock(ticket, *, actor, restore: str | None) -> None:
    """Release the ticket's block and, if the room is out of service, set it to `restore` (None = leave
    it as it is)."""
    if ticket.block_id:
        release_block(RoomBlock.objects.get(pk=ticket.block_id), actor=actor)
    if ticket.blocks_room:
        ticket.blocks_room = False
        ticket.save(update_fields=["blocks_room", "updated_at"])
    if ticket.room_id and restore:
        room = Room.objects.select_related("property").get(pk=ticket.room_id)
        if room.housekeeping_status == OUT_OF_SERVICE and restore != OUT_OF_SERVICE:
            set_housekeeping_status(room, restore, actor=actor, source="user")


def _after_repair(ticket) -> str | None:
    """Status of the room once the problem is fixed: to cleaning, unless it was already out of service
    before this ticket (another reason keeps it out)."""
    return DIRTY if ticket.room_status_before else None


def hold_blocked_room(room) -> bool:
    """Keep a room held by a blocking ticket out of service when it turns dirty behind the ticket's back.

    A check-out (or an in-house guest moved to another room) always leaves the room `dirty`, even when an open
    ticket blocks it from today (e.g. the guest of a room with a broken air conditioner leaves today). The
    room must stay out of service until the repair: it goes back to `out_of_service` and the ticket remembers
    that it needs cleaning (resolving or cancelling it sends the room to cleaning). True if it was held."""
    today = room.property.business_date
    with transaction.atomic():
        ticket = (
            MaintenanceTicket.objects.select_for_update(of=("self",))
            .filter(
                room=room,
                blocks_room=True,
                status__in=OPEN_STATUSES,
                block__released_at__isnull=True,
                block__start_date__lte=today,
                block__end_date__gt=today,
            )
            .order_by("created_at")
            .first()
        )
        if ticket is None:
            return False
        if ticket.room_status_before != DIRTY:
            ticket.room_status_before = DIRTY
            ticket.save(update_fields=["room_status_before", "updated_at"])
        set_housekeeping_status(room, OUT_OF_SERVICE, source="automation")
    return True


def create_ticket(
    property,
    *,
    title,
    room=None,
    description: str = "",
    location: str = "",
    priority=Priority.NORMAL,
    blocks_room: bool = False,
    blocked_until=None,
    assigned_to=None,
    actor=None,
    force: bool = False,
) -> MaintenanceTicket:
    title = (title or "").strip()
    if not title:
        raise _field_error("Escribe qué pasó", "title_required", "title")
    if priority not in Priority.values:
        raise _field_error(f"Prioridad inválida: {priority}", "invalid_priority", "priority")
    if room is not None and room.property_id != property.pk:
        raise _field_error("La habitación no pertenece a este hotel", "invalid_room", "room")
    if blocks_room and room is None:
        raise _field_error("Para bloquear una habitación, elige cuál", "room_required", "room")
    _check_assignee(assigned_to, property)
    with transaction.atomic():
        ticket = MaintenanceTicket.objects.create(
            property=property,
            room=room,
            location=(location or "").strip(),
            title=title,
            description=(description or "").strip(),
            priority=priority,
            reported_by=user_or_none(actor),
            assigned_to=assigned_to,
        )
        if blocks_room:
            _block(ticket, until=blocked_until, actor=actor, force=force)
        where = f"habitación {room.number}" if room else (ticket.location or "áreas comunes")
        _record(
            ticket,
            "housekeeping.ticket_created",
            actor=actor,
            summary=f"reportado en {where}" + (" (habitación bloqueada)" if blocks_room else ""),
            changes={"status": [None, ticket.status], "blocks_room": [None, ticket.blocks_room]},
        )
    return ticket


def update_ticket(ticket, data: dict, *, actor=None, force: bool = False) -> MaintenanceTicket:
    """Edit an open ticket: title, description, location, priority, assigned_to, blocks_room, blocked_until.
    Moving `blocked_until` replaces the block; turning `blocks_room` off releases it (room → cleaning)."""
    with transaction.atomic():
        ticket = _lock(ticket)
        if ticket.status not in OPEN_STATUSES:
            raise _closed()
        changes, fields = {}, []
        if "title" in data:
            title = (data["title"] or "").strip()
            if not title:
                raise _field_error("Escribe qué pasó", "title_required", "title")
            data = {**data, "title": title}
        if "priority" in data and data["priority"] not in Priority.values:
            raise _field_error(f"Prioridad inválida: {data['priority']}", "invalid_priority", "priority")
        if "assigned_to" in data:
            _check_assignee(data["assigned_to"], ticket.property)
        for field in ("title", "description", "location", "priority", "assigned_to"):
            if field in data and getattr(ticket, field) != data[field]:
                before = getattr(ticket, field)
                changes[field] = [str(before.pk) if hasattr(before, "pk") else before, _plain(data[field])]
                setattr(ticket, field, data[field])
                fields.append(field)
        if fields:
            ticket.save(update_fields=[*fields, "updated_at"])
        wants_block = data.get("blocks_room", ticket.blocks_room)
        if wants_block and ticket.room_id is None:
            raise _field_error("Para bloquear una habitación, elige cuál", "room_required", "room")
        if wants_block and not ticket.blocks_room:
            _block(ticket, until=data.get("blocked_until"), actor=actor, force=force)
            changes["blocks_room"] = [False, True]
        elif not wants_block and ticket.blocks_room:
            _unblock(ticket, actor=actor, restore=_after_repair(ticket))
            changes["blocks_room"] = [True, False]
        elif wants_block and data.get("blocked_until") and data["blocked_until"] != ticket.blocked_until:
            old_until = ticket.blocked_until
            if ticket.block_id:
                release_block(RoomBlock.objects.get(pk=ticket.block_id), actor=actor)
            _block(ticket, until=data["blocked_until"], actor=actor, force=force)
            changes["blocked_until"] = [_plain(old_until), _plain(ticket.blocked_until)]
        if changes:
            _record(
                ticket, "housekeeping.ticket_updated", actor=actor, summary="actualizado", changes=changes
            )
    return ticket


def _plain(value):
    if hasattr(value, "pk"):
        return str(value.pk)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def start_ticket(ticket, *, actor) -> MaintenanceTicket:
    with transaction.atomic():
        ticket = _lock(ticket)
        if ticket.status != Status.OPEN:
            raise (
                _closed()
                if ticket.status not in OPEN_STATUSES
                else ConflictError("El ticket ya está en curso", code="invalid_state")
            )
        ticket.status, ticket.started_at = Status.IN_PROGRESS, timezone.now()
        if ticket.assigned_to_id is None and can_maintain(user_or_none(actor), ticket.property):
            ticket.assigned_to = actor
        ticket.save(update_fields=["status", "started_at", "assigned_to", "updated_at"])
        _record(
            ticket,
            "housekeeping.ticket_started",
            actor=actor,
            summary="en curso",
            changes={"status": [Status.OPEN, Status.IN_PROGRESS]},
        )
    return ticket


def resolve_ticket(ticket, *, actor, notes: str = "") -> MaintenanceTicket:
    with transaction.atomic():
        ticket = _lock(ticket)
        if ticket.status not in OPEN_STATUSES:
            raise _closed()
        old = ticket.status
        ticket.status, ticket.resolved_at, ticket.resolved_by = (
            Status.RESOLVED,
            timezone.now(),
            user_or_none(actor),
        )
        ticket.resolution_notes = (notes or "").strip()
        ticket.save(update_fields=["status", "resolved_at", "resolved_by", "resolution_notes", "updated_at"])
        if ticket.blocks_room or ticket.block_id:
            _unblock(ticket, actor=actor, restore=_after_repair(ticket))
        _record(
            ticket,
            "housekeeping.ticket_resolved",
            actor=actor,
            summary="resuelto",
            changes={"status": [old, ticket.status]},
        )
    return ticket


def cancel_ticket(ticket, *, actor, reason: str = "") -> MaintenanceTicket:
    with transaction.atomic():
        ticket = _lock(ticket)
        if ticket.status not in OPEN_STATUSES:
            raise _closed()
        old = ticket.status
        ticket.status = Status.CANCELLED
        ticket.resolution_notes = (reason or "").strip()
        ticket.save(update_fields=["status", "resolution_notes", "updated_at"])
        if ticket.blocks_room or ticket.block_id:
            _unblock(ticket, actor=actor, restore=ticket.room_status_before or None)
        _record(
            ticket,
            "housekeeping.ticket_cancelled",
            actor=actor,
            summary="cancelado",
            changes={"status": [old, ticket.status]},
        )
    return ticket


def delete_ticket(ticket, *, actor) -> None:
    with transaction.atomic():
        ticket = _lock(ticket)
        if ticket.status in OPEN_STATUSES and (ticket.blocks_room or ticket.block_id):
            _unblock(ticket, actor=actor, restore=ticket.room_status_before or None)
        files = list(ticket.photos.values_list("image", flat=True))
        _record(ticket, "housekeeping.ticket_deleted", actor=actor, summary="eliminado")
        ticket.delete()
        _delete_files_on_commit(files)


# ---- Photos ---------------------------------------------------------------------------------------------


def sniff_photo(head: bytes) -> tuple[str, str] | None:
    """(extension, content type) of a JPEG / PNG / WebP / HEIC image recognized by its first bytes."""
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp", "image/webp"
    if head[4:8] == b"ftyp" and head[8:12] in HEIF_BRANDS:
        return ".heic", "image/heic"
    return None


def check_photo(file) -> tuple[str, str]:
    """Validate an uploaded photo (size, recognized image content) → (extension, content type)."""
    size = getattr(file, "size", None) or 0
    if size > MAX_PHOTO_BYTES:
        raise DomainError("La foto supera el máximo de 10 MB", code="file_too_large")
    file.seek(0)
    sniffed = sniff_photo(file.read(16))
    file.seek(0)
    if sniffed is None:
        raise DomainError(
            "Formato no admitido: sube una foto (JPG, PNG, WebP o HEIC)", code="invalid_file_type"
        )
    return sniffed


def check_photos(files, *, existing: int = 0) -> None:
    """Validate a batch before writing anything (a ticket reported with photos is created all or nothing)."""
    if existing + len(files) > MAX_PHOTOS:
        raise DomainError(f"Un ticket admite hasta {MAX_PHOTOS} fotos", code="too_many_photos")
    for file in files:
        check_photo(file)


def add_photo(ticket, *, file, actor=None) -> TicketPhoto:
    if ticket.photos.count() >= MAX_PHOTOS:
        raise DomainError(f"Un ticket admite hasta {MAX_PHOTOS} fotos", code="too_many_photos")
    extension, content_type = check_photo(file)
    size = getattr(file, "size", None) or 0
    file.name = f"photo{extension}"
    with transaction.atomic():
        photo = TicketPhoto.objects.create(
            ticket=ticket, image=file, content_type=content_type, size=size, uploaded_by=user_or_none(actor)
        )
        _record(ticket, "housekeeping.ticket_photo_added", actor=actor, summary="foto agregada")
    return photo


def delete_photo(photo, *, actor=None) -> None:
    with transaction.atomic():
        name = photo.image.name
        _record(photo.ticket, "housekeeping.ticket_photo_deleted", actor=actor, summary="foto eliminada")
        photo.delete()
        _delete_files_on_commit([name])


def _delete_files_on_commit(names: list[str]) -> None:
    storage = TicketPhoto._meta.get_field("image").storage
    transaction.on_commit(lambda: [storage.delete(name) for name in names if name])
