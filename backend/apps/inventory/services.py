"""Inventory contracts (spec §4.2 + plan §C). Phase A implements inheritance, blocks, housekeeping
status and the central custom-field validation; B1 completes `provision_room_type` and the API.

Ranges are half-open: a block covers `[start, end)`.
"""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core import audit, signals
from apps.core.errors import ConflictError, DomainError
from apps.inventory.custom_fields import validate_custom_values  # noqa: F401  (contract lives here)
from apps.inventory.models import ROOM_OVERRIDABLE_FIELDS, Bed, Room, RoomBlock, RoomType
from apps.inventory.numbering import duplicates_in, infer_floor, parse_room_numbers


def _user(actor):
    return actor if getattr(actor, "is_authenticated", False) else None


def effective_attributes(room) -> dict:
    """Resolve category → room inheritance.

    Returns every ROOM_OVERRIDABLE_FIELDS key (room override or category value), `amenities` (category codes
    + extra − removed, sorted), merged `custom_values` (room wins), the overridden markers
    (`overridden_fields`, `amenities_added`, `amenities_removed`, `overridden_custom_fields`) and identifiers
    (`room_id`, `room_type_id`, `number`, `room_name`, `floor`, `building`, `kind`). Unknown override
    keys are ignored.
    """
    room_type = room.room_type
    overrides = room.overrides if isinstance(room.overrides, dict) else {}
    attributes: dict = {}
    overridden = []
    for field in ROOM_OVERRIDABLE_FIELDS:
        if field in overrides:
            attributes[field] = overrides[field]
            overridden.append(field)
        else:
            attributes[field] = getattr(room_type, field)
    attributes["size_m2"] = _decimal_or_none(attributes["size_m2"])

    # `.all()` (not values_list) so a prefetched list is reused by list endpoints
    type_amenities = {amenity.code for amenity in room_type.amenities.all()}
    added = {amenity.code for amenity in room.extra_amenities.all()}
    removed = {amenity.code for amenity in room.removed_amenities.all()}
    room_custom = room.custom_values if isinstance(room.custom_values, dict) else {}
    attributes.update(
        {
            "room_id": room.pk,
            "room_type_id": room_type.pk,
            "number": room.number,
            "room_name": room.name,
            "floor": room.floor,
            "building": room.building,
            "kind": room_type.kind,
            "amenities": sorted((type_amenities | added) - removed),
            "amenities_added": sorted(added),
            "amenities_removed": sorted(removed),
            "custom_values": {**(room_type.custom_values or {}), **room_custom},
            "overridden_fields": sorted(overridden),
            "overridden_custom_fields": sorted(room_custom),
        }
    )
    return attributes


def _decimal_or_none(value):
    if value is None or isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def block_room(room, *, start, end, kind, reason, actor=None, bed=None) -> RoomBlock:
    """Take a room (or one dorm bed) out of inventory for `[start, end)`; emits `inventory_changed`.

    Active blocks of the same room cannot overlap (a whole-room block excludes any block of its beds, a bed
    block excludes the whole room and the same bed): ConflictError `block_overlap` (409, extra `block_id`),
    so availability never counts a room twice. Released blocks do not count.
    """
    if not start or not end or end <= start:
        raise DomainError("La fecha final debe ser posterior a la inicial", code="invalid_dates")
    if bed is not None and bed.room_id != room.pk:
        raise DomainError("La cama no pertenece a esta habitación", code="invalid_bed")
    if kind not in RoomBlock.Kind.values:
        raise DomainError(f"Tipo de bloqueo inválido: {kind}", code="invalid_kind")
    with transaction.atomic():
        Room.objects.select_for_update().filter(pk=room.pk).first()  # serializes blocks of one room
        overlapping = RoomBlock.objects.filter(
            room=room, released_at__isnull=True, start_date__lt=end, end_date__gt=start
        )
        if bed is not None:
            overlapping = overlapping.filter(Q(bed__isnull=True) | Q(bed=bed))
        clash = overlapping.order_by("start_date").first()
        if clash is not None:
            raise ConflictError(
                f"Ya hay un bloqueo activo del {clash.start_date} al {clash.end_date} en esas fechas",
                code="block_overlap",
                block_id=str(clash.pk),
            )
        block = RoomBlock.objects.create(
            room=room,
            bed=bed,
            start_date=start,
            end_date=end,
            kind=kind,
            reason=reason or "",
            created_by=_user(actor),
        )
        target = f"{room.number}-{bed.label}" if bed is not None else room.number
        audit.record(
            action="inventory.room_blocked",
            target=block,
            actor=actor,
            property=room.property,
            summary=f"Bloqueó {target} del {start} al {end} ({kind})",
            changes={"start_date": [None, start], "end_date": [None, end], "kind": [None, kind]},
        )
        signals.send_on_commit(
            signals.inventory_changed,
            property=room.property,
            room_type_ids=[room.room_type_id],
            start=start,
            end=end,
        )
    return block


def release_block(block, *, actor=None) -> RoomBlock:
    """Release a block (idempotent); emits `inventory_changed` for its range the first time."""
    if block.released_at is not None:
        return block
    with transaction.atomic():
        locked = (
            RoomBlock.objects.select_for_update().select_related("room", "room__property").get(pk=block.pk)
        )
        if locked.released_at is None:
            locked.released_at = timezone.now()
            locked.save(update_fields=["released_at", "updated_at"])
            audit.record(
                action="inventory.block_released",
                target=locked,
                actor=actor,
                property=locked.room.property,
                summary=f"Liberó el bloqueo de {locked.room.number}",
                changes={"released_at": [None, locked.released_at]},
            )
            signals.send_on_commit(
                signals.inventory_changed,
                property=locked.room.property,
                room_type_ids=[locked.room.room_type_id],
                start=locked.start_date,
                end=locked.end_date,
            )
    block.released_at = locked.released_at
    return locked


def set_housekeeping_status(room, status, *, actor=None, source="user") -> Room:
    """Change a room's housekeeping status; emits `room_status_changed(room, old, new)` when it changes."""
    if status not in Room.HousekeepingStatus.values:
        raise DomainError(f"Estado de limpieza inválido: {status}", code="invalid_status")
    with transaction.atomic():
        old = Room.objects.select_for_update().values_list("housekeeping_status", flat=True).get(pk=room.pk)
        room.housekeeping_status = status
        if old == status:
            return room
        room.save(update_fields=["housekeeping_status", "updated_at"])
        audit.record(
            action="inventory.room_status_changed",
            target=room,
            actor=actor,
            source=source,
            property=room.property,
            summary=f"Habitación {room.number}: {old} → {status}",
            changes={"housekeeping_status": [old, status]},
        )
        signals.send_on_commit(signals.room_status_changed, room=room, old=old, new=status)
    return room


