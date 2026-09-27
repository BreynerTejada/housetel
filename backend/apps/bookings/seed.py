"""Bookings demo data (plan B2b › Seed). Runs after inventory, rates and guests (SEED_ORDER).

For every property with active categories, rooms and a base plan: reservations from −60 to +90 days around
the business date, generated unit by unit (room, or dorm bed) so they never collide, with a realistic
occupancy (≈ 55–85 %, busier on Friday/Saturday nights and in December–January). Everything goes through the
contract services; states follow the dates:

- past stays → checked out (`check_in`/`check_out` with force, every night charged; realistic timestamps),
  some no-shows and late cancellations (`cancelled_at` on the arrival day);
- in house → checked in with the room charges posted until yesterday; some leave today;
- arrivals today → confirmed, some in a clean (ready) room, some without room;
- future → confirmed, a few tentative (hold of a few days) and a few cancelled (between booking and today);
- sources mixed: front desk, phone, email, walk-in, booking engine, marketplace and OTA (`booksim`/`airsim`
  with an `external_id`, restrictions not enforced); one or two groups; dorm parties of several beds; VIP
  bookers; lead times spread in `created_at` (pickup / booking-window reports).

Payments are left to the finance seeder (it runs next). Idempotent: a property that already has reservations
is skipped. Shares `ctx.data["bookings"][<property key>] = {"reservations": [ids], "arrivals_today": [ids],
"in_house": [ids], "departures_today": [ids]}`.
"""

import random
import zlib
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction

from apps.bookings.models import Reservation, ReservationGroup, Stay
from apps.bookings.services.assignment import free_units, load_units
from apps.bookings.services.availability import availability
from apps.bookings.services.charges import post_room_charges
from apps.bookings.services.inventory import rebuild_inventory
from apps.bookings.services.reservations import (
    assign_room,
    cancel_reservation,
    check_in,
    check_out,
    create_reservation,
    mark_no_show,
    modify_stay,
    unassign_room,
)
from apps.bookings.services.rooms import READY_STATUSES
from apps.bookings.types import ReservationRequest, StayRequest
from apps.core.errors import DomainError
from apps.guests.models import Guest
from apps.guests.types import GuestInput
from apps.inventory.models import Bed, Room, RoomType
from apps.rates.models import RatePlan

PAST_DAYS = 60
FUTURE_DAYS = 90
PRIVATE_NIGHTS = ([1, 2, 3, 4, 5, 6, 7], [14, 26, 24, 15, 9, 6, 6])
DORM_NIGHTS = ([1, 2, 3, 4, 5], [26, 30, 22, 13, 9])
SOURCES = [
    ("front_desk", 16), ("phone", 10), ("email", 6), ("walk_in", 4), ("booking_engine", 18),
    ("marketplace", 20), ("ota", 26),
]  # fmt: skip
PLAN_WEIGHTS = {"FLEX": 60, "NR": 25, "BB": 15}
MIN_GUESTS = 24
SEED_GUESTS = [
    ("Laura", "Martínez", "CO", "CO"), ("Andrés", "Restrepo", "CO", "CO"), ("Camila", "Rojas", "CO", "CO"),
    ("Juan", "Pérez", "CO", "CO"), ("Valentina", "Gómez", "CO", "CO"), ("Santiago", "López", "CO", "CO"),
    ("Mariana", "Castro", "CO", "CO"), ("Felipe", "Herrera", "CO", "CO"), ("Isabella", "Moreno", "CO", "CO"),
    ("Emma", "Johnson", "US", "US"), ("Lucas", "Martin", "FR", "FR"), ("Sofía", "García", "ES", "ES"),
    ("Hannah", "Müller", "DE", "DE"), ("Pedro", "Silva", "BR", "BR"), ("Olivia", "Brown", "CA", "CA"),
    ("Mateo", "Fernández", "AR", "AR"), ("Diego", "Hernández", "MX", "MX"), ("George", "Smith", "GB", "GB"),
]  # fmt: skip


@dataclass
class Unit:
    room: Room
    bed: Bed | None = None
    busy: list = field(default_factory=list)  # [(start, end)]

    def free(self, start, end) -> bool:
        return all(end <= busy_start or start >= busy_end for busy_start, busy_end in self.busy)


