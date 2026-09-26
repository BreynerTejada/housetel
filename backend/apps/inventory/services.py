"""Inventory contracts (spec §4.2 + plan §C). Phase A implements inheritance, blocks, housekeeping
status and the central custom-field validation; B1 completes `provision_room_type` and the API.

Ranges are half-open: a block covers `[start, end)`.
"""

from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.core import audit, signals
from apps.core.errors import DomainError
from apps.inventory.models import ROOM_OVERRIDABLE_FIELDS, Room, RoomBlock, RoomType


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

    type_amenities = set(room_type.amenities.values_list("code", flat=True))
    added = set(room.extra_amenities.values_list("code", flat=True))
    removed = set(room.removed_amenities.values_list("code", flat=True))
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


def block_room(room, *, start, end, kind, reason, actor=None, bed=None) -> RoomBlock:
    """Take a room (or one dorm bed) out of inventory for `[start, end)`; emits `inventory_changed`."""
    if not start or not end or end <= start:
        raise DomainError("La fecha final debe ser posterior a la inicial", code="invalid_dates")
    if bed is not None and bed.room_id != room.pk:
        raise DomainError("La cama no pertenece a esta habitación", code="invalid_bed")
    if kind not in RoomBlock.Kind.values:
        raise DomainError(f"Tipo de bloqueo inválido: {kind}", code="invalid_kind")
    with transaction.atomic():
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
    """Create a category with its rooms (and beds for dorms) in one go. Used by AI onboarding.

    data: RoomType keys (code, name{es,en}, kind, base_occupancy, max_adults, max_children,
    max_occupancy, beds, size_m2, view, amenities[codes], color, housekeeping_minutes). Implemented by B1.
    """
    raise NotImplementedError("inventory.provision_room_type: B1 implementa esta función")


def validate_custom_values(defs, values) -> dict:
    """Validate `values` against CustomFieldDefinitions (spec §4 central validation) and return them cleaned.

    Applies `default_value` for missing keys; rejects unknown keys, missing required ones and wrong types
    (text: str · number: int/float · boolean: bool · select: one option value · multiselect: list of option
    values · date: "YYYY-MM-DD"). Raises DomainError(code="invalid_custom_values", fields={key: [msg]}).
    """
    values = dict(values or {})
    definitions = {definition.key: definition for definition in defs}
    errors: dict[str, list[str]] = {
        key: ["Campo personalizado desconocido"] for key in values if key not in definitions
    }
    cleaned = {}
    for key, definition in definitions.items():
        value = values.get(key)
        if value is None or value == "" or value == []:
            if definition.default_value is not None:
                cleaned[key] = definition.default_value
            elif definition.required:
                errors[key] = ["Este campo es obligatorio"]
            continue
        try:
            cleaned[key] = _clean_custom_value(definition, value)
        except ValueError as exc:
            errors[key] = [str(exc)]
    if errors:
        raise DomainError("Hay campos personalizados inválidos", code="invalid_custom_values", fields=errors)
    return cleaned


def _clean_custom_value(definition, value):
    field_type = definition.field_type
    options = {option["value"] if isinstance(option, dict) else option for option in definition.options or []}
    if field_type == "text":
        if not isinstance(value, str):
            raise ValueError("Debe ser un texto")
        return value
    if field_type == "number":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("Debe ser un número")
        return value
    if field_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError("Debe ser sí o no")
        return value
    if field_type == "select":
        if value not in options:
            raise ValueError(f"Opción inválida: {value}")
        return value
    if field_type == "multiselect":
        if not isinstance(value, list) or any(item not in options for item in value):
            raise ValueError("Opciones inválidas")
        return value
    if field_type == "date":
        if isinstance(value, date):
            return value.isoformat()
        try:
            return date.fromisoformat(value).isoformat()
        except (TypeError, ValueError):
            raise ValueError("Debe ser una fecha AAAA-MM-DD") from None
    raise ValueError(f"Tipo de campo desconocido: {field_type}")
