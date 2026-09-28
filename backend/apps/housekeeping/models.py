"""Housekeeping and maintenance (spec §5 C2, plan Task C2).

- `HousekeepingSettings`: per-property rules (stayover frequency, optional inspection, auto-assignment).
- `HousekeepingTask`: one cleaning / inspection job on a room (or a dorm bed) for a business date. A room has
  at most one open departure/stayover clean (database constraint), so receivers can never duplicate it.
- `MaintenanceTicket` (+ `TicketPhoto`): a reported problem; when it makes the room unusable it holds a
  `RoomBlock` (created and released through the inventory contracts).
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel, Property
from apps.housekeeping.storage import PrivateMediaStorage, ticket_photo_upload_to
from apps.inventory.models import Bed, Room, RoomBlock

USER_MODEL = settings.AUTH_USER_MODEL


class Priority(models.TextChoices):
    LOW = "low", "Baja"
    NORMAL = "normal", "Normal"
    HIGH = "high", "Alta"
    URGENT = "urgent", "Urgente"


PRIORITY_RANK = {Priority.LOW: 0, Priority.NORMAL: 1, Priority.HIGH: 2, Priority.URGENT: 3}


class HousekeepingSettings(BaseModel):
    property = models.OneToOneField(Property, on_delete=models.CASCADE, related_name="housekeeping_settings")
    # Stayover service every N days of the stay (1 = daily); 0 = no stayover service.
    stayover_frequency_days = models.PositiveSmallIntegerField(default=1, validators=[MaxValueValidator(30)])
    require_inspection = models.BooleanField(default=False)
    auto_assign = models.BooleanField(default=True)
    minutes_per_shift = models.PositiveSmallIntegerField(
        default=420, validators=[MinValueValidator(60), MaxValueValidator(900)]
    )

    class Meta:
        verbose_name_plural = "housekeeping settings"

    def __str__(self) -> str:
        return f"Housekeeping · {self.property}"


class HousekeepingTask(BaseModel):
    class Kind(models.TextChoices):
        DEPARTURE_CLEAN = "departure_clean", "Limpieza de salida"
        STAYOVER = "stayover", "Repaso"
        DEEP_CLEAN = "deep_clean", "Limpieza profunda"
        INSPECTION = "inspection", "Inspección"
        TURNDOWN = "turndown", "Cobertura nocturna"
        CUSTOM = "custom", "Otra tarea"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        IN_PROGRESS = "in_progress", "En curso"
        DONE = "done", "Terminada"
        INSPECTED = "inspected", "Inspeccionada"
        CANCELLED = "cancelled", "Cancelada"

    class Source(models.TextChoices):
        CHECKOUT = "checkout", "Check-out"
        STATUS_CHANGE = "status_change", "Habitación marcada sucia"
        DAILY = "daily", "Generación diaria"
        INSPECTION = "inspection", "Inspección"
        MANUAL = "manual", "Manual"
        SEED = "seed", "Datos de demostración"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="housekeeping_tasks")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="housekeeping_tasks")
    bed = models.ForeignKey(
        Bed, null=True, blank=True, on_delete=models.CASCADE, related_name="housekeeping_tasks"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    business_date = models.DateField()
    assigned_to = models.ForeignKey(
        USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="housekeeping_tasks"
    )
    estimated_minutes = models.PositiveSmallIntegerField(default=30)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    finished_by = models.ForeignKey(
        USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    notes = models.TextField(blank=True)
    reservation = models.ForeignKey(
        "bookings.Reservation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="housekeeping_tasks",
    )
    created_source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)

    class Meta:
        ordering = ["business_date", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["room"],
                condition=Q(status__in=["pending", "in_progress"], kind__in=["departure_clean", "stayover"]),
                name="hk_one_open_turnover_per_room",
            )
        ]
        indexes = [
            models.Index(fields=["property", "business_date"], name="hk_task_property_date_idx"),
            models.Index(fields=["assigned_to", "business_date"], name="hk_task_assignee_date_idx"),
            models.Index(fields=["room", "status"], name="hk_task_room_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} · {self.room} · {self.business_date}"


class MaintenanceTicket(BaseModel):
    class Status(models.TextChoices):
        OPEN = "open", "Abierto"
        IN_PROGRESS = "in_progress", "En curso"
        RESOLVED = "resolved", "Resuelto"
        CANCELLED = "cancelled", "Cancelado"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="maintenance_tickets")
    room = models.ForeignKey(
        Room, null=True, blank=True, on_delete=models.SET_NULL, related_name="maintenance_tickets"
    )
    location = models.CharField(max_length=120, blank=True)  # common areas (no room): "Piscina", "Pasillo 2"
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    blocks_room = models.BooleanField(default=False)
    blocked_until = models.DateField(null=True, blank=True)  # exclusive end of the block
    block = models.ForeignKey(RoomBlock, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    room_status_before = models.CharField(max_length=20, blank=True)  # restored if the ticket is cancelled
    reported_by = models.ForeignKey(
        USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    assigned_to = models.ForeignKey(
        USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="maintenance_tickets"
    )
    started_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    resolution_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["property", "status"], name="hk_ticket_property_status_idx")]

    def __str__(self) -> str:
        return self.title


class TicketPhoto(BaseModel):
    ticket = models.ForeignKey(MaintenanceTicket, on_delete=models.CASCADE, related_name="photos")
    # Private: outside MEDIA_ROOT, no public URL (apps/housekeeping/storage.py).
    image = models.FileField(upload_to=ticket_photo_upload_to, storage=PrivateMediaStorage(), max_length=255)
    content_type = models.CharField(max_length=50)
    size = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return self.image.name