def provision_room_type(
    property,
    *,
    data: dict,
    room_numbers: list[str],
    floor: str | None = None,
    beds_per_room: int | None = None,
    actor=None,
) -> RoomType:
    """Create a category with its rooms (and beds for dorms) in one atomic call. Used by AI onboarding (C9)
    and signup (C11).

    data: RoomType keys (code, name{es,en}, description, kind, base_occupancy, max_adults, max_children,
    max_occupancy, beds, size_m2, view, smoking_allowed, accessible, amenities[codes], color,
    housekeeping_minutes, sort_order, is_active, custom_values), validated exactly like the API
    (`RoomTypeSerializer`); unknown keys are ignored, so a generated proposal can be passed as it is.
    Safe normalizations: a plain-string name/description is Spanish; the code is made valid ("Suite Vista"
    → "SUITE-VISTA", at most 20 characters) or, when missing or unusable, derived from the name and kept
    unique; `kind` and bed types are case-insensitive; `size_m2` is rounded to 2 decimals; missing
    occupancy values are filled; dorm occupancy is always 1 per bed.
    room_numbers: numbers or ranges (["101-110", "201"], ints accepted); may be empty (category only).
    floor: None infers each room's floor from its number ("305" → "3"); "" leaves it empty.
    beds_per_room (dorms only, 1–50 when rooms are created): beds per room, labeled C1…Cn; None → counted
    from `data["beds"]` (a bunk counts twice). Ignored for private categories.

    Errors (nothing is created): DomainError `validation_error` (fields: `data`, any RoomType field,
    `floor`, `beds_per_room` — also when a dorm room would get no bed), `invalid_room_numbers`,
    `duplicate_room_numbers` (extra `duplicates`: numbers that exist or repeat). Concurrent calls for one
    property are serialized (the property row is locked), so the loser gets one of these errors, never an
    IntegrityError. Works inside the caller's transaction. Audits `inventory.room_type_provisioned` and emits
    `inventory_changed(start=None, end=None)` on commit.
    """
    from apps.core.models import Property
    from apps.inventory.serializers import RoomTypeSerializer, sanitize_code, validated

    if not isinstance(data, dict):
        raise DomainError(
            "Los datos de la categoría deben ser un objeto", code="validation_error",
            fields={"data": ["Debe ser un objeto"]},
        )  # fmt: skip
    data = dict(data)
    if "code" in data:
        data["code"] = sanitize_code(data["code"])  # "" → derived from the name
    if isinstance(data.get("kind"), str):
        data["kind"] = data["kind"].strip().lower()
    numbers = parse_room_numbers(room_numbers) if room_numbers else []
    floor = _clean_floor(floor)
    with transaction.atomic():
        # One provisioning (or bulk creation) at a time per property: codes and numbers are checked and
        # inserted without a race.
        Property.objects.select_for_update().filter(pk=property.pk).first()
        serializer = validated(
            RoomTypeSerializer, data=data, context={"property": property},
            message="Hay datos inválidos en la categoría",
        )  # fmt: skip
        kind = serializer.validated_data.get("kind", RoomType.Kind.PRIVATE)
        bed_types = (
            _dorm_bed_types(serializer.validated_data.get("beds") or [], beds_per_room)
            if (kind == RoomType.Kind.DORM)
            else []
        )
        if kind == RoomType.Kind.DORM and numbers and not bed_types:
            raise DomainError(
                "Un dormitorio vende camas: indica cuántas camas tiene cada habitación",
                code="validation_error",
                fields={"beds_per_room": ["Cada habitación de un dormitorio necesita al menos una cama"]},
            )
        ensure_new_room_numbers(property, numbers, field="room_numbers")
        room_type = serializer.save(property=property)
        rooms = _create_rooms(property, room_type, numbers, floor=floor, bed_types=bed_types)
        audit.record(
            action="inventory.room_type_provisioned",
            target=room_type,
            actor=actor,
            property=property,
            summary=f"Creó la categoría {room_type.code} con {len(rooms)} habitaciones",
            changes={"code": [None, room_type.code], "rooms": [None, [room.number for room in rooms]]},
        )
        signals.send_on_commit(
            signals.inventory_changed, property=property, room_type_ids=[room_type.pk], start=None, end=None
        )
    return room_type


# ---- Helpers shared by provisioning and bulk creation -------------------------------------------------

BED_LABEL_PREFIX = "C"  # "cama"
MAX_BEDS_PER_ROOM = 50


def ensure_new_room_numbers(property, numbers: list[str], *, field: str = "numbers") -> None:
    """Raise DomainError(code="duplicate_room_numbers", duplicates=[...]) when numbers repeat or already exist
    in the property (in order of first appearance)."""
    repeated = set(duplicates_in(numbers))
    existing = set(
        Room.objects.filter(property=property, number__in=numbers).values_list("number", flat=True)
    )
    duplicates = [number for number in dict.fromkeys(numbers) if number in repeated or number in existing]
    if duplicates:
        message = f"Estos números ya existen o se repiten: {', '.join(duplicates)}"
        raise DomainError(
            message, code="duplicate_room_numbers", duplicates=duplicates, fields={field: [message]}
        )


def _clean_floor(floor):
    if floor is None:
        return None
    if not isinstance(floor, str | int) or isinstance(floor, bool) or len(str(floor).strip()) > 20:
        raise DomainError(
            "Piso inválido", code="validation_error", fields={"floor": ["Máximo 20 caracteres"]}
        )
    return str(floor).strip()


def _dorm_bed_types(beds_config: list[dict], beds_per_room) -> list[str]:
    """Bed types of each dorm room: from the category's bed configuration (bunk → bottom + top), trimmed or
    padded with singles to `beds_per_room` when given."""
    from_config: list[str] = []
    for item in beds_config:
        for _ in range(item["count"]):
            if item["type"] == "bunk":
                from_config += [Bed.BedType.BUNK_BOTTOM, Bed.BedType.BUNK_TOP]
            elif item["type"] in ("double", "queen", "king"):
                from_config.append(Bed.BedType.DOUBLE)
            else:
                from_config.append(Bed.BedType.SINGLE)
    if beds_per_room is None:
        return from_config[:MAX_BEDS_PER_ROOM]
    if isinstance(beds_per_room, str) and beds_per_room.strip().isdigit():
        beds_per_room = int(beds_per_room)
    if (
        isinstance(beds_per_room, bool)
        or not isinstance(beds_per_room, int)
        or not (0 <= beds_per_room <= MAX_BEDS_PER_ROOM)
    ):
        raise DomainError(
            "Camas por habitación inválidas", code="validation_error",
            fields={"beds_per_room": [f"Debe estar entre 0 y {MAX_BEDS_PER_ROOM}"]},
        )  # fmt: skip
    return (from_config + [Bed.BedType.SINGLE] * beds_per_room)[:beds_per_room]


