"""Housekeeping demo data (plan C2 · Seed). Runs after bookings and finance (`SEED_ORDER`).

Per property with rooms, through the housekeeping services (so rooms, blocks, audit and inventory stay
coherent). Idempotent: a hotel that already has tasks for its business date keeps them, and one that already
has tickets gets no new ones; existing settings are never overwritten.

1. Settings: the defaults; Andino Medellín requires inspection (shows the supervisor's flow).
2. Three maintenance tickets, before planning the day (a blocked room is out of service and gets no clean):
   - «Aire acondicionado no enfría»: blocks a vacant room (no guest in house, no active stay nor block in the
     next two nights) through `inventory.block_room`;
   - «Grifo del lavamanos gotea»: open, in a room, reported by the housekeeper with a (drawn) photo;
   - «Bombillo fundido en el pasillo»: common area, in progress with the maintenance technician or the owner.
3. Today's tasks: the daily generation (departures, stayovers, dirty rooms) and the auto-assignment among the
   hotel's housekeepers (Casa Aurora → limpieza@casaaurora.co; the Bogotá hostel has none: unassigned).
4. The morning's progress, as each housekeeper: about half of the cleans she can do are finished (room clean;
   an inspection pending where required), one is in progress and the rest wait. Departures whose guest has
   not checked out yet stay pending. Work times are spread over the morning, never before today's midnight.

`seed_demo` runs this inside `seeding()`: the housekeeping receivers ignore the signals of these writes.
"""

import io
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.files.base import ContentFile
from django.utils import timezone

from apps.bookings.models import ACTIVE_STAY_STATUSES, Stay
from apps.core.models import Property
from apps.housekeeping.models import HousekeepingSettings, HousekeepingTask, MaintenanceTicket, Priority
from apps.housekeeping.services import tasks as task_svc
from apps.housekeeping.services import tickets as ticket_svc
from apps.housekeeping.services.assignment import (
    auto_assign,
    eligible_staff,
    floor_key,
    maintenance_staff,
    natural_key,
)
from apps.housekeeping.services.common import CLEANING_KINDS, Status
from apps.housekeeping.services.generation import generate_daily_tasks
from apps.inventory.models import Room, RoomBlock

INSPECTION_PROPERTIES = {"andino_mde"}
OWNER_KEYS = {"aurora": "aurora_owner", "andino_mde": "andino_owner", "andino_bog": "andino_owner"}
BLOCK_NIGHTS = 2
READY = (Room.HousekeepingStatus.CLEAN, Room.HousekeepingStatus.INSPECTED)


def seed(ctx) -> None:
    for key, prop in ctx.properties.items():
        prop = Property.objects.get(pk=prop.pk)
        rooms = list(
            Room.objects.filter(property=prop, is_active=True)
            .select_related("room_type")
            .order_by("sort_order", "number")
        )
        if not rooms:
            ctx.log(f"  housekeeping: {prop.name} no tiene habitaciones, se omite")
            continue
        HousekeepingSettings.objects.get_or_create(
            property=prop, defaults={"require_inspection": key in INSPECTION_PROPERTIES}
        )
        housekeepers = eligible_staff(prop)
        if not MaintenanceTicket.objects.filter(property=prop).exists():
            owner = ctx.users.get(OWNER_KEYS.get(key, ""))
            _seed_tickets(prop, rooms, reporter=housekeepers[0] if housekeepers else None, owner=owner)
        if HousekeepingTask.objects.filter(property=prop, business_date=prop.business_date).exists():
            ctx.log(f"  housekeeping: {prop.name} ya tiene las tareas de hoy, se omite")
            continue
        generate_daily_tasks(prop)
        auto_assign(prop, staff=housekeepers)
        for housekeeper in housekeepers:
            _morning_progress(prop, housekeeper)
        total = HousekeepingTask.objects.filter(property=prop, business_date=prop.business_date).count()
        ctx.log(f"  housekeeping: {prop.name} · {total} tareas de hoy, 3 tickets de mantenimiento")


# ---- Tickets ----------------------------------------------------------------------------------------------


def _seed_tickets(prop, rooms, *, reporter, owner) -> None:
    today = prop.business_date
    vacant = _vacant_room(prop, rooms, today)
    ticket_svc.create_ticket(
        prop,
        title="Aire acondicionado no enfría",
        room=vacant,
        location="" if vacant else "Habitaciones",
        description="El equipo enciende pero sale aire caliente. Revisar gas y compresor.",
        priority=Priority.HIGH,
        blocks_room=vacant is not None,
        blocked_until=today + timedelta(days=BLOCK_NIGHTS) if vacant else None,
        actor=reporter,
    )
    faucet_room = _occupied_room(prop, rooms, exclude=vacant)
    faucet = ticket_svc.create_ticket(
        prop,
        title="Grifo del lavamanos gotea",
        room=faucet_room,
        description="Gotea constantemente aunque esté cerrado. El huésped pidió revisarlo hoy.",
        priority=Priority.NORMAL,
        actor=reporter,
    )
    ticket_svc.add_photo(faucet, file=_faucet_photo(), actor=reporter)
    floor = next((room.floor for room in reversed(rooms) if room.floor), "")
    bulb = ticket_svc.create_ticket(
        prop,
        title="Bombillo fundido en el pasillo",
        location=f"Pasillo del piso {floor}" if floor else "Pasillo principal",
        description="El pasillo queda oscuro de noche.",
        priority=Priority.LOW,
        actor=reporter,
    )
    technicians = maintenance_staff(prop)
    ticket_svc.start_ticket(bulb, actor=technicians[0] if technicians else owner)


