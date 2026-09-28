"""Read models of the housekeeping API: occupancy of the day, the supervision board, the day summary and the
staff with their load. Everything is computed with a constant number of queries."""

from collections import defaultdict

from django.db.models import Case, Count, IntegerField, Q, Sum, Value, When

from apps.bookings.models import Stay
from apps.housekeeping.models import MaintenanceTicket, Priority
from apps.housekeeping.services.assignment import eligible_staff, floor_key, maintenance_staff
from apps.housekeeping.services.common import ARRIVING_STATUSES, Kind, Status
from apps.housekeeping.services.config import get_settings
from apps.housekeeping.services.queries import day_tasks
from apps.inventory.models import Room, RoomBlock

TASK_RELATED = ("room__room_type", "bed", "assigned_to", "finished_by", "reservation")
OPEN_TICKET_STATUSES = (MaintenanceTicket.Status.OPEN, MaintenanceTicket.Status.IN_PROGRESS)

STATUS_ORDER = Case(
    When(status=Status.IN_PROGRESS, then=Value(0)),
    When(status=Status.PENDING, then=Value(1)),
    When(status=Status.DONE, then=Value(2)),
    When(status=Status.INSPECTED, then=Value(3)),
    default=Value(4),
    output_field=IntegerField(),
)
PRIORITY_ORDER = Case(
    When(priority=Priority.URGENT, then=Value(0)),
    When(priority=Priority.HIGH, then=Value(1)),
    When(priority=Priority.NORMAL, then=Value(2)),
    default=Value(3),
    output_field=IntegerField(),
)


def ordered_tasks(queryset):
    """Open work first (in progress, then pending), by priority, then room order."""
    return queryset.annotate(_status_order=STATUS_ORDER, _priority_order=PRIORITY_ORDER).order_by(
        "_status_order", "_priority_order", "room__sort_order", "room__number", "created_at"
    )


def _eta(value) -> str | None:
    return value.strftime("%H:%M") if value else None


class DayIndex:
    """Who is in each room and who arrives today (two queries for any number of rooms)."""

    def __init__(self, property, rooms):
        self.today = property.business_date
        rooms = list(rooms)
        room_ids = [room.pk for room in rooms]
        self.dorm_rooms = {room.pk for room in rooms if room.room_type.kind == "dorm"}
        self.occupied_rooms: set = set()
        self.occupied_beds: set = set()
        self.in_house_by_room: dict = {}
        stays = (
            Stay.objects.filter(room_id__in=room_ids, status="checked_in")
            .values(
                "room_id",
                "bed_id",
                "checkout_date",
                "adults",
                "children",
                "reservation__code",
                "reservation__booker__is_vip",
            )
            .order_by("checkout_date", "created_at")
        )
        for stay in stays:
            self.occupied_rooms.add(stay["room_id"])
            if stay["bed_id"]:
                self.occupied_beds.add(stay["bed_id"])
            current = self.in_house_by_room.get(stay["room_id"])
            if current is None:
                self.in_house_by_room[stay["room_id"]] = {
                    "code": stay["reservation__code"],
                    "checkout_date": stay["checkout_date"],
                    "departs_today": stay["checkout_date"] <= self.today,
                    "guests": stay["adults"] + stay["children"],
                    "is_vip": bool(stay["reservation__booker__is_vip"]),
                }
            else:  # dorm: several beds in house
                current["guests"] += stay["adults"] + stay["children"]
                current["departs_today"] = current["departs_today"] or stay["checkout_date"] <= self.today
                current["is_vip"] = current["is_vip"] or bool(stay["reservation__booker__is_vip"])
        self.arrivals: dict = {}
        arrivals = (
            Stay.objects.filter(room_id__in=room_ids, checkin_date=self.today, status__in=ARRIVING_STATUSES)
            .values("room_id", "reservation__code", "reservation__eta", "reservation__booker__is_vip")
            .order_by("reservation__eta", "created_at")
        )
        for stay in arrivals:
            self.arrivals.setdefault(
                stay["room_id"],
                {
                    "code": stay["reservation__code"],
                    "eta": _eta(stay["reservation__eta"]),
                    "is_vip": bool(stay["reservation__booker__is_vip"]),
                },
            )

    def waiting_for_checkout(self, task) -> bool:
        """Same rule as `services.tasks.guest_still_in_room`, from the index."""
        if task.kind != Kind.DEPARTURE_CLEAN:
            return False
        if task.room_id in self.dorm_rooms:
            return task.bed_id is not None and task.bed_id in self.occupied_beds
        return task.room_id in self.occupied_rooms

    def arrival(self, room_id):
        return self.arrivals.get(room_id)

    def in_house(self, room_id):
        return self.in_house_by_room.get(room_id)