def _create_rooms(property, room_type, numbers, *, floor, bed_types, building="") -> list[Room]:
    from apps.inventory.serializers import room_custom_defaults

    custom_defaults = room_custom_defaults(property) if numbers else {}
    rooms = Room.objects.bulk_create(
        [
            Room(
                property=property,
                room_type=room_type,
                number=number,
                floor=infer_floor(number) if floor is None else floor,
                building=building,
                custom_values=dict(custom_defaults),
            )
            for number in numbers
        ]
    )
    if bed_types:
        Bed.objects.bulk_create(
            [
                Bed(room=room, label=f"{BED_LABEL_PREFIX}{index}", bed_type=bed_type)
                for room in rooms
                for index, bed_type in enumerate(bed_types, start=1)
            ]
        )
    return rooms


# ---- Rooms: bulk creation, deletion, bulk update, inheritance reset -----------------------------------


def _signal_inventory(property, room_type_ids) -> None:
    ids = sorted(set(room_type_ids), key=str)
    if ids:
        signals.send_on_commit(
            signals.inventory_changed, property=property, room_type_ids=ids, start=None, end=None
        )


def bulk_create_rooms(
    property, *, room_type, numbers, floor=None, building="", beds_per_room=None, actor=None
) -> list[Room]:
    """Create rooms from a numbers spec ("101-110,201,203" or a list) in one category.

    floor None infers it from each number; dorm rooms get `beds_per_room` beds (None → from the category's bed
    configuration). Errors: `validation_error`, `invalid_room_numbers`, `duplicate_room_numbers` (extra
    `duplicates`, nothing created; also for a concurrent creation of the same numbers, never an
    IntegrityError). Emits `inventory_changed` once.
    """
    from apps.core.models import Property

    if room_type is None or room_type.property_id != property.pk:
        raise DomainError(
            "La categoría no pertenece a esta propiedad", code="validation_error",
            fields={"room_type": ["Categoría inválida"]},
        )  # fmt: skip
    numbers = parse_room_numbers(numbers)
    floor = _clean_floor(floor)
    building = (building or "").strip()
    if len(building) > 50:
        raise DomainError(
            "Edificio inválido", code="validation_error", fields={"building": ["Máximo 50 caracteres"]}
        )
    bed_types = (
        _dorm_bed_types(room_type.beds or [], beds_per_room) if room_type.kind == RoomType.Kind.DORM else []
    )
    with transaction.atomic():
        Property.objects.select_for_update().filter(pk=property.pk).first()  # see provision_room_type
        ensure_new_room_numbers(property, numbers, field="numbers")
        rooms = _create_rooms(
            property, room_type, numbers, floor=floor, bed_types=bed_types, building=building
        )
        audit.record(
            action="inventory.rooms_bulk_created",
            target=room_type,
            actor=actor,
            property=property,
            summary=f"Creó {len(rooms)} habitaciones en {room_type.code}: {_numbers_label(numbers)}",
            changes={"rooms": [None, numbers]},
        )
        _signal_inventory(property, [room_type.pk])
    return rooms


def _numbers_label(numbers: list[str], limit: int = 12) -> str:
    shown = ", ".join(numbers[:limit])
    return shown if len(numbers) <= limit else f"{shown}… (+{len(numbers) - limit})"


def active_stay_counts(rooms) -> dict:
    """{room_id: active stays (tentative/confirmed/checked_in) assigned to it}."""
    from django.db.models import Count

    from apps.bookings.models import ACTIVE_STAY_STATUSES, Stay

    rows = (
        Stay.objects.filter(room__in=rooms, status__in=ACTIVE_STAY_STATUSES)
        .values("room_id")
        .annotate(total=Count("id"))
    )
    return {row["room_id"]: row["total"] for row in rows}


def delete_room(room, *, actor=None) -> None:
    """Delete a room that no reservation references; otherwise ConflictError `room_in_use` (409, extra
    `active_stays`) suggesting to deactivate it. Emits `inventory_changed`."""
    from apps.bookings.models import Stay

    active = active_stay_counts([room]).get(room.pk, 0)
    if active:
        raise ConflictError(
            f"La habitación {room.number} tiene {active} reserva(s) activa(s): reasígnalas antes de borrarla",
            code="room_in_use",
            active_stays=active,
        )
    if Stay.objects.filter(room=room).exists():
        raise ConflictError(
            f"La habitación {room.number} tiene historial de reservas: desactívala en lugar de borrarla",
            code="room_in_use",
            active_stays=0,
        )
    with transaction.atomic():
        room_type_id, number = room.room_type_id, room.number
        audit.record(
            action="inventory.room_deleted",
            target=room,
            actor=actor,
            property=room.property,
            summary=f"Borró la habitación {number}",
            changes={"number": [number, None]},
        )
        room.delete()
        _signal_inventory(room.property, [room_type_id])


def ensure_rooms_free(rooms, *, reason: str) -> None:
    """ConflictError `room_in_use` (extra `rooms`: numbers) when any room has active stays assigned."""
    counts = active_stay_counts(rooms)
    busy = sorted((room.number for room in rooms if counts.get(room.pk)), key=str)
    if busy:
        raise ConflictError(
            f"{reason}: {', '.join(busy)} tiene(n) reservas activas asignadas; reasígnalas primero",
            code="room_in_use",
            rooms=busy,
        )


BULK_RESET_TARGETS = "campos sobrescribibles, custom_values.<clave> o amenities"


def _bulk_plan(property, values: dict, reset: list):
    """Validate a bulk update → (room_fields, overrides, custom, clear_custom, reset_overrides, reset_custom,
    reset_amenities). Raises DomainError(validation_error) keyed by the keys the client sent."""
    from rest_framework import serializers as drf

    from apps.inventory.serializers import RoomBulkFieldsSerializer, clean_override, clean_room_custom_values

    context = {"property": property}
    errors: dict = {}
    room_input, overrides, custom, clear_custom = {}, {}, {}, []
    bulk_fields = RoomBulkFieldsSerializer.__dict__["_declared_fields"]
    for key, value in values.items():
        if key.startswith("custom_values."):
            custom_key = key.removeprefix("custom_values.")
            if value is None:
                clear_custom.append(custom_key)
                continue
            try:
                custom.update(clean_room_custom_values(property, {custom_key: value}, partial=True))
            except DomainError as exc:
                errors[key] = next(iter((exc.extra.get("fields") or {}).values()), [exc.message])
        elif key.startswith("overrides.") or (key in ROOM_OVERRIDABLE_FIELDS and key not in bulk_fields):
            field = key.removeprefix("overrides.")
            try:
                overrides[field] = clean_override(field, value, context=context)
            except drf.ValidationError as exc:
                errors[key] = exc.detail
        elif key in bulk_fields:
            room_input[key] = value
        else:
            errors[key] = ["Este campo no se puede editar en bloque"]
    serializer = RoomBulkFieldsSerializer(data=room_input, context=context, partial=True)
    if not serializer.is_valid():
        errors.update(serializer.errors)

    reset_overrides, reset_custom, reset_amenities = [], [], False
    for item in reset:
        if not isinstance(item, str):
            errors["reset"] = [f"Solo se puede restaurar: {BULK_RESET_TARGETS}"]
        elif item == "amenities":
            reset_amenities = True
        elif item.startswith("custom_values."):
            reset_custom.append(item.removeprefix("custom_values."))
        elif item.removeprefix("overrides.") in ROOM_OVERRIDABLE_FIELDS:
            reset_overrides.append(item.removeprefix("overrides."))
        else:
            errors[item] = [f"Solo se puede restaurar: {BULK_RESET_TARGETS}"]
    if errors:
        from apps.inventory.serializers import plain_errors

        raise DomainError("Hay datos inválidos", code="validation_error", fields=plain_errors(errors))
    plan = {
        "room_fields": serializer.validated_data,
        "overrides": overrides,
        "custom": custom,
        "clear_custom": clear_custom + reset_custom,
        "reset_overrides": reset_overrides,
        "reset_amenities": reset_amenities,
    }
    return plan


