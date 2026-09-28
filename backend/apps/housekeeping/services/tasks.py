"""Housekeeping tasks: automatic creation (with de-duplication), the task life cycle and room status.

Life cycle: pending → in_progress (start) → done (finish) → inspected (inspect). Finishing a departure clean,
stayover or deep clean leaves the room `clean` through `inventory.set_housekeeping_status`; with
`require_inspection` it also creates an inspection task, and passing it leaves the room `inspected`.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.bookings.models import Stay
from apps.core import audit
from apps.core.errors import ConflictError, DomainError
from apps.core.permissions import has_perm
from apps.housekeeping.models import HousekeepingTask, Priority
from apps.housekeeping.services.common import (
    CLEANING_KINDS,
    OPEN_STATUSES,
    TURNOVER_KINDS,
    Kind,
    Status,
    arrives_today,
    estimated_minutes,
    in_house_stay,
    rank,
    user_or_none,
)
from apps.housekeeping.services.config import get_settings
from apps.inventory.models import Room
from apps.inventory.services import set_housekeeping_status

SOURCE_AUDIT = {
    HousekeepingTask.Source.CHECKOUT: "automation",
    HousekeepingTask.Source.STATUS_CHANGE: "automation",
    HousekeepingTask.Source.DAILY: "automation",
    HousekeepingTask.Source.INSPECTION: "automation",
    HousekeepingTask.Source.SEED: "system",
}


def open_cleaning_task(room):
    """The open departure / stayover / deep clean of a room (any business date), or None."""
    return (
        HousekeepingTask.objects.filter(room=room, status__in=OPEN_STATUSES, kind__in=CLEANING_KINDS)
        .order_by("-status", "business_date", "created_at")  # in_progress first
        .first()
    )


def ensure_turnover_task(room, *, kind, source, reservation=None, bed=None, actor=None):
    """Make sure the room has an open clean for today; returns `(task, created)`.

    - No open clean → a new `kind` task (departure clean or stayover) for the business date, `high` priority
      when a guest arrives today in the room (else `normal`), with the room's estimated minutes.
    - An open clean exists → nothing is duplicated: a stayover becomes the departure clean when the guest
      left, the priority is raised to `high` if someone arrives today, and a dorm task for one bed widens to
      the whole room when another bed needs it.
    The database allows one open turnover per room, so a concurrent creation falls back to updating it.
    """
    prop = room.property
    today = prop.business_date
    priority = Priority.HIGH if arrives_today(room, today) else Priority.NORMAL
    for _attempt in range(3):
        task = open_cleaning_task(room)
        if task is not None:
            _merge_into(task, room, kind=kind, priority=priority, reservation=reservation, bed=bed)
            return task, False
        try:
            with transaction.atomic():
                task = HousekeepingTask.objects.create(
                    property=prop,
                    room=room,
                    bed=bed,
                    kind=kind,
                    priority=priority,
                    business_date=today,
                    estimated_minutes=estimated_minutes(room, kind),
                    reservation=reservation,
                    created_source=source,
                )
                audit.record(
                    action="housekeeping.task_created",
                    target=task,
                    actor=actor,
                    source="user" if user_or_none(actor) else SOURCE_AUDIT.get(source, "system"),
                    property=prop,
                    summary=f"{task.get_kind_display()} · habitación {room.number}",
                    changes={"kind": [None, kind], "priority": [None, priority]},
                )
        except IntegrityError:
            continue  # another process created it meanwhile: update that one
        return task, True
    raise RuntimeError(f"No se pudo crear la tarea de limpieza de la habitación {room.number}")


def _merge_into(task, room, *, kind, priority, reservation, bed) -> None:
    fields = []
    if kind == Kind.DEPARTURE_CLEAN and task.kind == Kind.STAYOVER:
        task.kind = Kind.DEPARTURE_CLEAN
        task.estimated_minutes = estimated_minutes(room, Kind.DEPARTURE_CLEAN)
        fields += ["kind", "estimated_minutes"]
    if rank(priority) > rank(task.priority):
        task.priority = priority
        fields.append("priority")
    if reservation is not None and task.reservation_id is None:
        task.reservation = reservation
        fields.append("reservation")
    if task.bed_id is not None and (bed is None or bed.pk != task.bed_id):
        task.bed = None
        fields.append("bed")
    if fields:
        task.save(update_fields=[*fields, "updated_at"])


def close_pending_turnovers(room, *, new_status) -> int:
    """The room was declared clean / inspected outside a task: its pending departure / stayover cleans are
    no longer needed (cancelled with a note). A clean already in progress stays with its housekeeper."""
    note = f"Cancelada automáticamente: la habitación se marcó «{new_status}» sin terminar la tarea."
    closed = 0
    for task in HousekeepingTask.objects.filter(room=room, status=Status.PENDING, kind__in=TURNOVER_KINDS):
        task.status = Status.CANCELLED
        task.notes = f"{task.notes}\n{note}".strip()
        task.save(update_fields=["status", "notes", "updated_at"])
        audit.record(
            action="housekeeping.task_cancelled",
            target=task,
            source="automation",
            property=task.property,
            summary=f"{task.get_kind_display()} · habitación {room.number}: {note}",
            changes={"status": [Status.PENDING, Status.CANCELLED]},
        )
        closed += 1
    return closed


# ---- Life cycle ---------------------------------------------------------------------------------------


def _invalid_state(message: str) -> ConflictError:
    return ConflictError(message, code="invalid_state")


def _lock(task) -> HousekeepingTask:
    return (
        HousekeepingTask.objects.select_for_update(of=("self",))
        .select_related("room__room_type", "room__property", "property", "assigned_to")
        .get(pk=task.pk)
    )


def _append_note(task, note: str) -> None:
    if note:
        task.notes = f"{task.notes}\n{note}".strip()


def _record(task, action, *, actor, summary, changes, source="user") -> None:
    audit.record(
        action=action,
        target=task,
        actor=actor,
        source=source if user_or_none(actor) is None else "user",
        property=task.property,
        summary=f"{task.get_kind_display()} · habitación {task.room.number}: {summary}",
        changes=changes,
    )


def guest_still_in_room(task) -> bool:
    """A departure clean waits for the check-out: a private room with a guest in house, or the dorm bed of
    the task still occupied (the other beds of a dorm are made while their guests stay)."""
    if task.kind != Kind.DEPARTURE_CLEAN:
        return False
    stays = Stay.objects.filter(room_id=task.room_id, status="checked_in")
    if task.room.room_type.kind == "dorm":
        if task.bed_id is None:
            return False
        stays = stays.filter(bed_id=task.bed_id)
    return stays.exists()


def _ensure_guest_left(task) -> None:
    if guest_still_in_room(task):
        raise ConflictError(
            f"El huésped de la habitación {task.room.number} aún no ha hecho check-out", code="guest_in_room"
        )


def can_clean(user, property) -> bool:
    """Active member with access to the property whose role grants `housekeeping.work`."""
    return bool(user and user.is_active and has_perm(user, property, "housekeeping.work"))


def start_task(task, *, actor) -> HousekeepingTask:
    """pending → in_progress. An unassigned task is taken by whoever starts it."""
    with transaction.atomic():
        task = _lock(task)
        if task.status != Status.PENDING:
            raise _invalid_state("La tarea ya fue iniciada o está cerrada")
        _ensure_guest_left(task)
        task.status, task.started_at = Status.IN_PROGRESS, timezone.now()
        fields = ["status", "started_at"]
        if task.assigned_to_id is None and user_or_none(actor) is not None:
            task.assigned_to = actor
            fields.append("assigned_to")
        task.save(update_fields=[*fields, "updated_at"])
        _record(
            task,
            "housekeeping.task_started",
            actor=actor,
            summary="iniciada",
            changes={"status": [Status.PENDING, Status.IN_PROGRESS]},
        )
    return task


def finish_task(task, *, actor, notes: str = "") -> HousekeepingTask:
    """pending / in_progress → done. A clean leaves the room `clean` (a room out of service keeps that status)
    and, with `require_inspection`, creates the inspection task."""
    with transaction.atomic():
        task = _lock(task)
        if task.kind == Kind.INSPECTION:
            raise _invalid_state("Una inspección se aprueba o se rechaza, no se termina")
        if task.status not in OPEN_STATUSES:
            raise _invalid_state("La tarea ya está cerrada")
        _ensure_guest_left(task)
        old_status, now = task.status, timezone.now()
        task.status, task.finished_at, task.finished_by = Status.DONE, now, user_or_none(actor)
        task.started_at = task.started_at or now
        if task.assigned_to_id is None:
            task.assigned_to = user_or_none(actor)
        _append_note(task, notes.strip())
        task.save(
            update_fields=[
                "status",
                "finished_at",
                "finished_by",
                "started_at",
                "assigned_to",
                "notes",
                "updated_at",
            ]
        )
        _record(
            task,
            "housekeeping.task_finished",
            actor=actor,
            summary="terminada",
            changes={"status": [old_status, Status.DONE]},
        )
        if task.kind in CLEANING_KINDS:
            room = Room.objects.select_related("property").get(pk=task.room_id)
            if room.housekeeping_status != Room.HousekeepingStatus.OUT_OF_SERVICE:
                set_housekeeping_status(room, Room.HousekeepingStatus.CLEAN, actor=actor, source="user")
                if get_settings(task.property).require_inspection:
                    _create_inspection(task, actor=actor)
    return task


def _create_inspection(task, *, actor) -> HousekeepingTask | None:
    open_inspection = HousekeepingTask.objects.filter(
        room_id=task.room_id, kind=Kind.INSPECTION, status__in=OPEN_STATUSES
    ).exists()
    if open_inspection:
        return None
    inspection = HousekeepingTask.objects.create(
        property=task.property,
        room=task.room,
        bed=task.bed,
        kind=Kind.INSPECTION,
        priority=task.priority,
        business_date=task.property.business_date,
        estimated_minutes=estimated_minutes(task.room, Kind.INSPECTION),
        reservation=task.reservation,
        created_source=HousekeepingTask.Source.INSPECTION,
    )
    _record(
        inspection,
        "housekeeping.task_created",
        actor=None,
        source="automation",
        summary="pendiente de inspección",
        changes={"kind": [None, Kind.INSPECTION]},
    )
    return inspection


def inspect_task(task, *, actor, passed: bool = True, notes: str = "") -> HousekeepingTask:
    """Inspect a room: an open inspection task, or directly a finished clean (spot check).

    Passed → the task is `inspected` (and any other open inspection of the room) and the room `inspected`.
    Failed → the room goes back to `dirty` with a high-priority clean assigned to whoever cleaned it last.
    """
    with transaction.atomic():
        task = _lock(task)
        if task.kind == Kind.INSPECTION:
            if task.status not in OPEN_STATUSES:
                raise _invalid_state("La inspección ya está cerrada")
        elif task.kind not in CLEANING_KINDS or task.status != Status.DONE:
            raise _invalid_state("Solo se inspecciona una limpieza terminada")
        now, inspector = timezone.now(), user_or_none(actor)
        old_status = task.status
        room = Room.objects.select_related("property", "room_type").get(pk=task.room_id)
        others = HousekeepingTask.objects.filter(
            room_id=task.room_id, kind=Kind.INSPECTION, status__in=OPEN_STATUSES
        ).exclude(pk=task.pk)
        if passed:
            task.status = Status.INSPECTED
            _append_note(task, notes.strip())
            if task.kind == Kind.INSPECTION:
                task.started_at, task.finished_at, task.finished_by = task.started_at or now, now, inspector
            task.save(
                update_fields=["status", "notes", "started_at", "finished_at", "finished_by", "updated_at"]
            )
            others.update(status=Status.INSPECTED, finished_at=now, finished_by=inspector, updated_at=now)
            set_housekeeping_status(room, Room.HousekeepingStatus.INSPECTED, actor=actor, source="user")
        else:
            note = f"Inspección no aprobada: {notes.strip()}" if notes.strip() else "Inspección no aprobada"
            if task.kind == Kind.INSPECTION:
                task.status = Status.DONE
                task.started_at, task.finished_at, task.finished_by = task.started_at or now, now, inspector
            _append_note(task, note)
            task.save(
                update_fields=["status", "notes", "started_at", "finished_at", "finished_by", "updated_at"]
            )
            others.update(status=Status.CANCELLED, updated_at=now)
            _redo_clean(room, note=note, actor=actor)
            set_housekeeping_status(room, Room.HousekeepingStatus.DIRTY, actor=actor, source="user")
        _record(
            task,
            "housekeeping.task_inspected",
            actor=actor,
            summary="inspección aprobada" if passed else "inspección no aprobada",
            changes={"status": [old_status, task.status], "passed": [None, passed]},
        )
    return task


def _redo_clean(room, *, note: str, actor) -> HousekeepingTask:
    last_clean = (
        HousekeepingTask.objects.filter(
            room=room, kind__in=CLEANING_KINDS, status__in=(Status.DONE, Status.INSPECTED)
        )
        .order_by("-finished_at", "-updated_at")
        .first()
    )
    cleaner = (last_clean.assigned_to or last_clean.finished_by) if last_clean else None
    occupant = in_house_stay(room) if room.room_type.kind == "private" else None
    redo, _created = ensure_turnover_task(
        room,
        kind=Kind.STAYOVER if occupant else Kind.DEPARTURE_CLEAN,
        source=HousekeepingTask.Source.INSPECTION,
        reservation=occupant.reservation if occupant else None,
        actor=actor,
    )
    redo.priority = Priority.HIGH if rank(redo.priority) < rank(Priority.HIGH) else redo.priority
    if redo.assigned_to_id is None:
        redo.assigned_to = cleaner
    _append_note(redo, f"Repetir: {note}")
    redo.save(update_fields=["priority", "assigned_to", "notes", "updated_at"])
    return redo


def assign_task(task, *, user, actor) -> HousekeepingTask:
    """Assign an open task to someone who cleans in this property (`housekeeping.work`), or unassign it."""
    with transaction.atomic():
        task = _lock(task)
        if task.status not in OPEN_STATUSES:
            raise _invalid_state("La tarea ya está cerrada")
        if user is not None and not can_clean(user, task.property):
            raise DomainError(
                "Esa persona no hace limpieza en este hotel (le falta el permiso de limpieza)",
                code="invalid_assignee",
            )
        old = task.assigned_to
        if (old.pk if old else None) != (user.pk if user else None):
            task.assigned_to = user
            task.save(update_fields=["assigned_to", "updated_at"])
            _record(
                task,
                "housekeeping.task_assigned",
                actor=actor,
                summary=f"asignada a {user.full_name or user.email}" if user else "sin asignar",
                changes={"assigned_to": [str(old.pk) if old else None, str(user.pk) if user else None]},
            )
    return task


UPDATABLE_FIELDS = ("priority", "notes", "estimated_minutes")


def update_task(task, data: dict, *, actor) -> HousekeepingTask:
    """Supervisor edits of an open task: priority, notes (replaced) and estimated minutes."""
    with transaction.atomic():
        task = _lock(task)
        if task.status not in OPEN_STATUSES:
            raise _invalid_state("La tarea ya está cerrada")
        if "priority" in data and data["priority"] not in Priority.values:
            raise DomainError(f"Prioridad inválida: {data['priority']}", code="invalid_priority")
        changes = {}
        for field in UPDATABLE_FIELDS:
            if field not in data:
                continue
            value = data[field].strip() if field == "notes" else data[field]
            if getattr(task, field) != value:
                changes[field] = [getattr(task, field), value]
                setattr(task, field, value)
        if changes:
            task.save(update_fields=[*changes, "updated_at"])
            _record(task, "housekeeping.task_updated", actor=actor, summary="actualizada", changes=changes)
    return task


def cancel_task(task, *, actor, reason: str = "") -> HousekeepingTask:
    with transaction.atomic():
        task = _lock(task)
        if task.status not in OPEN_STATUSES:
            raise _invalid_state("La tarea ya está cerrada")
        old_status = task.status
        task.status = Status.CANCELLED
        _append_note(task, f"Cancelada: {reason.strip()}" if reason.strip() else "")
        task.save(update_fields=["status", "notes", "updated_at"])
        _record(
            task,
            "housekeeping.task_cancelled",
            actor=actor,
            summary="cancelada",
            changes={"status": [old_status, Status.CANCELLED]},
        )
    return task


def create_task(
    property,
    *,
    room,
    kind,
    priority=Priority.NORMAL,
    notes: str = "",
    assigned_to=None,
    bed=None,
    minutes: int | None = None,
    actor=None,
) -> HousekeepingTask:
    """A task created by a supervisor (deep clean, turndown, other…) for the business date."""
    if kind not in Kind.values:
        raise DomainError(f"Tipo de tarea inválido: {kind}", code="invalid_kind")
    if priority not in Priority.values:
        raise DomainError(f"Prioridad inválida: {priority}", code="invalid_priority")
    if room.property_id != property.pk:
        raise DomainError("La habitación no pertenece a este hotel", code="invalid_room")
    if bed is not None and bed.room_id != room.pk:
        raise DomainError("La cama no pertenece a esta habitación", code="invalid_bed")
    if assigned_to is not None and not can_clean(assigned_to, property):
        raise DomainError("Esa persona no hace limpieza en este hotel", code="invalid_assignee")
    if kind in TURNOVER_KINDS:
        existing = HousekeepingTask.objects.filter(
            room=room, kind__in=TURNOVER_KINDS, status__in=OPEN_STATUSES
        ).first()
        if existing is not None:
            raise ConflictError(
                f"La habitación {room.number} ya tiene una limpieza abierta",
                code="task_exists",
                task_id=existing.pk,
            )
    try:
        with transaction.atomic():
            task = HousekeepingTask.objects.create(
                property=property,
                room=room,
                bed=bed,
                kind=kind,
                priority=priority,
                business_date=property.business_date,
                estimated_minutes=minutes or estimated_minutes(room, kind),
                notes=notes.strip(),
                assigned_to=assigned_to,
                created_source=HousekeepingTask.Source.MANUAL,
            )
            _record(
                task,
                "housekeeping.task_created",
                actor=actor,
                summary="creada",
                changes={"kind": [None, kind], "priority": [None, priority]},
            )
    except IntegrityError:
        raise ConflictError(
            f"La habitación {room.number} ya tiene una limpieza abierta", code="task_exists"
        ) from None
    return task
