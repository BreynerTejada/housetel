"""Bookings (spec §4 + plan §C/Step 4).

Stay dates are half-open: `checkin_date` inclusive, `checkout_date` exclusive. Overlap queries use
`checkin_date__lt=end, checkout_date__gt=start`. The database forbids two active stays in the same room
(or, in dorms, the same bed) for overlapping nights via ExclusionConstraints over
`daterange(checkin, checkout, '[)')`.
"""

import builtins

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeOperators
from django.db import models
from django.db.models import F, Func, Q, Value

from apps.core.codes import generate_code
from apps.core.dates import nights
from apps.core.fields import json_field, money_field
from apps.core.models import BaseModel, Property
from apps.guests.models import Guest
from apps.inventory.models import Bed, Room, RoomType
from apps.rates.models import RatePlan

ACTIVE_STAY_STATUSES = ["tentative", "confirmed", "checked_in"]


class DateRangeFunc(Func):
    function = "daterange"
    output_field = DateRangeField()


class BookingStatus(models.TextChoices):
    """Shared by Reservation.status and Stay.status."""

    TENTATIVE = "tentative", "Tentativa"
    CONFIRMED = "confirmed", "Confirmada"
    CHECKED_IN = "checked_in", "En casa"
    CHECKED_OUT = "checked_out", "Salió"
    CANCELLED = "cancelled", "Cancelada"
    NO_SHOW = "no_show", "No show"


class ReservationGroup(BaseModel):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="reservation_groups")
    name = models.CharField(max_length=200)
    contact_guest = models.ForeignKey(
        Guest, null=True, blank=True, on_delete=models.SET_NULL, related_name="reservation_groups"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class GroupBlock(BaseModel):
    """An allotment (cupo): `units` rooms — beds in a dorm — of `room_type` held for a group on the nights
    `[start, end)`. The hold is kept in `InventoryDay.held_units` (`services.blocks`): stays created "from the
    block" (`Stay.group_block`) consume it (pickup) and what is not picked up goes back to general inventory
    when the block is released (`released_at`), by hand or on its `release_date` (automation
    `bookings.release_group_blocks`)."""

    group = models.ForeignKey(ReservationGroup, on_delete=models.CASCADE, related_name="blocks")
    room_type = models.ForeignKey(RoomType, on_delete=models.RESTRICT, related_name="group_blocks")
    start = models.DateField()
    end = models.DateField()  # exclusive
    units = models.PositiveSmallIntegerField()
    release_date = models.DateField()
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["start", "created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(end__gt=F("start")), name="group_block_dates_valid"),
            models.CheckConstraint(condition=Q(units__gte=1), name="group_block_units_positive"),
        ]
        indexes = [models.Index(fields=["room_type", "start", "end"], name="group_block_type_range_idx")]

    def __str__(self) -> str:
        return f"{self.group} · {self.units} × {self.room_type} {self.start}→{self.end}"


class Reservation(BaseModel):
    Status = BookingStatus

    class Source(models.TextChoices):
        WALK_IN = "walk_in", "Walk-in"
        PHONE = "phone", "Teléfono"
        EMAIL = "email", "Email"
        FRONT_DESK = "front_desk", "Recepción"
        BOOKING_ENGINE = "booking_engine", "Motor de reservas"
        MARKETPLACE = "marketplace", "Marketplace"
        OTA = "ota", "OTA"
        API = "api", "API"
        IMPORT = "import", "Importación"  # migrated from another PMS (apps.imports)

    class Guarantee(models.TextChoices):
        NONE = "none", "Sin garantía"
        CARD = "card", "Tarjeta"
        DEPOSIT = "deposit", "Depósito"
        OTA = "ota", "OTA"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="reservations")
    code = models.CharField(max_length=20, unique=True)  # generated on save when empty: HT-7K2M9Q
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.CONFIRMED)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.FRONT_DESK)
    channel_code = models.CharField(max_length=40, blank=True)  # booksim, airsim, ical, channex, ...
    external_id = models.CharField(max_length=120, blank=True)
    external_payload = json_field()
    booker = models.ForeignKey(Guest, on_delete=models.RESTRICT, related_name="reservations")
    group = models.ForeignKey(
        ReservationGroup, null=True, blank=True, on_delete=models.SET_NULL, related_name="reservations"
    )
    checkin_date = models.DateField()
    checkout_date = models.DateField()  # exclusive
    adults = models.PositiveSmallIntegerField(default=1)
    children = models.PositiveSmallIntegerField(default=0)
    currency = models.CharField(max_length=3, default="COP")
    total_amount = money_field(default=0)
    language = models.CharField(max_length=5, default="es")
    eta = models.TimeField(null=True, blank=True)
    special_requests = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    promo_code = models.CharField(max_length=40, blank=True)
    guarantee = models.CharField(max_length=10, choices=Guarantee.choices, default=Guarantee.NONE)
    cancellation_policy_snapshot = json_field()
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    cancellation_fee = money_field(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    custom_values = json_field()
    tags = json_field(default=list)
    hold_expires_at = models.DateTimeField(null=True, blank=True)  # tentative reservations only

    class Meta:
        ordering = ["-checkin_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(checkout_date__gt=F("checkin_date")), name="reservation_dates_valid"
            )
        ]
        indexes = [
            models.Index(fields=["property", "checkin_date"], name="reservation_prop_checkin_idx"),
            models.Index(fields=["property", "checkout_date"], name="reservation_prop_checkout_idx"),
            models.Index(fields=["property", "status"], name="reservation_prop_status_idx"),
            models.Index(fields=["property", "channel_code", "external_id"], name="reservation_external_idx"),
        ]

    def __str__(self) -> str:
        return self.code

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = generate_code("HT")
        super().save(*args, **kwargs)


