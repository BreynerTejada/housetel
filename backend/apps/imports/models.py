"""Data import from another PMS (pilot plan, task P5).

- `ImportJob`: one uploaded file (CSV/XLSX) of one kind (guests, reservations, room types or rooms) with its
  column mapping, value mapping (categories and rate plans), options, validation counts, progress and results.
- `ImportRow`: one data row of the file: the raw cells, the normalized values, the validation issues and the
  outcome of the dry-run and of the real run (what it created or updated).
- `ImportedRecord`: idempotency key (property, kind, source system, external id) → the Housetel object that a
  previous import created, so importing the same file again updates or skips instead of duplicating.

Everything Housetel creates goes through the contract services of each app (guests, bookings, finance,
inventory, rates); these models only keep the import's own bookkeeping.
"""

from django.conf import settings
from django.db import models

from apps.core.fields import json_field
from apps.core.models import BaseModel, Property


class ImportJob(BaseModel):
    class Kind(models.TextChoices):
        GUESTS = "guests", "Huéspedes"
        RESERVATIONS = "reservations", "Reservas"
        ROOM_TYPES = "room_types", "Categorías"
        ROOMS = "rooms", "Habitaciones"

    class Preset(models.TextChoices):
        GENERIC = "generic", "Genérico"
        CLOUDBEDS = "cloudbeds", "Export de Cloudbeds"

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Por mapear"
        VALIDATED = "validated", "Revisado"
        QUEUED = "queued", "En cola"
        RUNNING = "running", "En proceso"
        COMPLETED = "completed", "Completado"
        FAILED = "failed", "Falló"
        REVERTED = "reverted", "Revertido"

    class Phase(models.TextChoices):
        NONE = "", "—"
        DRY_RUN = "dry_run", "Simulación"
        RUN = "run", "Importación"
        REVERT = "revert", "Reversión"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="import_jobs")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    preset = models.CharField(max_length=20, choices=Preset.choices, default=Preset.GENERIC)
    # Idempotency namespace (slug of the label): the same external id from another system is another record.
    source_system = models.CharField(max_length=60)
    source_label = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADED)
    phase = models.CharField(max_length=20, choices=Phase.choices, blank=True, default="")
    filename = models.CharField(max_length=255)
    file_format = models.CharField(max_length=10)  # csv | xlsx
    file_size = models.PositiveIntegerField(default=0)
    sheet_name = models.CharField(max_length=100, blank=True)
    headers = json_field(default=list)  # column titles in file order
    mapping = json_field()  # {field code: column title}
    value_map = json_field()  # {"room_type": {"<file value>": "<uuid>" | ""}, "rate_plan": {...}}
    options = json_field()  # see apps.imports.catalog.DEFAULT_OPTIONS
    total_rows = models.PositiveIntegerField(default=0)
    counts = json_field()  # validation: {"valid", "warning", "error", "skip"}
    progress_done = models.PositiveIntegerField(default=0)
    progress_total = models.PositiveIntegerField(default=0)
    dry_run_at = models.DateTimeField(null=True, blank=True)
    dry_run_summary = json_field()
    summary = json_field()  # real run: outcome counts, affected dates and room types
    revert_summary = json_field()
    error = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # who launched the current/last dry-run, run or rollback (the actor of every audited change)
    run_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    queued_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    reverted_at = models.DateTimeField(null=True, blank=True)
    reverted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # Habeas Data retention: the file's cells were erased (automation `imports.purge_data`).
    data_purged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["property", "-created_at"], name="import_job_prop_created_idx")]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} · {self.filename}"


class ImportRow(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Sin revisar"
        VALID = "valid", "Lista"
        WARNING = "warning", "Con advertencias"
        ERROR = "error", "Con errores"
        SKIP = "skip", "Se omite"

    class DryOutcome(models.TextChoices):
        NONE = "", "—"
        CREATE = "create", "Se crearía"
        UPDATE = "update", "Se actualizaría"
        SKIP = "skip", "Se omitiría"
        FAIL = "fail", "Fallaría"

    class Outcome(models.TextChoices):
        NONE = "", "—"
        CREATED = "created", "Creado"
        UPDATED = "updated", "Actualizado"
        SKIPPED = "skipped", "Omitido"
        FAILED = "failed", "Con error"
        REVERTED = "reverted", "Revertido"

    job = models.ForeignKey(ImportJob, on_delete=models.CASCADE, related_name="rows")
    number = models.PositiveIntegerField()  # spreadsheet row (the header is row 1)
    raw = json_field()  # {column title: cell text}
    data = json_field()  # normalized values after validation
    external_id = models.CharField(max_length=200, blank=True)
    group_key = models.CharField(max_length=200, blank=True)  # rows of one multi-room reservation
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    issues = json_field(default=list)  # [{"level", "code", "field", "message": {"es", "en"}}]
    dry_outcome = models.CharField(max_length=10, choices=DryOutcome.choices, blank=True, default="")
    dry_message = json_field()  # {"code", "es", "en"}
    outcome = models.CharField(max_length=10, choices=Outcome.choices, blank=True, default="")
    outcome_message = json_field()  # {"code", "es", "en"}
    target_type = models.CharField(max_length=40, blank=True)
    target_id = models.UUIDField(null=True, blank=True)
    target_label = models.CharField(max_length=160, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    extra = json_field()  # e.g. {"payment_ids": [...], "guest_id": "..."}

    class Meta:
        ordering = ["number"]
        constraints = [models.UniqueConstraint(fields=["job", "number"], name="import_row_job_number_unique")]
        indexes = [
            models.Index(fields=["job", "status"], name="import_row_job_status_idx"),
            models.Index(fields=["job", "outcome"], name="import_row_job_outcome_idx"),
            models.Index(fields=["target_type", "target_id"], name="import_row_target_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.job_id} · fila {self.number}"


class ImportedRecord(BaseModel):
    """What an import created, by (property, kind, source system, external id)."""

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=20, choices=ImportJob.Kind.choices)
    source_system = models.CharField(max_length=60)
    external_id = models.CharField(max_length=200)
    target_type = models.CharField(max_length=40)
    target_id = models.UUIDField()
    job = models.ForeignKey(
        ImportJob, null=True, blank=True, on_delete=models.SET_NULL, related_name="records"
    )
    created_by_job = models.ForeignKey(
        ImportJob, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["property", "kind", "source_system", "external_id"], name="imported_record_unique"
            )
        ]
        indexes = [models.Index(fields=["target_type", "target_id"], name="imported_record_target_idx")]

    def __str__(self) -> str:
        return f"{self.kind}:{self.source_system}:{self.external_id}"