@dataclass
class Intent:
    """A reservation to create: one or several units for the same dates."""

    room_type: RoomType
    units: list
    checkin: date
    checkout: date
    group: ReservationGroup | None = None


def seed(ctx) -> None:
    ctx.data.setdefault("bookings", {})
    for key, prop in ctx.properties.items():
        if Reservation.objects.filter(property=prop).exists():
            ctx.log(f"  bookings: {prop.name} ya tiene reservas, se omite")
            ctx.data["bookings"][key] = _summary(prop)
            continue
        rng = random.Random(ctx.rng.randrange(2**32) ^ zlib.crc32(prop.slug.encode()))
        created = PropertySeeder(ctx, key, prop, rng).run()
        ctx.data["bookings"][key] = _summary(prop)
        ctx.log(f"  bookings: {prop.name} · {created} reservas")


def _summary(prop) -> dict:
    today = prop.business_date
    stays = Stay.objects.filter(reservation__property=prop)
    return {
        "reservations": [
            str(pk) for pk in Reservation.objects.filter(property=prop).values_list("pk", flat=True)
        ],
        "arrivals_today": [
            str(pk)
            for pk in stays.filter(checkin_date=today, status__in=["confirmed", "tentative"]).values_list(
                "reservation_id", flat=True
            )
        ],
        "in_house": [
            str(pk) for pk in stays.filter(status="checked_in").values_list("reservation_id", flat=True)
        ],
        "departures_today": [
            str(pk)
            for pk in stays.filter(checkout_date=today, status="checked_in").values_list(
                "reservation_id", flat=True
            )
        ],
    }