def bulk_update_rooms(property, *, room_ids, values=None, reset=None, actor=None) -> list[Room]:
    """Apply the same change to many rooms of the property, all or nothing.

    values (`set` in the API): plain Room fields (floor, building, name, room_type, is_active, sort_order,
    notes, housekeeping_status), overridable fields (`view` or `overrides.view`; `overrides.name` for the
    category name) and `custom_values.<key>` (None clears it). reset: overridable fields,
    `custom_values.<key>` or `amenities` go back to the category's values.
    Rules: effective occupancy must stay consistent; rooms with active stays cannot change category or be
    deactivated (`room_in_use`, extra `rooms`); status changes go through `set_housekeeping_status`.
    Emits one `inventory_changed` when categories or active flags change.
    """
    from apps.inventory.serializers import plain_errors, room_occupancy_errors

    values = values or {}
    reset = reset or []
    if not isinstance(values, dict) or not isinstance(reset, list):
        raise DomainError("Formato inválido", code="validation_error", fields={"set": ["Debe ser un objeto"]})
    ids = [str(pk) for pk in (room_ids or [])]
    if not ids:
        raise DomainError(
            "Selecciona al menos una habitación", code="validation_error", fields={"ids": ["Vacío"]}
        )
    rooms = list(Room.objects.filter(property=property, pk__in=_valid_uuids(ids)).select_related("room_type"))
    missing = sorted(set(ids) - {str(room.pk) for room in rooms})
    if missing:
        raise DomainError(
            "Algunas habitaciones no existen en esta propiedad", code="validation_error",
            fields={"ids": [f"No encontradas: {', '.join(missing)}"]},
        )  # fmt: skip
    if not values and not reset:
        raise DomainError("No hay cambios", code="validation_error", fields={"set": ["Indica qué cambiar"]})
    plan = _bulk_plan(property, values, reset)
    room_fields = dict(plan["room_fields"])
    status = room_fields.pop("housekeeping_status", None)
    new_type = room_fields.get("room_type")

    moving = [room for room in rooms if new_type is not None and room.room_type_id != new_type.pk]
    deactivating = [room for room in rooms if room_fields.get("is_active") is False and room.is_active]
    if moving:
        ensure_rooms_free(moving, reason="No se puede cambiar la categoría de")
    if deactivating:
        ensure_rooms_free(deactivating, reason="No se puede desactivar")

    occupancy: dict[str, list[str]] = {}
    for room in rooms:
        overrides = {**(room.overrides or {}), **plan["overrides"]}
        for field in plan["reset_overrides"]:
            overrides.pop(field, None)
        for field in room_occupancy_errors(new_type or room.room_type, overrides):
            occupancy.setdefault(field, []).append(room.number)
        room._bulk_overrides = overrides
    if occupancy:
        raise DomainError(
            "La ocupación resultante no es válida", code="validation_error",
            fields=plain_errors({
                field: [f"Ocupación inválida en {', '.join(numbers)}"] for field, numbers in occupancy.items()
            }),
        )  # fmt: skip

    changed_types: set = set()
    with transaction.atomic():
        for room in rooms:
            before = {"room_type": room.room_type_id, "is_active": room.is_active}
            for field, value in room_fields.items():
                setattr(room, field, value)
            room.overrides = room._bulk_overrides
            custom = {**(room.custom_values or {}), **plan["custom"]}
            for key in plan["clear_custom"]:
                custom.pop(key, None)
            room.custom_values = custom
            # never the stale housekeeping status read above (set_housekeeping_status changes it below)
            room.save(update_fields=[*room_fields, "overrides", "custom_values", "updated_at"])
            if plan["reset_amenities"]:
                room.extra_amenities.clear()
                room.removed_amenities.clear()
            if before["room_type"] != room.room_type_id or before["is_active"] != room.is_active:
                changed_types |= {before["room_type"], room.room_type_id}
            if status is not None:
                set_housekeeping_status(room, status, actor=actor, source="user")
        audit.record(
            action="inventory.rooms_bulk_updated",
            target=rooms[0].room_type if len({r.room_type_id for r in rooms}) == 1 else None,
            actor=actor,
            property=property,
            summary=f"Editó en bloque {len(rooms)} habitaciones: {_numbers_label([r.number for r in rooms])}",
            changes={"rooms": [r.number for r in rooms], "set": values, "reset": reset},
        )
        _signal_inventory(property, changed_types)
    return rooms


def _valid_uuids(ids: list[str]) -> list[str]:
    from uuid import UUID

    valid = []
    for value in ids:
        try:
            valid.append(str(UUID(value)))
        except ValueError:
            continue
    return valid


def reset_override(room, field: str, *, actor=None) -> Room:
    """Make a room inherit again: an overridable field (or `overrides.<field>`), `amenities` (drops extra and
    removed amenities) or `custom_values.<key>`. Unknown → DomainError(validation_error)."""
    target = field.removeprefix("overrides.") if isinstance(field, str) else ""
    if target in ROOM_OVERRIDABLE_FIELDS:
        overrides = dict(room.overrides or {})
        changed = overrides.pop(target, None) is not None or target in (room.overrides or {})
        room.overrides = overrides
        update_fields = ["overrides", "updated_at"]
    elif target == "amenities":
        changed = room.extra_amenities.exists() or room.removed_amenities.exists()
        update_fields = []
    elif target.startswith("custom_values."):
        custom = dict(room.custom_values or {})
        changed = target.removeprefix("custom_values.") in custom
        custom.pop(target.removeprefix("custom_values."), None)
        room.custom_values = custom
        update_fields = ["custom_values", "updated_at"]
    else:
        raise DomainError(
            "Ese campo no se puede restaurar", code="validation_error",
            fields={"field": [f"Solo se puede restaurar: {BULK_RESET_TARGETS}"]},
        )  # fmt: skip
    if not changed:
        return room
    with transaction.atomic():
        if target == "amenities":
            room.extra_amenities.clear()
            room.removed_amenities.clear()
        else:
            room.save(update_fields=update_fields)
        audit.record(
            action="inventory.room_override_reset",
            target=room,
            actor=actor,
            property=room.property,
            summary=f"Habitación {room.number}: {target} vuelve a heredar de la categoría",
            changes={"field": [target, None]},
        )
    return room