def _vacant_room(prop, rooms, today):
    """A room without guests in house (a guest leaving today is still inside: check-out is exclusive but the
    room is not free until the check-out), active stays nor blocks in the next nights, ready (clean/
    inspected): the last private one in the hotel's order (a dorm only if no private room qualifies). None if
    the hotel is full."""
    end = today + timedelta(days=BLOCK_NIGHTS)
    stays = Stay.objects.filter(room__property=prop)
    busy = set(
        stays.filter(
            status__in=ACTIVE_STAY_STATUSES, checkin_date__lt=end, checkout_date__gt=today
        ).values_list("room_id", flat=True)
    )
    busy |= set(stays.filter(status="checked_in").values_list("room_id", flat=True))
    busy |= set(
        RoomBlock.objects.filter(
            room__property=prop, released_at__isnull=True, start_date__lt=end, end_date__gt=today
        ).values_list("room_id", flat=True)
    )
    candidates = [room for room in rooms if room.pk not in busy and room.housekeeping_status in READY]
    private = [room for room in candidates if room.room_type.kind == "private"]
    pool = private or candidates
    return pool[-1] if pool else None


def _occupied_room(prop, rooms, *, exclude):
    in_house = set(
        Stay.objects.filter(room__property=prop, status="checked_in").values_list("room_id", flat=True)
    )
    usable = [room for room in rooms if room != exclude]
    return next((room for room in usable if room.pk in in_house), usable[0] if usable else None)


def _faucet_photo() -> ContentFile:
    """A small drawn JPEG (a dripping faucet over a basin): deterministic and offline."""
    from PIL import Image, ImageDraw

    width, height = 960, 720
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):  # warm wall, lighter at the top
        shade = 236 - (y * 38) // height
        draw.line([(0, y), (width, y)], fill=(shade, shade - 5, shade - 12))
    draw.rectangle([0, 470, width, height], fill=(214, 206, 196))  # counter
    draw.rounded_rectangle(
        [250, 400, 710, 600], radius=70, fill=(248, 246, 243), outline=(176, 168, 158), width=6
    )
    draw.ellipse([440, 470, 520, 510], fill=(160, 170, 180))  # drain
    draw.rounded_rectangle([455, 230, 505, 410], radius=14, fill=(150, 159, 170))  # faucet body
    draw.rounded_rectangle([455, 230, 640, 280], radius=20, fill=(150, 159, 170))  # spout
    draw.rounded_rectangle([420, 200, 540, 232], radius=12, fill=(130, 139, 150))  # handle
    for top in (300, 340, 382):  # drops
        draw.ellipse([612, top, 634, top + 30], fill=(78, 108, 136))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=82)
    return ContentFile(buffer.getvalue(), name="grifo.jpg")


# ---- Tasks ------------------------------------------------------------------------------------------------


def _morning_progress(prop, housekeeper) -> None:
    tasks = [
        task
        for task in HousekeepingTask.objects.filter(
            property=prop,
            business_date=prop.business_date,
            status=Status.PENDING,
            assigned_to=housekeeper,
            kind__in=CLEANING_KINDS,
        ).select_related("room__room_type")
        if not task_svc.guest_still_in_room(task)
    ]
    tasks.sort(key=lambda task: (floor_key(task.room.floor), natural_key(task.room.number)))
    done_count = len(tasks) // 2
    done, current = tasks[:done_count], tasks[done_count] if len(tasks) > done_count else None
    for task in done:
        task_svc.start_task(task, actor=housekeeper)
        task_svc.finish_task(task, actor=housekeeper)
    if current is not None:
        task_svc.start_task(current, actor=housekeeper)
    _spread_work_times(prop, done, current)


def _spread_work_times(prop, done, current) -> None:
    """Backwards from now: the task in progress started a few minutes ago and each finished one took its
    estimated minutes; nothing before today's midnight in the hotel's time zone."""
    zone = ZoneInfo(prop.timezone or "America/Bogota")
    now = timezone.now()
    midnight = datetime.combine(now.astimezone(zone).date(), time.min, tzinfo=zone)
    cursor = now - timedelta(minutes=12)
    if current is not None:
        HousekeepingTask.objects.filter(pk=current.pk).update(started_at=max(midnight, cursor))
    for task in reversed(done):
        finished = max(midnight, cursor - timedelta(minutes=5))
        started = max(midnight, finished - timedelta(minutes=task.estimated_minutes))
        HousekeepingTask.objects.filter(pk=task.pk).update(started_at=started, finished_at=finished)
        cursor = started
