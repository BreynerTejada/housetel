"""Channel manager (plan C3): connections to channels, their mappings, the ARI queue, the sync log, the link
between channel bookings and PMS reservations, and the data of the local OTA simulator.

Date ranges are half-open (`start` inclusive, `end` exclusive), like every range of the PMS.
"""

import secrets
from decimal import Decimal

from django.db import models
from django.db.models import Q

from apps.bookings.models import Reservation
from apps.core.fields import json_field, money_field
from apps.core.models import BaseModel, Property
from apps.inventory.models import Room, RoomType
from apps.rates.models import RatePlan


def new_export_token() -> str:
    """Secret of a public iCal export URL (unguessable, URL-safe)."""
    return secrets.token_urlsafe(24)


class ChannelConnection(BaseModel):
    """A property connected to one channel. BookSim, AirSim and Channex: at most one per property; iCal: one
    per listing site (Airbnb, VRBO…), each with its calendars in `room_mappings`."""

    class Channel(models.TextChoices):
        BOOKSIM = "booksim", "BookSim"
        AIRSIM = "airsim", "AirSim"
        ICAL = "ical", "iCal"
        CHANNEX = "channex", "Channex"

    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        PAUSED = "paused", "Pausada"
        ERROR = "error", "Con error"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="channel_connections")
    channel_code = models.CharField(max_length=20, choices=Channel.choices)
    name = models.CharField(max_length=120)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    settings = json_field()
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["name", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["property", "channel_code"],
                condition=~Q(channel_code="ical"),
                name="channel_connection_unique_per_property",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.channel_code})"


class RoomMapping(BaseModel):
    """A PMS category (or one room, for iCal calendars) ↔ the channel's room. iCal mappings carry the secret
    token of their export URL and, optionally, the URL of the remote calendar to import."""

    connection = models.ForeignKey(ChannelConnection, on_delete=models.CASCADE, related_name="room_mappings")
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name="channel_mappings")
    room = models.ForeignKey(
        Room, null=True, blank=True, on_delete=models.CASCADE, related_name="channel_mappings"
    )
    external_room_id = models.CharField(max_length=120, blank=True)
    ical_import_url = models.URLField(max_length=1000, blank=True)
    ical_export_token = models.CharField(max_length=64, unique=True, default=new_export_token)
    ical_last_sync_at = models.DateTimeField(null=True, blank=True)
    ical_last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["room_type__sort_order", "room_type__code", "room__number"]
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "room_type", "room"],
                nulls_distinct=False,
                name="room_mapping_unique_unit",
            ),
            models.UniqueConstraint(
                fields=["connection", "external_room_id"],
                condition=~Q(external_room_id=""),
                name="room_mapping_unique_external_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.room_type.code} ↔ {self.external_room_id or self.pk}"


class RateMapping(BaseModel):
    """A PMS rate plan ↔ the channel's rate, sold at the plan price × (1 + markup_percent/100).

    `room_type` null = the rate applies to every mapped category the plan sells (BookSim/AirSim); Channex rate
    plans belong to one room type, so there it is set. A deleted plan leaves `rate_plan` null: the channel
    rate is then pushed closed (stop-sell) until it is remapped or removed.
    """

    connection = models.ForeignKey(ChannelConnection, on_delete=models.CASCADE, related_name="rate_mappings")
    rate_plan = models.ForeignKey(
        RatePlan, null=True, blank=True, on_delete=models.SET_NULL, related_name="channel_mappings"
    )
    room_type = models.ForeignKey(
        RoomType, null=True, blank=True, on_delete=models.CASCADE, related_name="channel_rate_mappings"
    )
    external_rate_id = models.CharField(max_length=120, blank=True)
    markup_percent = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "rate_plan", "room_type"],
                nulls_distinct=False,
                condition=Q(rate_plan__isnull=False),
                name="rate_mapping_unique_plan",
            )
        ]

    def __str__(self) -> str:
        return f"{self.rate_plan_id} ↔ {self.external_rate_id}"