class PropertySeeder:
    def __init__(self, ctx, key, prop, rng):
        self.ctx, self.key, self.prop, self.rng = ctx, key, prop, rng
        self.today = prop.business_date
        self.start = self.today - timedelta(days=PAST_DAYS)
        self.end = self.today + timedelta(days=FUTURE_DAYS)
        self.tz = ZoneInfo(prop.timezone or "America/Bogota")

    # --- orchestration --------------------------------------------------------------------------------------

    def run(self) -> int:
        room_types = list(
            RoomType.objects.filter(property=self.prop, is_active=True).order_by("sort_order", "code")
        )
        self.plans = {
            room_type.pk: [
                plan
                for plan in RatePlan.objects.filter(
                    property=self.prop, is_active=True, room_types=room_type
                ).order_by("sort_order", "code")
            ]
            for room_type in room_types
        }
        self.units = {room_type.pk: self._units(room_type) for room_type in room_types}
        sellable = [
            room_type for room_type in room_types if self.units[room_type.pk] and self.plans[room_type.pk]
        ]
        if not sellable:
            self.ctx.log(f"  bookings: {self.prop.name} sin habitaciones o planes, se omite")
            return 0
        # Materialize InventoryDay for the whole window at once (otherwise every booking on new dates would
        # rebuild its own small range).
        rebuild_inventory(self.prop, self.start - timedelta(days=7), self.end + timedelta(days=8))
        self.guests = self._guest_pool()
        intents = self._group_intents(sellable)
        for room_type in sellable:
            intents += self._intents(room_type)
        intents.sort(key=lambda intent: (intent.checkin, intent.room_type.sort_order))
        created = 0
        for intent in intents:
            if self._create(intent):
                created += 1
        self._todays_arrivals()
        self._room_statuses()
        return created

    # --- inventory model ------------------------------------------------------------------------------------

    def _units(self, room_type) -> list:
        rooms = list(
            Room.objects.filter(room_type=room_type, is_active=True).order_by("sort_order", "number")
        )
        if room_type.kind == RoomType.Kind.DORM:
            return [
                Unit(bed.room, bed)
                for room in rooms
                for bed in room.beds.filter(is_active=True).order_by("label")
            ]
        return [Unit(room) for room in rooms]

    def _start_probability(self, day) -> float:
        probability = 0.42
        if day.weekday() in (4, 5):  # Friday / Saturday nights
            probability += 0.2
        if day.month in (12, 1):
            probability += 0.1
        return probability

    def _intents(self, room_type) -> list:
        dorm = room_type.kind == RoomType.Kind.DORM
        nights_choice = DORM_NIGHTS if dorm else PRIVATE_NIGHTS
        intents = []
        units = self.units[room_type.pk]
        for unit in units:
            day = self.start + timedelta(days=self.rng.randint(0, 2))
            while day < self.end:
                if not unit.free(day, day + timedelta(days=1)) or self.rng.random() > self._start_probability(
                    day
                ):
                    day += timedelta(days=1)
                    continue
                nights = self.rng.choices(*nights_choice)[0]
                checkout = day + timedelta(days=nights)
                while not unit.free(day, checkout):
                    checkout -= timedelta(days=1)
                if checkout <= day or checkout <= self.start:
                    day += timedelta(days=1)
                    continue
                party = [unit]
                if dorm and self.rng.random() < 0.3:  # friends sharing the dorm room
                    for other in units:
                        if len(party) >= self.rng.randint(2, 4):
                            break
                        if other is not unit and other.room == unit.room and other.free(day, checkout):
                            party.append(other)
                for member in party:
                    member.busy.append((day, checkout))
                intents.append(Intent(room_type, party, day, checkout))
                day = checkout + timedelta(days=0 if self.rng.random() < 0.6 else self.rng.randint(1, 2))
        return intents

    def _group_intents(self, room_types) -> list:
        """One or two groups (a wedding, a company) with a few rooms of the same category and dates."""
        groups = []
        privates = [room_type for room_type in room_types if room_type.kind == RoomType.Kind.PRIVATE]
        if not privates:
            return groups
        names = ["Boda Rodríguez · Pérez", "Congreso Médico Andino"]
        for index, offset in enumerate((6, 21)[: 1 + (len(self.units[privates[0].pk]) >= 8)]):
            room_type = privates[index % len(privates)]
            checkin = self.today + timedelta(days=offset)
            checkout = checkin + timedelta(days=self.rng.randint(2, 3))
            free = [unit for unit in self.units[room_type.pk] if unit.free(checkin, checkout)]
            size = min(len(free), 3 if len(free) < 8 else 4)
            if size < 2:
                continue
            group = ReservationGroup.objects.create(
                property=self.prop, name=names[index], notes="Grupo de demostración"
            )
            for unit in free[:size]:
                unit.busy.append((checkin, checkout))
                groups.append(Intent(room_type, [unit], checkin, checkout, group=group))
        return groups

    # --- guests ---------------------------------------------------------------------------------------------

    def _guest_pool(self) -> list:
        organization = self.prop.organization
        ids = next(
            (
                value
                for org_key, value in (self.ctx.data.get("guests") or {}).items()
                if self.ctx.orgs.get(org_key) == organization
            ),
            None,
        )
        pool = Guest.objects.filter(organization=organization, merged_into__isnull=True)
        if ids:
            pool = pool.filter(pk__in=ids)
        guests = list(pool.order_by("created_at"))
        if len(guests) < MIN_GUESTS:
            from apps.guests.services import upsert_guest

            for index, (first, last, nationality, residence) in enumerate(SEED_GUESTS):
                slug = f"{first}.{last}".lower().encode("ascii", "ignore").decode()
                guests.append(
                    upsert_guest(
                        organization,
                        GuestInput(
                            first_name=first,
                            last_name=last,
                            email=f"{slug}@example.com",
                            document_type="CC" if nationality == "CO" else "PA",
                            document_number=f"{'10' if nationality == 'CO' else 'P'}{7000100 + index}",
                            nationality=nationality,
                            country_of_residence=residence,
                            language="es" if nationality in ("CO", "ES", "AR", "MX") else "en",
                            data_processing_consent=True,
                        ),
                    )
                )
        if not any(guest.is_vip for guest in guests):
            from apps.guests.services import update_guest

            update_guest(guests[0], {"is_vip": True}, source="system")
        return guests

    def _booker(self, intent):
        vips = [guest for guest in self.guests if guest.is_vip]
        arriving_soon = self.today <= intent.checkin <= self.today + timedelta(days=2)
        if vips and (self.rng.random() < 0.05 or (arriving_soon and self.rng.random() < 0.25)):
            return self.rng.choice(vips)
        return self.rng.choice(self.guests)

    # --- creation -------------------------------------------------------------------------------------------

    def _create(self, intent) -> bool:
        source = self.rng.choices([name for name, _ in SOURCES], [weight for _, weight in SOURCES])[0]
        if source == "walk_in" and intent.checkin > self.today:
            source = "front_desk"
        plan = self._plan(intent.room_type)
        assign = self._assign_now(intent)
        stays = [
            StayRequest(
                room_type_id=intent.room_type.pk,
                rate_plan_id=plan.pk,
                checkin=intent.checkin,
                checkout=intent.checkout,
                adults=self._adults(intent.room_type),
                room_id=unit.room.pk if assign else None,
                bed_id=unit.bed.pk if assign and unit.bed else None,
            )
            for unit in intent.units
        ]
        channel = self.rng.choice(["booksim", "airsim"]) if source == "ota" else ""
        future = intent.checkin > self.today
        status = "tentative" if future and source != "ota" and self.rng.random() < 0.06 else "confirmed"
        req = ReservationRequest(
            property=self.prop,
            booker=self._booker(intent),
            stays=stays,
            source=source,
            channel_code=channel,
            external_id=f"{channel[:2].upper()}-{self.rng.randint(10_000_000, 99_999_999)}"
            if channel
            else "",
            language="es",
            status=status,
            hold_minutes=self.rng.randint(2, 4) * 24 * 60,
            enforce_restrictions=source != "ota",
            guarantee="ota" if source == "ota" else self.rng.choice(["none", "card", "deposit"]),
            group_id=intent.group.pk if intent.group else None,
            special_requests=self.rng.choice(
                ["", "", "", "Cama adicional para bebé", "Llegada tarde", "Piso alto"]
            ),
        )
        try:
            with transaction.atomic():
                reservation = create_reservation(req, source_label="system")
                self._backdate(reservation)
                self._advance(reservation, intent)
        except DomainError as exc:
            self.ctx.log(f"    omitida {intent.room_type.code} {intent.checkin}: {exc.message}")
            return False
        return True

    def _plan(self, room_type):
        plans = self.plans[room_type.pk]
        weights = [PLAN_WEIGHTS.get(plan.code, 10) for plan in plans]
        return self.rng.choices(plans, weights)[0]

    def _adults(self, room_type) -> int:
        if room_type.kind == RoomType.Kind.DORM:
            return 1
        return max(1, min(room_type.max_adults, self.rng.choices([1, 2, 2, 2, 3], k=1)[0]))

    def _assign_now(self, intent) -> bool:
        """Past and in-house stays always have their room; today's arrivals half of the time; the future
        mostly for the next week."""
        if intent.checkin < self.today or intent.group:
            return True
        if intent.checkin == self.today:
            return self.rng.random() < 0.5
        return self.rng.random() < (0.7 if intent.checkin <= self.today + timedelta(days=7) else 0.25)

    def _backdate(self, reservation) -> None:
        """Booking lead time: created some days before arrival (never in the future)."""
        lead = self.rng.choices([0, 1, 3, 7, 14, 30, 60], [8, 10, 14, 20, 20, 18, 10])[0]
        created = datetime.combine(reservation.checkin_date - timedelta(days=lead), time(10), tzinfo=self.tz)
        created += timedelta(minutes=self.rng.randint(0, 600))
        now = datetime.now(self.tz)
        Reservation.objects.filter(pk=reservation.pk).update(created_at=min(created, now))

    def _advance(self, reservation, intent) -> None:
        """Bring the reservation to the state its dates imply (only through the services)."""
        if reservation.status == "tentative":
            return
        if intent.checkout < self.today or (intent.checkout == self.today and intent.checkin < self.today):
            roll = self.rng.random()
            if intent.checkout < self.today and roll < 0.05:
                mark_no_show(reservation, source="system")
                return
            if intent.checkout < self.today and roll < 0.12:
                cancel_reservation(reservation, reason="Cambio de planes del huésped", source="user")
                self._date_cancellation(reservation, late=True)
                return
        elif intent.checkin > self.today:
            if self.rng.random() < 0.05:
                cancel_reservation(reservation, reason="El huésped canceló", source="guest")
                self._date_cancellation(reservation, late=False)
            return
        elif intent.checkin == self.today:
            return
        for stay in Stay.objects.filter(reservation=reservation).order_by("created_at"):
            check_in(stay, force=True)
            arrived = datetime.combine(stay.checkin_date, time(15), tzinfo=self.tz) + timedelta(
                minutes=self.rng.randint(0, 420)
            )
            Stay.objects.filter(pk=stay.pk).update(checked_in_at=arrived)
            if stay.checkout_date < self.today:
                check_out(stay, force=True)
                left = datetime.combine(stay.checkout_date, time(9), tzinfo=self.tz) + timedelta(
                    minutes=self.rng.randint(0, 180)
                )
                Stay.objects.filter(pk=stay.pk).update(checked_out_at=left)
            else:
                post_room_charges(stay, until_date=self.today, source="system")

    def _date_cancellation(self, reservation, *, late: bool) -> None:
        """`cancel_reservation` stamps `cancelled_at` with the moment the seed runs: move it to when it
        happened.

        A past booking was cancelled on its arrival day, before or around check-in time (a late cancellation:
        the reason it paid the penalty computed now). A future one some time between the booking and today,
        unless its penalty depends on how close to the arrival it came (then it keeps today). Never before the
        booking nor in the future. (The finance seed dates the penalty charge on that same day.)"""
        values = Reservation.objects.filter(pk=reservation.pk).values(
            "created_at", "cancelled_at", "cancellation_fee", "cancellation_policy_snapshot"
        )[0]
        created, stamped = values["created_at"], values["cancelled_at"]
        policy = values["cancellation_policy_snapshot"] or {}
        if late:
            moment = datetime.combine(reservation.checkin_date, time(7), tzinfo=self.tz)
            moment += timedelta(minutes=self.rng.randint(0, 420))
        elif values["cancellation_fee"] and not policy.get("non_refundable"):
            return
        else:
            span = max(0, int((stamped - created).total_seconds()))
            moment = created + timedelta(seconds=self.rng.randint(0, span))
        moment = min(max(moment, created + timedelta(minutes=30)), stamped)
        Reservation.objects.filter(pk=reservation.pk).update(cancelled_at=moment)

    # --- finishing touches ----------------------------------------------------------------------------------

    def _todays_arrivals(self) -> None:
        """Today's arrivals show both cases (the "Hoy" panel and the auto-assignment demo): at least two (a
        phone or front-desk booking is added in a unit free tonight when the dice left fewer), one in a vacant
        room — no guest still in it — that `_room_statuses` makes ready, and one without room. Groups are left
        alone."""
        arrivals = self._arrivals()
        for _attempt in range(4):
            if len(arrivals) >= 2:
                break
            free = self._free_tonight() or self._make_room_tonight()
            if not free:
                break
            self._book_today(free[0])
            arrivals = self._arrivals()
        if len(arrivals) < 2:
            return
        occupied = set(
            Stay.objects.filter(reservation__property=self.prop, status="checked_in").values_list(
                "room_id", flat=True
            )
        )
        ready = next((stay for stay in arrivals if stay.room_id and stay.room_id not in occupied), None)
        if ready is None:
            for stay in sorted(arrivals, key=lambda item: item.room_type.kind == RoomType.Kind.DORM):
                unit = self._vacant_unit(stay, occupied)
                if unit is not None:
                    assign_room(stay, unit.room, bed=unit.bed)
                    ready = stay
                    break
        others = [stay for stay in arrivals if ready is None or stay.pk != ready.pk]
        if all(stay.room_id for stay in others):
            unassign_room(others[-1])

    def _vacant_unit(self, stay, occupied):
        """A unit of the stay's category free for its dates in a room nobody is staying in now."""
        units = load_units(self.prop, [stay.room_type_id], stay.checkin_date, stay.checkout_date)
        return next(
            (
                unit
                for unit in free_units(stay, units.get(stay.room_type_id, []))
                if unit.room.pk not in occupied
            ),
            None,
        )

    def _arrivals(self) -> list:
        return list(
            Stay.objects.filter(
                reservation__property=self.prop,
                checkin_date=self.today,
                status__in=["confirmed", "tentative"],
                reservation__group__isnull=True,
            )
            .select_related("reservation__property", "room_type")
            .order_by("created_at")
        )

    def _free_tonight(self) -> list:
        """Active categories with a unit free tonight, private rooms first."""
        free = availability(property=self.prop, checkin=self.today, checkout=self.today + timedelta(days=1))
        room_types = RoomType.objects.filter(pk__in=[pk for pk, units in free.items() if units > 0])
        return sorted(
            room_types, key=lambda room_type: (room_type.kind == RoomType.Kind.DORM, room_type.sort_order)
        )

    def _make_room_tonight(self) -> list:
        """Full tonight: an in-house guest of a private room leaves today instead (one more departure of
        today), which frees the room for an arrival."""
        stay = (
            Stay.objects.filter(
                reservation__property=self.prop,
                status="checked_in",
                checkin_date__lt=self.today,
                checkout_date__gt=self.today,
                room_type__kind=RoomType.Kind.PRIVATE,
            )
            .order_by("-checkout_date", "created_at")
            .first()
        )
        if stay is None:
            return []
        try:
            with transaction.atomic():
                modify_stay(stay, checkout=self.today, reprice=False)
        except DomainError:
            return []
        return self._free_tonight()

    def _book_today(self, room_type) -> None:
        """A phone / front-desk arrival of today without room (the longest stay that fits, up to 3 nights)."""
        plan = (
            RatePlan.objects.filter(property=self.prop, is_active=True, room_types=room_type)
            .order_by("sort_order", "code")
            .first()
        )
        if plan is None:
            return
        guests = getattr(self, "guests", None) or self._guest_pool()
        booker, source = self.rng.choice(guests), self.rng.choice(["phone", "front_desk"])
        adults = self._adults(room_type)
        for nights in range(self.rng.randint(1, 3), 0, -1):
            req = ReservationRequest(
                property=self.prop,
                booker=booker,
                stays=[
                    StayRequest(
                        room_type_id=room_type.pk,
                        rate_plan_id=plan.pk,
                        checkin=self.today,
                        checkout=self.today + timedelta(days=nights),
                        adults=adults,
                    )
                ],
                source=source,
                guarantee="card",
            )
            try:
                with transaction.atomic():
                    create_reservation(req, source_label="system")
                return
            except DomainError as exc:
                self.ctx.log(
                    f"    llegada de hoy ({nights} noches) omitida en {room_type.code}: {exc.message}"
                )

    def _room_statuses(self) -> None:
        """After the history, rooms reflect today: rooms of in-house guests are part dirty (stayover service
        pending), rooms left yesterday are dirty, most arrival rooms are ready (always the first one) unless a
        guest still has to leave them today; the rest is clean."""
        from apps.inventory.services import set_housekeeping_status

        stays = Stay.objects.filter(reservation__property=self.prop, room__isnull=False)
        arrival_rooms = set(
            stays.filter(checkin_date=self.today, status__in=["confirmed", "tentative"]).values_list(
                "room_id", flat=True
            )
        )
        in_house = set(stays.filter(status="checked_in").values_list("room_id", flat=True))
        left_yesterday = set(
            stays.filter(status="checked_out", checkout_date=self.today - timedelta(days=1)).values_list(
                "room_id", flat=True
            )
        )
        ready_arrival = False
        for room in Room.objects.filter(property=self.prop, is_active=True).order_by("sort_order", "number"):
            if room.pk in in_house:
                status = "dirty" if self.rng.random() < 0.4 else "clean"
            elif room.pk in arrival_rooms:
                dirty = ready_arrival and self.rng.random() < 0.3
                status = "dirty" if dirty else self.rng.choice(["clean", "inspected"])
                ready_arrival = ready_arrival or status in READY_STATUSES
            elif room.pk in left_yesterday:
                status = "dirty"
            else:
                status = "clean"
            if room.housekeeping_status != status:
                set_housekeeping_status(room, status, source="system")