class Stay(BaseModel):
    """A room (or, in dorms, a bed) inside a reservation. Dorm stays: `room` = dorm, `bed` = the bed."""

    Status = BookingStatus

    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name="stays")
    room_type = models.ForeignKey(RoomType, on_delete=models.RESTRICT, related_name="stays")
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.RESTRICT, related_name="stays")
    room = models.ForeignKey(Room, null=True, blank=True, on_delete=models.RESTRICT, related_name="stays")
    bed = models.ForeignKey(Bed, null=True, blank=True, on_delete=models.RESTRICT, related_name="stays")
    checkin_date = models.DateField()
    checkout_date = models.DateField()  # exclusive
    adults = models.PositiveSmallIntegerField(default=1)
    children = models.PositiveSmallIntegerField(default=0)
    children_ages = json_field(default=list)
    occupants = models.ManyToManyField(Guest, blank=True, related_name="stays")
    nightly_rates = json_field(default=list)  # [{"date": "2026-10-01", "amount": "350000.00"}]
    total_amount = money_field(default=0)
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.CONFIRMED)
    locked_room = models.BooleanField(default=False)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    # Created "from the group's allotment": it consumes the block's held units (pickup), see services.blocks.
    group_block = models.ForeignKey(
        GroupBlock, null=True, blank=True, on_delete=models.SET_NULL, related_name="stays"
    )

    class Meta:
        ordering = ["checkin_date", "created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(checkout_date__gt=F("checkin_date")), name="stay_dates_valid"),
            ExclusionConstraint(
                name="stay_no_room_overlap",
                expressions=[
                    (DateRangeFunc("checkin_date", "checkout_date", Value("[)")), RangeOperators.OVERLAPS),
                    ("room", RangeOperators.EQUAL),
                ],
                condition=Q(status__in=ACTIVE_STAY_STATUSES, room__isnull=False, bed__isnull=True),
            ),
            ExclusionConstraint(
                name="stay_no_bed_overlap",
                expressions=[
                    (DateRangeFunc("checkin_date", "checkout_date", Value("[)")), RangeOperators.OVERLAPS),
                    ("bed", RangeOperators.EQUAL),
                ],
                condition=Q(status__in=ACTIVE_STAY_STATUSES, bed__isnull=False),
            ),
        ]
        indexes = [
            models.Index(fields=["room_type", "checkin_date", "checkout_date"], name="stay_type_range_idx"),
            models.Index(fields=["room", "checkin_date"], name="stay_room_checkin_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.reservation.code} · {self.checkin_date}→{self.checkout_date}"

    @property
    def nights(self) -> list:
        return nights(self.checkin_date, self.checkout_date)


UNIT_COUNTERS = ("total_units", "sold_units", "blocked_units", "held_units")


class InventoryDayQuerySet(models.QuerySet):
    def only(self, *fields):
        """`available` needs the four unit counters: a query that loads some of them (e.g. the rate grid's
        `.only("room_type_id", "date", "total_units", "sold_units", "blocked_units")`, written before
        `held_units` existed) loads them all, instead of one extra query per row for the deferred one."""
        if any(name in UNIT_COUNTERS for name in fields):
            fields = (*fields, *(name for name in UNIT_COUNTERS if name not in fields))
        return super().only(*fields)


class InventoryDay(BaseModel):
    """Materialized availability per category and night (units = rooms, or beds for dorms).

    `blocked_units` are units out of order (room blocks: they leave the sellable inventory, and occupancy);
    `held_units` are units held for group allotments not picked up yet (`GroupBlock`): not sellable to anyone
    else, but still part of the inventory for occupancy figures."""

    objects = InventoryDayQuerySet.as_manager()

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="inventory_days")
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name="inventory_days")
    date = models.DateField()
    total_units = models.PositiveIntegerField(default=0)
    sold_units = models.PositiveIntegerField(default=0)
    blocked_units = models.PositiveIntegerField(default=0)
    held_units = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["date"]
        constraints = [models.UniqueConstraint(fields=["room_type", "date"], name="inventory_day_unique")]
        indexes = [models.Index(fields=["property", "date"], name="inventory_day_prop_date_idx")]

    def __str__(self) -> str:
        return f"{self.room_type} {self.date}: {self.available}"

    @builtins.property  # the `property` FK shadows the builtin inside the class body
    def available(self) -> int:
        """May be negative when the category is overbooked."""
        return self.total_units - self.sold_units - self.blocked_units - self.held_units