def task_context(property, tasks) -> dict:
    """Serializer context for `HousekeepingTaskSerializer` (tasks loaded with `room__room_type`)."""
    rooms = {task.room_id: task.room for task in tasks}
    return {"day": DayIndex(property, rooms.values()), "business_date": property.business_date}


def summary(property) -> dict:
    today = property.business_date
    rooms = Room.objects.filter(property=property, is_active=True).aggregate(
        total=Count("id"),
        clean=Count("id", filter=Q(housekeeping_status="clean")),
        dirty=Count("id", filter=Q(housekeeping_status="dirty")),
        inspected=Count("id", filter=Q(housekeeping_status="inspected")),
        out_of_service=Count("id", filter=Q(housekeeping_status="out_of_service")),
    )
    rooms["occupied"] = (
        Stay.objects.filter(room__property=property, room__is_active=True, status="checked_in")
        .values("room_id")
        .distinct()
        .count()
    )
    work = day_tasks(property, today).exclude(status=Status.CANCELLED)
    cleaning = work.exclude(kind=Kind.INSPECTION)
    done_statuses = (Status.DONE, Status.INSPECTED)
    counts = cleaning.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=Status.PENDING)),
        in_progress=Count("id", filter=Q(status=Status.IN_PROGRESS)),
        done=Count("id", filter=Q(status__in=done_statuses)),
        unassigned=Count("id", filter=Q(status=Status.PENDING, assigned_to__isnull=True)),
        minutes=Sum("estimated_minutes"),
        minutes_done=Sum("estimated_minutes", filter=Q(status__in=done_statuses)),
    )
    inspections = work.filter(kind=Kind.INSPECTION, status__in=(Status.PENDING, Status.IN_PROGRESS)).count()
    tickets = MaintenanceTicket.objects.filter(property=property, status__in=OPEN_TICKET_STATUSES).aggregate(
        open=Count("id"), blocking=Count("id", filter=Q(blocks_room=True))
    )
    return {
        "business_date": today,
        "rooms": rooms,
        "tasks": {
            "total": counts["total"],
            "pending": counts["pending"],
            "in_progress": counts["in_progress"],
            "done": counts["done"],
            "inspections_pending": inspections,
            "unassigned": counts["unassigned"],
        },
        "minutes": {"total": counts["minutes"] or 0, "done": counts["minutes_done"] or 0},
        "tickets": tickets,
    }


def housekeepers_with_load(property) -> list[dict]:
    people = eligible_staff(property)
    loads = {
        row["assigned_to"]: row
        for row in day_tasks(property, property.business_date)
        .exclude(status=Status.CANCELLED)
        .filter(assigned_to__in=people)
        .values("assigned_to")
        .annotate(
            minutes=Sum("estimated_minutes"),
            minutes_done=Sum("estimated_minutes", filter=Q(status__in=(Status.DONE, Status.INSPECTED))),
            tasks=Count("id"),
            tasks_done=Count("id", filter=Q(status__in=(Status.DONE, Status.INSPECTED))),
        )
    }
    rows = []
    for user in people:
        load = loads.get(user.pk, {})
        rows.append(
            {
                "id": user.pk,
                "full_name": user.full_name or user.email,
                "email": user.email,
                "minutes": load.get("minutes") or 0,
                "minutes_done": load.get("minutes_done") or 0,
                "tasks": load.get("tasks") or 0,
                "tasks_done": load.get("tasks_done") or 0,
            }
        )
    return rows