# ---- Categories ---------------------------------------------------------------------------------------

ROOM_TYPE_AUDIT_FIELDS = [
    "code", "name", "description", "kind", "base_occupancy", "max_adults", "max_children", "max_occupancy",
    "beds", "size_m2", "view", "smoking_allowed", "accessible", "color", "housekeeping_minutes", "sort_order",
    "is_active", "custom_values",
]  # fmt: skip


def _snapshot(obj, fields) -> dict:
    from apps.inventory.serializers import jsonable

    return {field: jsonable(getattr(obj, field)) for field in fields}


def _active_stays_of_type(room_type) -> int:
    from apps.bookings.models import ACTIVE_STAY_STATUSES, Stay

    return Stay.objects.filter(room_type=room_type, status__in=ACTIVE_STAY_STATUSES).count()


def save_room_type(property, *, data: dict, room_type=None, actor=None) -> RoomType:
    """Create or update a category from `RoomTypeSerializer.validated_data`; audits the diff. Deactivating a
    category with active reservations → ConflictError `room_type_in_use`. Emits `inventory_changed` when it is
    created or its active flag changes."""
    data = dict(data)
    amenities = data.pop("amenities", None)
    with transaction.atomic():
        if room_type is None:
            room_type = RoomType.objects.create(property=property, **data)
            before, created = {}, True
        else:
            if data.get("is_active") is False and room_type.is_active:
                active = _active_stays_of_type(room_type)
                if active:
                    raise ConflictError(
                        f"La categoría tiene {active} reserva(s) activa(s): no se puede desactivar",
                        code="room_type_in_use",
                        active_stays=active,
                    )
            before, created = _snapshot(room_type, ROOM_TYPE_AUDIT_FIELDS), False
            before_amenities = sorted(a.code for a in room_type.amenities.all())
            for field, value in data.items():
                setattr(room_type, field, value)
            room_type.save()
        if amenities is not None:
            room_type.amenities.set(amenities)
        after = _snapshot(room_type, ROOM_TYPE_AUDIT_FIELDS)
        changes = audit.diff(before, after)
        if amenities is not None:
            new_codes = sorted(a.code for a in amenities)
            if created or new_codes != before_amenities:
                changes["amenities"] = [None if created else before_amenities, new_codes]
        if created or changes:
            audit.record(
                action="inventory.room_type_created" if created else "inventory.room_type_updated",
                target=room_type,
                actor=actor,
                property=property,
                summary=f"{'Creó' if created else 'Editó'} la categoría {room_type.code}",
                changes=changes,
            )
        if created or "is_active" in changes:
            _signal_inventory(property, [room_type.pk])
    return room_type


def delete_room_type(room_type, *, actor=None) -> None:
    """Delete a category without rooms nor reservations (its prices go with it); otherwise ConflictError
    `room_type_in_use` suggesting to deactivate it."""
    from apps.bookings.models import Stay

    if room_type.rooms.exists():
        raise ConflictError(
            "La categoría tiene habitaciones: muévelas a otra categoría o desactívala",
            code="room_type_in_use",
            rooms=room_type.rooms.count(),
        )
    if Stay.objects.filter(room_type=room_type).exists():
        raise ConflictError(
            "La categoría tiene reservas: desactívala en lugar de borrarla", code="room_type_in_use", rooms=0
        )
    with transaction.atomic():
        audit.record(
            action="inventory.room_type_deleted",
            target=room_type,
            actor=actor,
            property=room_type.property,
            summary=f"Borró la categoría {room_type.code}",
            changes={"code": [room_type.code, None]},
        )
        room_type.delete()


def duplicate_room_type(room_type, *, code=None, name=None, actor=None) -> RoomType:
    """Copy a category's parameters, amenities and custom values (not rooms nor photos). Default code: the
    same with a numeric suffix; default name: "<name> (copia)" / "(copy)"."""
    from apps.inventory.serializers import RoomTypeSerializer, validated

    prop = room_type.property
    data = {
        field: getattr(room_type, field)
        for field in ROOM_TYPE_AUDIT_FIELDS
        if field not in ("code", "name", "sort_order")
    }
    data["amenities"] = [amenity.code for amenity in room_type.amenities.all()]
    data["code"] = code or ""
    data["name"] = name or {
        language: f"{text} ({'copia' if language == 'es' else 'copy'})"
        for language, text in (room_type.name or {}).items()
        if text
    }
    if not code:
        from apps.inventory.serializers import unique_room_type_code

        data["code"] = unique_room_type_code(prop, room_type.code)
    serializer = validated(
        RoomTypeSerializer, data=data, context={"property": prop}, message="Datos inválidos"
    )
    copy = save_room_type(prop, data=serializer.validated_data, actor=actor)
    return copy


# ---- Rooms --------------------------------------------------------------------------------------------

ROOM_AUDIT_FIELDS = [
    "number", "name", "floor", "building", "room_type_id", "overrides", "custom_values", "is_active",
    "sort_order", "notes",
]  # fmt: skip


def save_room(property, *, data: dict, room=None, actor=None) -> Room:
    """Create or update a room from `RoomSerializer.validated_data`. Moving a room with active stays to
    another category or deactivating it → ConflictError `room_in_use`. Emits `inventory_changed` on
    creation, category change or active flag change (both categories)."""
    data = dict(data)
    m2m = {
        key: data.pop(key)
        for key in ("extra_amenities", "removed_amenities", "connecting_rooms")
        if key in data
    }
    with transaction.atomic():
        if room is None:
            room = Room.objects.create(property=property, **data)
            before, created = {}, True
            type_ids = {room.room_type_id}
        else:
            if data.get("room_type") is not None and data["room_type"].pk != room.room_type_id:
                ensure_rooms_free([room], reason="No se puede cambiar la categoría de")
            if data.get("is_active") is False and room.is_active:
                ensure_rooms_free([room], reason="No se puede desactivar")
            before, created = _snapshot(room, ROOM_AUDIT_FIELDS), False
            old_type_id, old_active = room.room_type_id, room.is_active
            for field, value in data.items():
                setattr(room, field, value)
            # only the edited columns: housekeeping may have changed the status since the room was read
            room.save(update_fields=[*data, "updated_at"])
            type_ids = set()
            if old_type_id != room.room_type_id:
                type_ids |= {old_type_id, room.room_type_id}
            if old_active != room.is_active:
                type_ids.add(room.room_type_id)
        for key, value in m2m.items():
            getattr(room, key).set(value)
        after = _snapshot(room, ROOM_AUDIT_FIELDS)
        changes = audit.diff(before, after)
        for key in ("extra_amenities", "removed_amenities"):
            if key in m2m:
                changes[key] = [None, sorted(a.code for a in m2m[key])]
        if created or changes:
            audit.record(
                action="inventory.room_created" if created else "inventory.room_updated",
                target=room,
                actor=actor,
                property=property,
                summary=f"{'Creó' if created else 'Editó'} la habitación {room.number}",
                changes=changes,
            )
        _signal_inventory(property, type_ids)
    return room


