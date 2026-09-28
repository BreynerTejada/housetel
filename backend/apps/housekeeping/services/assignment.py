"""Who cleans and automatic assignment (automation `housekeeping.auto_assign`, 07:15, and `assign_new_task`
for the cleans created during the day by the receivers).

Housekeepers of a property = active members with access to it whose role grants `housekeeping.work` but not
`housekeeping.supervise` (owners, managers and supervisors match `housekeeping.work` through `*` /
`housekeeping.*` and must not receive rooms to clean).

Algorithm (greedy, deterministic): the target is (minutes already assigned today + minutes to assign) /
people. Tasks go in floor order (then priority, then room number); each one goes to the least-loaded
housekeeper already working on that floor while she stays within target + half a task, otherwise to the
least-loaded housekeeper overall. Result: minutes balanced within one task and every person on as few floors
as possible.
"""

import re

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Membership
from apps.core import audit
from apps.core.permissions import codes_match
from apps.housekeeping.models import HousekeepingTask
from apps.housekeeping.services.common import OPEN_STATUSES, Kind, Status, rank
from apps.housekeeping.services.config import get_settings
from apps.housekeeping.services.queries import day_tasks


def _members_with(property, code: str, *, exclude: str | None = None) -> list:
    memberships = (
        Membership.objects.filter(
            organization_id=property.organization_id, is_active=True, user__is_active=True
        )
        .select_related("user", "role")
        .prefetch_related("properties")
    )
    users = []
    for membership in memberships:
        if not (membership.all_properties or any(p.pk == property.pk for p in membership.properties.all())):
            continue
        granted = membership.role.permissions
        if codes_match(granted, code) and not (exclude and codes_match(granted, exclude)):
            users.append(membership.user)
    return sorted(users, key=lambda u: ((u.full_name or u.email).lower(), str(u.pk)))


def eligible_staff(property) -> list:
    """Housekeepers who receive rooms (see module docstring), sorted by name."""
    return _members_with(property, "housekeeping.work", exclude="housekeeping.supervise")


def maintenance_staff(property) -> list:
    """Maintenance technicians (`housekeeping.maintenance` without `housekeeping.supervise`)."""
    return _members_with(property, "housekeeping.maintenance", exclude="housekeeping.supervise")


def natural_key(value: str) -> tuple:
    return tuple(
        int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value or "") if part
    )


def floor_key(floor: str) -> tuple:
    return (1, "") if not floor else (0, natural_key(floor))


def assign_new_task(task):
    """A clean created during the day (check-out, room marked dirty, repair finished) goes straight to a
    housekeeper when the hotel assigns automatically, with the rule of the daily auto-assignment: someone
    already working that floor while she stays within the balanced target, else the lightest load. Without
    housekeepers, with auto-assignment off, or for an inspection, it stays unassigned. Returns the user."""
    prop = task.property
    if task.assigned_to_id or task.status != Status.PENDING or task.kind == Kind.INSPECTION:
        return None
    if not get_settings(prop).auto_assign:
        return None
    people = eligible_staff(prop)
    if not people:
        return None
    loads = {user.pk: 0 for user in people}
    floors: dict = {user.pk: set() for user in people}
    for row in (
        day_tasks(prop, prop.business_date)
        .filter(status__in=OPEN_STATUSES, assigned_to__in=people)
        .values("assigned_to", "estimated_minutes", "room__floor")
    ):
        loads[row["assigned_to"]] += row["estimated_minutes"]
        floors[row["assigned_to"]].add(row["room__floor"])
    minutes, floor = task.estimated_minutes, task.room.floor
    target = (sum(loads.values()) + minutes) / len(people)
    order = {user.pk: index for index, user in enumerate(people)}
    same_floor = [pk for pk in loads if floor in floors[pk] and loads[pk] + minutes <= target + minutes / 2]
    chosen = next(
        user for user in people if user.pk == min(same_floor or loads, key=lambda pk: (loads[pk], order[pk]))
    )
    with transaction.atomic():
        updated = HousekeepingTask.objects.filter(pk=task.pk, assigned_to__isnull=True).update(
            assigned_to=chosen, updated_at=timezone.now()
        )
        if not updated:
            return None  # someone assigned it meanwhile
        task.assigned_to = chosen
        audit.record(
            action="housekeeping.task_assigned",
            target=task,
            source="automation",
            property=prop,
            summary=(
                f"{task.get_kind_display()} · habitación {task.room.number}: "
                f"asignada automáticamente a {chosen.full_name or chosen.email}"
            ),
            changes={"assigned_to": [None, str(chosen.pk)]},
        )
    return chosen


def auto_assign(property, *, actor=None, staff=None) -> dict:
    """Assign the unassigned pending tasks of the day (inspections excluded) among `staff` (default: every
    housekeeper of the property). Returns the per-person minutes and who goes over `minutes_per_shift`."""
    today = property.business_date
    people = list(staff) if staff is not None else eligible_staff(property)
    order = {user.pk: index for index, user in enumerate(people)}
    with transaction.atomic():
        todo = list(
            day_tasks(property, today)
            .filter(status=Status.PENDING, assigned_to__isnull=True)
            .exclude(kind=Kind.INSPECTION)
            .select_related("room")
            .select_for_update(of=("self",))
        )
        loads = {user.pk: 0 for user in people}
        counts = {user.pk: 0 for user in people}
        floors: dict = {user.pk: set() for user in people}
        assigned_now = []
        if people:
            for task in (
                day_tasks(property, today)
                .filter(status__in=OPEN_STATUSES, assigned_to__in=people)
                .select_related("room")
            ):
                loads[task.assigned_to_id] += task.estimated_minutes
                counts[task.assigned_to_id] += 1
                floors[task.assigned_to_id].add(task.room.floor)
            target = (sum(loads.values()) + sum(t.estimated_minutes for t in todo)) / len(people)
            todo.sort(
                key=lambda t: (
                    floor_key(t.room.floor),
                    -rank(t.priority),
                    natural_key(t.room.number),
                    str(t.pk),
                )
            )
            by_pk = {user.pk: user for user in people}
            for task in todo:
                floor, minutes = task.room.floor, task.estimated_minutes
                same_floor = [
                    pk for pk in loads if floor in floors[pk] and loads[pk] + minutes <= target + minutes / 2
                ]
                chosen = min(same_floor or list(loads), key=lambda pk: (loads[pk], order[pk]))
                task.assigned_to = by_pk[chosen]
                task.save(update_fields=["assigned_to", "updated_at"])
                loads[chosen] += minutes
                counts[chosen] += 1
                floors[chosen].add(floor)
                assigned_now.append(task)
        shift = get_settings(property).minutes_per_shift
        report = {
            "business_date": today.isoformat(),
            "assigned": len(assigned_now),
            "unassigned": len(todo) - len(assigned_now),
            "staff": [
                {
                    "user_id": str(u.pk),
                    "full_name": u.full_name or u.email,
                    "minutes": loads[u.pk],
                    "tasks": counts[u.pk],
                }
                for u in people
            ],
            "overloaded": [str(u.pk) for u in people if loads[u.pk] > shift],
            "minutes_per_shift": shift,
        }
        if assigned_now:
            audit.record(
                action="housekeeping.tasks_auto_assigned",
                target=property,
                actor=actor,
                source="user" if getattr(actor, "is_authenticated", False) else "automation",
                property=property,
                summary=f"Asignó {len(assigned_now)} tareas de limpieza entre {len(people)} personas",
                changes={"assignments": {str(t.pk): str(t.assigned_to_id) for t in assigned_now}},
            )
    return report