def staff(property) -> dict:
    technicians = maintenance_staff(property)
    open_by_user = dict(
        MaintenanceTicket.objects.filter(
            property=property, status__in=OPEN_TICKET_STATUSES, assigned_to__in=technicians
        )
        .values("assigned_to")
        .annotate(n=Count("id"))
        .values_list("assigned_to", "n")
    )
    return {
        "housekeepers": housekeepers_with_load(property),
        "maintenance": [
            {
                "id": user.pk,
                "full_name": user.full_name or user.email,
                "email": user.email,
                "open_tickets": open_by_user.get(user.pk, 0),
            }
            for user in technicians
        ],
    }


def board(property, *, only_assignee=None) -> dict:
    """Every active room grouped by floor with its status, occupancy, arrival of today, today's tasks (and
    those still open from earlier days), active block and open tickets.

    `only_assignee`: a housekeeper (works without supervising) sees every room but only her own tasks and
    her own load."""
    from apps.housekeeping.api.serializers import HousekeepingSettingsSerializer, HousekeepingTaskSerializer

    today = property.business_date
    rooms = list(
        Room.objects.filter(property=property, is_active=True)
        .select_related("room_type")
        .order_by("sort_order", "number")
    )
    day = DayIndex(property, rooms)
    task_queryset = day_tasks(property, today).select_related(*TASK_RELATED)
    if only_assignee is not None:
        task_queryset = task_queryset.filter(assigned_to=only_assignee)
    tasks = list(ordered_tasks(task_queryset))
    serialized = HousekeepingTaskSerializer(
        tasks, many=True, context={"day": day, "business_date": today}
    ).data
    tasks_by_room = defaultdict(list)
    for task, data in zip(tasks, serialized, strict=True):
        tasks_by_room[task.room_id].append(data)
    blocks = {}
    for block in RoomBlock.objects.filter(
        room__in=rooms, released_at__isnull=True, start_date__lte=today, end_date__gt=today
    ).order_by("start_date"):
        blocks.setdefault(
            block.room_id,
            {
                "id": block.pk,
                "kind": block.kind,
                "reason": block.reason,
                "start_date": block.start_date,
                "end_date": block.end_date,
            },
        )
    tickets = dict(
        MaintenanceTicket.objects.filter(
            property=property, status__in=OPEN_TICKET_STATUSES, room__isnull=False
        )
        .values("room_id")
        .annotate(n=Count("id"))
        .values_list("room_id", "n")
    )
    floors = defaultdict(list)
    for room in rooms:
        room_type = room.room_type
        floors[room.floor].append(
            {
                "id": room.pk,
                "number": room.number,
                "name": room.name,
                "floor": room.floor,
                "housekeeping_status": room.housekeeping_status,
                "room_type": {
                    "id": room_type.pk,
                    "code": room_type.code,
                    "name": room_type.name,
                    "color": room_type.color,
                    "kind": room_type.kind,
                },
                "occupied": room.pk in day.occupied_rooms,
                "in_house": day.in_house(room.pk),
                "arrival_today": day.arrival(room.pk),
                "tasks": tasks_by_room.get(room.pk, []),
                "active_block": blocks.get(room.pk),
                "open_tickets": tickets.get(room.pk, 0),
            }
        )
    staff_rows = housekeepers_with_load(property)
    if only_assignee is not None:
        staff_rows = [row for row in staff_rows if row["id"] == only_assignee.pk]
    return {
        "business_date": today,
        "settings": HousekeepingSettingsSerializer(get_settings(property)).data,
        "summary": summary(property),
        "staff": staff_rows,
        "floors": [{"floor": floor, "rooms": floors[floor]} for floor in sorted(floors, key=floor_key)],
    }