# ---- Beds ---------------------------------------------------------------------------------------------


class NotADormError(DomainError):
    code = "not_a_dorm"


def ensure_dorm(room) -> None:
    if room.room_type.kind != RoomType.Kind.DORM:
        raise NotADormError("Las camas vendibles solo existen en habitaciones de dormitorio")


def _bed_stays(bed, *, active_only: bool) -> int:
    from apps.bookings.models import ACTIVE_STAY_STATUSES, Stay

    stays = Stay.objects.filter(bed=bed)
    if active_only:
        stays = stays.filter(status__in=ACTIVE_STAY_STATUSES)
    return stays.count()


def save_bed(room, *, data: dict, bed=None, actor=None) -> Bed:
    """Create or update a dorm bed; deactivating a bed with active stays → ConflictError `bed_in_use`.
    Emits `inventory_changed` on creation or active flag change."""
    ensure_dorm(room)
    with transaction.atomic():
        if bed is None:
            bed = Bed.objects.create(room=room, **data)
            changes, created = {"label": [None, bed.label]}, True
        else:
            if data.get("is_active") is False and bed.is_active and _bed_stays(bed, active_only=True):
                raise ConflictError("La cama tiene reservas activas: reasígnalas primero", code="bed_in_use")
            before = {field: getattr(bed, field) for field in ("label", "bed_type", "is_active")}
            for field, value in data.items():
                setattr(bed, field, value)
            bed.save()
            changes = audit.diff(before, {field: getattr(bed, field) for field in before})
            created = False
        if changes:
            audit.record(
                action="inventory.bed_created" if created else "inventory.bed_updated",
                target=bed,
                actor=actor,
                property=room.property,
                summary=f"{'Creó' if created else 'Editó'} la cama {room.number}-{bed.label}",
                changes=changes,
            )
        if created or "is_active" in changes:
            _signal_inventory(room.property, [room.room_type_id])
    return bed


def create_beds(
    room, *, count: int, prefix: str = BED_LABEL_PREFIX, bed_type: str = "single", actor=None
) -> list[Bed]:
    """Add `count` beds labeled `<prefix><n>`, continuing after the highest existing number with that prefix.
    `bed_type="bunk"` alternates bunk bottom/top. Emits `inventory_changed`."""
    import re

    ensure_dorm(room)
    if not 1 <= count <= MAX_BEDS_PER_ROOM:
        raise DomainError("Cantidad inválida", code="validation_error", fields={"count": ["Entre 1 y 50"]})
    prefix = (prefix or "").strip()
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    labels = set(room.beds.values_list("label", flat=True))
    start = max([int(m.group(1)) for label in labels if (m := pattern.match(label))], default=0) + 1
    types = (
        [Bed.BedType.BUNK_BOTTOM if index % 2 == 0 else Bed.BedType.BUNK_TOP for index in range(count)]
        if bed_type == "bunk"
        else [bed_type] * count
    )
    new_labels = []
    number = start
    while len(new_labels) < count:
        label = f"{prefix}{number}"
        if label not in labels:
            new_labels.append(label)
        number += 1
    if any(len(label) > 20 for label in new_labels):
        raise DomainError(
            "Etiqueta demasiado larga", code="validation_error", fields={"prefix": ["Muy largo"]}
        )
    with transaction.atomic():
        beds = Bed.objects.bulk_create(
            [
                Bed(room=room, label=label, bed_type=bed_kind)
                for label, bed_kind in zip(new_labels, types, strict=True)
            ]
        )
        audit.record(
            action="inventory.beds_created",
            target=room,
            actor=actor,
            property=room.property,
            summary=f"Agregó {count} camas a {room.number}: {', '.join(new_labels)}",
            changes={"beds": [None, new_labels]},
        )
        _signal_inventory(room.property, [room.room_type_id])
    return beds


def delete_bed(bed, *, actor=None) -> None:
    """Delete a bed no reservation references (ConflictError `bed_in_use` otherwise). Emits
    `inventory_changed`."""
    if _bed_stays(bed, active_only=False):
        raise ConflictError("La cama tiene reservas: desactívala en lugar de borrarla", code="bed_in_use")
    room = bed.room
    with transaction.atomic():
        audit.record(
            action="inventory.bed_deleted",
            target=bed,
            actor=actor,
            property=room.property,
            summary=f"Borró la cama {room.number}-{bed.label}",
            changes={"label": [bed.label, None]},
        )
        bed.delete()
        _signal_inventory(room.property, [room.room_type_id])


# ---- Custom fields ------------------------------------------------------------------------------------


def _inventory_records_with_key(definition):
    """(model, record) of the room types and rooms in the definition's scope that store its key. Rooms may
    override category fields, so a `room_type` definition also reaches rooms. Guest and reservation values
    belong to their apps (nothing here)."""
    from apps.inventory.models import CustomFieldDefinition

    targets = {
        CustomFieldDefinition.AppliesTo.ROOM_TYPE: [RoomType, Room],
        CustomFieldDefinition.AppliesTo.ROOM: [Room],
    }
    scope = {"property": definition.property} if definition.property_id else {
        "property__organization": definition.organization
    }  # fmt: skip
    for model in targets.get(definition.applies_to, []):
        for record in model.objects.filter(**scope, custom_values__has_key=definition.key):
            yield model, record


def create_custom_field(serializer, *, organization, property=None, actor=None):
    """Save a validated new `CustomFieldDefinitionSerializer` (`property=None` = organization-wide) together
    with its audit event."""
    with transaction.atomic():
        definition = serializer.save(organization=organization, property=property)
        audit.record(
            action="inventory.custom_field_created",
            target=definition,
            actor=actor,
            organization=organization,
            property=definition.property,
            summary=f"Creó el campo personalizado {definition.applies_to}.{definition.key}",
        )
    return definition