class AriUpdate(BaseModel):
    """Pending availability/rates/restrictions of one category for one connection. Signals coalesce into the
    pending row of (connection, category): its range grows to the union and `kinds` to the union of kinds.
    `sending` = claimed by a push in progress (never extended); `rate_plan` null = every mapped plan."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        SENDING = "sending", "Enviando"
        SENT = "sent", "Enviada"
        FAILED = "failed", "Fallida"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="ari_updates")
    connection = models.ForeignKey(ChannelConnection, on_delete=models.CASCADE, related_name="ari_updates")
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name="ari_updates")
    rate_plan = models.ForeignKey(
        RatePlan, null=True, blank=True, on_delete=models.SET_NULL, related_name="ari_updates"
    )
    start = models.DateField()
    end = models.DateField()  # exclusive
    kinds = json_field(default=list)  # "availability", "rates", "restrictions"
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    payload = json_field()
    response = json_field()
    last_error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="ari_update_due_idx"),
            models.Index(fields=["connection", "room_type", "status"], name="ari_update_coalesce_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.connection_id} · {self.room_type_id} {self.start}→{self.end} ({self.status})"


class SyncLog(BaseModel):
    """What went in (bookings, calendars) or out (ARI) of a connection, and how it ended."""

    class Direction(models.TextChoices):
        IN = "in", "Entrada"
        OUT = "out", "Salida"

    class Status(models.TextChoices):
        SUCCESS = "success", "Correcto"
        WARNING = "warning", "Advertencia"
        ERROR = "error", "Error"
        SKIPPED = "skipped", "Sin cambios"

    connection = models.ForeignKey(ChannelConnection, on_delete=models.CASCADE, related_name="logs")
    direction = models.CharField(max_length=3, choices=Direction.choices)
    kind = models.CharField(max_length=40)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUCCESS)
    message = models.TextField(blank=True)
    payload = json_field()
    external_id = models.CharField(max_length=120, blank=True)
    reservation = models.ForeignKey(
        Reservation, null=True, blank=True, on_delete=models.SET_NULL, related_name="channel_logs"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["connection", "-created_at"], name="sync_log_connection_idx")]

    def __str__(self) -> str:
        return f"{self.direction} {self.kind} · {self.status}"


class ExternalReservationMap(BaseModel):
    """The PMS reservation of a channel booking. `last_payload_hash` makes imports idempotent: the same
    booking payload received twice changes nothing."""

    connection = models.ForeignKey(
        ChannelConnection, on_delete=models.CASCADE, related_name="reservation_maps"
    )
    external_id = models.CharField(max_length=120)
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name="channel_maps")
    room_mapping = models.ForeignKey(
        RoomMapping, null=True, blank=True, on_delete=models.SET_NULL, related_name="reservation_maps"
    )
    last_payload_hash = models.CharField(max_length=64, blank=True)
    last_status = models.CharField(max_length=20, blank=True)  # new | modified | cancelled
    last_payload = json_field()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "external_id"], name="external_reservation_unique_per_connection"
            )
        ]

    def __str__(self) -> str:
        return f"{self.external_id} → {self.reservation_id}"


class SimOtaInventory(BaseModel):
    """What a simulated OTA (BookSim, AirSim, simulated Channex) holds after the ARI pushes: one row per
    channel room × channel rate × night."""

    connection = models.ForeignKey(ChannelConnection, on_delete=models.CASCADE, related_name="sim_inventory")
    external_room_id = models.CharField(max_length=120)
    external_rate_id = models.CharField(max_length=120)
    date = models.DateField()
    available = models.IntegerField(default=0)
    price = money_field(null=True, blank=True)
    min_los = models.PositiveSmallIntegerField(null=True, blank=True)
    max_los = models.PositiveSmallIntegerField(null=True, blank=True)
    closed_to_arrival = models.BooleanField(default=False)
    closed_to_departure = models.BooleanField(default=False)
    stop_sell = models.BooleanField(default=False)

    class Meta:
        ordering = ["external_room_id", "external_rate_id", "date"]
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "external_room_id", "external_rate_id", "date"],
                name="sim_ota_inventory_unique_cell",
            )
        ]
        indexes = [models.Index(fields=["connection", "date"], name="sim_ota_inventory_date_idx")]

    def __str__(self) -> str:
        return f"{self.external_room_id}/{self.external_rate_id} {self.date}"


class SimOtaBooking(BaseModel):
    """A booking made in a simulated OTA. BookSim/AirSim deliver it to the PMS at once (the OTA calls us);
    simulated Channex and iCal keep it until the PMS pulls (`pms_status` pending)."""

    class Status(models.TextChoices):
        NEW = "new", "Nueva"
        MODIFIED = "modified", "Modificada"
        CANCELLED = "cancelled", "Cancelada"

    class PmsStatus(models.TextChoices):
        PENDING = "pending", "Pendiente"
        IMPORTED = "imported", "Importada"
        FAILED = "failed", "Falló"

    connection = models.ForeignKey(ChannelConnection, on_delete=models.CASCADE, related_name="sim_bookings")
    external_id = models.CharField(max_length=40)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    payload = json_field()
    revision = models.PositiveIntegerField(default=1)
    pms_status = models.CharField(max_length=10, choices=PmsStatus.choices, default=PmsStatus.PENDING)
    pms_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["connection", "external_id"], name="sim_ota_booking_unique")
        ]

    def __str__(self) -> str:
        return f"{self.external_id} ({self.status})"