def delete_custom_field(definition, *, actor=None) -> None:
    """Delete a definition and remove its key from the inventory values in its scope (room types and rooms;
    rooms may override category fields). Guest/reservation values are owned by their apps (see notes)."""
    key = definition.key
    with transaction.atomic():
        for model, record in _inventory_records_with_key(definition):
            values = dict(record.custom_values)
            values.pop(key, None)
            model.objects.filter(pk=record.pk).update(custom_values=values)
        audit.record(
            action="inventory.custom_field_deleted",
            target=definition,
            actor=actor,
            organization=definition.organization,
            property=definition.property,
            summary=f"Borró el campo personalizado {definition.applies_to}.{key}",
            changes={"key": [key, None]},
        )
        definition.delete()


def update_custom_field(serializer, *, actor=None):
    """Save a validated `CustomFieldDefinitionSerializer` change and audit it. When options of a select or
    multiselect field are removed, room types and rooms in its scope drop the values that used them (as
    deleting the field does), so a stale value never blocks saving them later."""
    from apps.inventory.custom_fields import option_values

    definition = serializer.instance
    options_before = option_values(definition)
    with transaction.atomic():
        definition = serializer.save()
        removed = options_before - option_values(definition)
        cleaned = 0
        if removed and definition.field_type in ("select", "multiselect"):
            for model, record in _inventory_records_with_key(definition):
                values = dict(record.custom_values)
                value = values[definition.key]
                if isinstance(value, list):
                    kept = [item for item in value if item not in removed]
                    changed = len(kept) != len(value)
                    if kept:
                        values[definition.key] = kept
                    else:
                        values.pop(definition.key)
                else:
                    changed = value in removed
                    if changed:
                        values.pop(definition.key)
                if changed:
                    model.objects.filter(pk=record.pk).update(custom_values=values)
                    cleaned += 1
        audit.record(
            action="inventory.custom_field_updated",
            target=definition,
            actor=actor,
            organization=definition.organization,
            property=definition.property,
            summary=f"Editó el campo personalizado {definition.applies_to}.{definition.key}"
            + (f" (se limpiaron {cleaned} valores de opciones eliminadas)" if cleaned else ""),
            changes={"removed_options": [sorted(map(str, removed)), None]} if removed else None,
        )
    return definition


# ---- Photos and logo ----------------------------------------------------------------------------------


def _image_filename(image) -> str:
    """A fresh `<uuid>.<ext>` for a validated upload (the extension follows the real image format)."""
    import uuid

    from apps.inventory.serializers import PHOTO_FORMATS

    pil_image = getattr(image, "image", None)
    extension = PHOTO_FORMATS.get(getattr(pil_image, "format", ""), "jpg")
    return f"{uuid.uuid4().hex}.{extension}"


def add_photo(property, *, image, caption=None, room_type=None, actor=None):
    """Store an already validated image as the last photo of a category (or of the property), under
    `Photo.image.upload_to` (`photos/<year>/<month>/<uuid>.<ext>`)."""
    from django.db.models import Max

    from apps.inventory.models import Photo

    with transaction.atomic():
        top = Photo.objects.filter(property=property, room_type=room_type, room__isnull=True).aggregate(
            top=Max("sort_order")
        )["top"]
        photo = Photo(
            property=property, room_type=room_type, caption=caption or {}, sort_order=(top or 0) + 1
        )
        photo.image.save(_image_filename(image), image, save=False)  # upload_to adds the dated folder
        photo.save()
        audit.record(
            action="inventory.photo_added",
            target=photo,
            actor=actor,
            property=property,
            summary=f"Agregó una foto a {room_type.code if room_type else 'la propiedad'}",
        )
    return photo


def update_photo_caption(photo, *, caption: dict, actor=None):
    """Change a photo's caption `{es, en}` (audited when it changes)."""
    before = dict(photo.caption or {})
    if before == caption:
        return photo
    gallery = photo.room_type.code if photo.room_type else "la propiedad"
    with transaction.atomic():
        photo.caption = caption
        photo.save(update_fields=["caption", "updated_at"])
        audit.record(
            action="inventory.photo_updated",
            target=photo,
            actor=actor,
            property=photo.property,
            summary=f"Editó la descripción de una foto de {gallery}",
            changes={"caption": [before, caption]},
        )
    return photo


def delete_photo(photo, *, actor=None) -> None:
    with transaction.atomic():
        audit.record(
            action="inventory.photo_deleted",
            target=photo,
            actor=actor,
            property=photo.property,
            summary=f"Borró una foto de {photo.room_type.code if photo.room_type else 'la propiedad'}",
        )
        photo.delete()  # the file goes after commit (receivers.delete_photo_file)


def reorder_photos(photos, ids, *, gallery=None, actor=None) -> list:
    """Photos in the order of `ids`, which must be exactly the given photos. `gallery` (the room type, or the
    property for its own gallery) is the audited target when the order changes."""
    by_id = {str(photo.pk): photo for photo in photos}
    ids = [str(pk) for pk in ids]
    if sorted(ids) != sorted(by_id):
        raise DomainError(
            "Envía todas las fotos, cada una una vez", code="validation_error",
            fields={"ids": ["Deben ser exactamente las fotos de esta galería"]},
        )  # fmt: skip
    ordered = [by_id[pk] for pk in ids]
    before = [
        str(photo.pk) for photo in sorted(photos, key=lambda photo: (photo.sort_order, photo.created_at))
    ]
    with transaction.atomic():
        for index, photo in enumerate(ordered, start=1):
            if photo.sort_order != index:
                photo.sort_order = index
                photo.save(update_fields=["sort_order", "updated_at"])
        if gallery is not None and before != ids:
            audit.record(
                action="inventory.photos_reordered",
                target=gallery,
                actor=actor,
                summary=f"Reordenó las fotos de {getattr(gallery, 'code', None) or 'la propiedad'}",
                changes={"order": [before, ids]},
            )
    return ordered


# ---- Amenities (organization catalog) -----------------------------------------------------------------


def _replace_profile_amenity(organization, code: str, new_code: str | None) -> None:
    """Property profiles keep their amenities as codes (`Property.settings["amenities"]`): follow a renamed
    code (`new_code`) or drop a deleted one (`None`), so no profile keeps a code that no longer exists."""
    from apps.core.models import Property

    for prop in Property.objects.select_for_update().filter(organization=organization):
        codes = list((prop.settings or {}).get("amenities") or [])
        if code not in codes:
            continue
        if new_code is None:
            codes = [item for item in codes if item != code]
        else:
            codes = list(dict.fromkeys(new_code if item == code else item for item in codes))
        prop.settings = {**prop.settings, "amenities": codes}
        prop.save(update_fields=["settings", "updated_at"])


def save_amenity(serializer, *, organization, actor=None):
    """Create or update one of the organization's own amenities from a validated `AmenitySerializer` (the
    global catalog is read-only: the view refuses it). A new code is followed by the property profiles that
    listed the old one. Audited with `property=None` (organization level)."""
    amenity = serializer.instance
    fields = ("code", "name", "icon", "category")
    before = {field: getattr(amenity, field) for field in fields} if amenity is not None else {}
    with transaction.atomic():
        amenity = serializer.save(organization=organization) if amenity is None else serializer.save()
        after = {field: getattr(amenity, field) for field in fields}
        changes = audit.diff(before, after)
        if before and before["code"] != amenity.code:
            _replace_profile_amenity(organization, before["code"], amenity.code)
        if not before or changes:
            audit.record(
                action="inventory.amenity_created" if not before else "inventory.amenity_updated",
                target=amenity,
                actor=actor,
                organization=organization,
                summary=f"{'Creó' if not before else 'Editó'} la amenidad {amenity.code}",
                changes=changes,
            )
    return amenity


def delete_amenity(amenity, *, actor=None) -> None:
    """Delete one of the organization's own amenities: categories, rooms and property profiles stop listing
    it."""
    with transaction.atomic():
        _replace_profile_amenity(amenity.organization, amenity.code, None)
        audit.record(
            action="inventory.amenity_deleted",
            target=amenity,
            actor=actor,
            organization=amenity.organization,
            summary=f"Borró la amenidad {amenity.code}",
            changes={"code": [amenity.code, None]},
        )
        amenity.delete()


def set_property_logo(property, *, image, actor=None):
    from django.core.files.storage import default_storage

    name = default_storage.save(f"branding/{property.pk}/{_image_filename(image)}", image)
    old = (property.branding or {}).get("logo", "")
    property.branding = {**(property.branding or {}), "logo": default_storage.url(name)}
    property.save(update_fields=["branding", "updated_at"])
    _delete_media_url(old)
    audit.record(action="inventory.logo_updated", target=property, actor=actor, summary="Actualizó el logo")
    return property


def remove_property_logo(property, *, actor=None):
    old = (property.branding or {}).get("logo", "")
    if old:
        property.branding = {key: value for key, value in (property.branding or {}).items() if key != "logo"}
        property.save(update_fields=["branding", "updated_at"])
        _delete_media_url(old)
        audit.record(action="inventory.logo_removed", target=property, actor=actor, summary="Quitó el logo")
    return property


def _delete_media_url(url: str) -> None:
    from django.conf import settings
    from django.core.files.storage import default_storage

    if url and url.startswith(settings.MEDIA_URL):
        name = url.removeprefix(settings.MEDIA_URL)
        if default_storage.exists(name):
            default_storage.delete(name)


# ---- Property profile ---------------------------------------------------------------------------------

PROFILE_AUDIT_FIELDS = [
    "name", "description", "address", "city", "department", "latitude", "longitude", "phone", "email",
    "website", "rnt_number", "nit", "legal_name", "star_rating", "check_in_time", "check_out_time",
    "default_language", "house_rules", "branding", "settings",
]  # fmt: skip


def update_property_profile(property, serializer, *, actor=None):
    """Save a validated `PropertyProfileSerializer` and audit the diff (`inventory.property_updated`)."""
    before = _snapshot(property, PROFILE_AUDIT_FIELDS)
    with transaction.atomic():
        property = serializer.save()
        changes = audit.diff(before, _snapshot(property, PROFILE_AUDIT_FIELDS))
        if changes:
            audit.record(
                action="inventory.property_updated",
                target=property,
                actor=actor,
                summary="Actualizó el perfil de la propiedad",
                changes=changes,
            )
    return property


# ---- Summary (checklist, onboarding) ------------------------------------------------------------------


def inventory_summary(property) -> dict:
    """Units per category, totals, housekeeping counts of active rooms, warnings and missing profile fields.

    warnings: `room_type_without_rooms` (room_type_id) and `dorm_room_without_beds` (room_type_id, room_id).
    """
    from django.db.models import Count

    from apps.inventory.serializers import PROFILE_RECOMMENDED

    room_types = list(
        RoomType.objects.filter(property=property)
        .annotate(
            rooms_total=Count("rooms", distinct=True),
            active_rooms=Count("rooms", filter=Q(rooms__is_active=True), distinct=True),
            active_beds=Count(
                "rooms__beds", filter=Q(rooms__is_active=True, rooms__beds__is_active=True), distinct=True
            ),
        )
        .order_by("sort_order", "code")
    )
    warnings = []
    rows = []
    for room_type in room_types:
        is_dorm = room_type.kind == RoomType.Kind.DORM
        units = room_type.active_beds if is_dorm else room_type.active_rooms
        rows.append(
            {
                "id": str(room_type.pk),
                "code": room_type.code,
                "name": room_type.name,
                "kind": room_type.kind,
                "color": room_type.color,
                "is_active": room_type.is_active,
                "max_occupancy": room_type.max_occupancy,
                "rooms": room_type.rooms_total,
                "active_rooms": room_type.active_rooms,
                "beds": room_type.active_beds,
                "units": units,
            }
        )
        if room_type.rooms_total == 0:
            warnings.append({
                "code": "room_type_without_rooms", "room_type_id": str(room_type.pk),
                "message": f"La categoría {room_type.code} no tiene habitaciones",
            })  # fmt: skip
    dorm_rooms_without_beds = (
        Room.objects.filter(property=property, is_active=True, room_type__kind=RoomType.Kind.DORM)
        .annotate(active_beds=Count("beds", filter=Q(beds__is_active=True)))
        .filter(active_beds=0)
        .select_related("room_type")
        .order_by("number")
    )
    for room in dorm_rooms_without_beds:
        warnings.append({
            "code": "dorm_room_without_beds", "room_type_id": str(room.room_type_id), "room_id": str(room.pk),
            "message": f"El dormitorio {room.number} no tiene camas vendibles",
        })  # fmt: skip
    statuses = dict(
        Room.objects.filter(property=property, is_active=True)
        .values_list("housekeeping_status")
        .annotate(total=Count("id"))
    )
    active_rooms = [row for row in rows if row["is_active"]]
    return {
        "room_types": rows,
        "totals": {
            "room_types": len(rows),
            "active_room_types": len(active_rooms),
            "rooms": sum(row["rooms"] for row in rows),
            "active_rooms": sum(row["active_rooms"] for row in rows),
            "beds": sum(row["beds"] for row in rows if row["kind"] == RoomType.Kind.DORM),
            "units": sum(row["units"] for row in active_rooms),
        },
        "housekeeping": {status: statuses.get(status, 0) for status in Room.HousekeepingStatus.values},
        "blocked_today": RoomBlock.objects.filter(
            room__property=property,
            released_at__isnull=True,
            start_date__lte=property.business_date,
            end_date__gt=property.business_date,
        ).count(),  # fmt: skip
        "warnings": warnings,
        "profile_missing": [
            field
            for field in PROFILE_RECOMMENDED
            if not (
                getattr(property, field) if field != "description" else (property.description or {}).get("es")
            )
        ],  # fmt: skip
    }
