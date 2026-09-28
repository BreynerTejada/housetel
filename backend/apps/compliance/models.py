"""Legal Colombia (spec §5 C7): DIAN electronic invoicing, SIRE (Migración Colombia) and TRA (MinCIT).

- Invoice numbers come from an `InvoiceResolution` (DIAN numbering authorization) locked with
  `select_for_update`; `current_number` is the last number handed out (0 = none yet).
- Legal files (PDF/XML/SIRE TXT) live in a private storage (apps/compliance/storage.py).
- Invoices, SIRE records and TRA registrations are kept even when a guest is anonymized: the law requires
  their retention (see docs/integration-notes/C7-compliance.md).
"""

import builtins

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.bookings.models import Reservation, Stay
from apps.compliance.storage import ComplianceStorage, invoice_upload_to, sire_upload_to
from apps.core.fields import json_field, money_field
from apps.core.models import BaseModel, Property
from apps.finance.models import Charge, Folio
from apps.guests.models import Guest

FINAL_CONSUMER_ID = "222222222222"  # DIAN "consumidor final"


class IntegrationMode(models.TextChoices):
    REAL = "real", "Real"
    SIMULATED = "simulated", "Simulado"


class ComplianceSettings(BaseModel):
    """Per-property legal configuration. Created on first use with the defaults below."""

    property = models.OneToOneField(Property, on_delete=models.CASCADE, related_name="compliance_settings")
    # Movements (check-outs to invoice, check-ins to register, SIRE days) before this date are not expected in
    # Housetel (the hotel reported them elsewhere): they never show up as pending. Null = no limit.
    go_live_date = models.DateField(null=True, blank=True)
    # DIAN
    auto_issue_invoices = models.BooleanField(default=True)  # issue when the last stay checks out
    final_consumer_id = models.CharField(max_length=20, default=FINAL_CONSUMER_ID)
    invoice_notes = models.TextField(blank=True)  # printed at the bottom of the invoice PDF
    # SIRE (Migración Colombia)
    sire_establishment_code = models.CharField(max_length=20, blank=True)
    sire_city_code = models.CharField(max_length=10, blank=True)  # DIVIPOLA; empty → from Property.city
    sire_document_codes = json_field()  # overrides of SIRE_DOCUMENT_TYPES: {"PA": "3"}
    sire_country_codes = json_field()  # overrides of SIRE_COUNTRY_CODES: {"US": "249"}
    sire_second_surname_column = models.BooleanField(default=False)  # 13-column layout
    # TRA (MinCIT)
    tra_auto_register = models.BooleanField(default=True)  # register every guest at check-in
    tra_establishment_id = models.CharField(max_length=30, blank=True)  # RNT; empty → Property.rnt_number
    tra_travel_reason = models.CharField(max_length=80, default="Vacaciones, recreo y ocio")
    tra_accommodation_type = models.CharField(max_length=60, blank=True)  # empty → from property_type

    class Meta:
        verbose_name_plural = "compliance settings"

    def __str__(self) -> str:
        return f"Legal · {self.property}"


class InvoiceResolution(BaseModel):
    """DIAN numbering authorization (prefix + range + validity). One active per document kind."""

    class DocumentKind(models.TextChoices):
        INVOICE = "invoice", "Factura"
        CREDIT_NOTE = "credit_note", "Nota crédito"

    class Environment(models.TextChoices):
        TEST = "test", "Pruebas (habilitación)"
        PRODUCTION = "production", "Producción"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="invoice_resolutions")
    document_kind = models.CharField(
        max_length=20, choices=DocumentKind.choices, default=DocumentKind.INVOICE
    )
    prefix = models.CharField(max_length=10, blank=True)
    resolution_number = models.CharField(max_length=40, blank=True)
    from_number = models.PositiveBigIntegerField()
    to_number = models.PositiveBigIntegerField()
    current_number = models.PositiveBigIntegerField(default=0)  # last number handed out; 0 = none yet
    valid_from = models.DateField()
    valid_to = models.DateField()
    technical_key = models.CharField(max_length=128, blank=True)  # "clave técnica" (CUFE input)
    environment = models.CharField(max_length=20, choices=Environment.choices, default=Environment.TEST)
    provider_range_id = models.CharField(max_length=40, blank=True)  # e.g. Factus numbering_range_id
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["document_kind", "-is_active", "-valid_from"]
        constraints = [
            models.CheckConstraint(
                condition=Q(to_number__gte=F("from_number")), name="resolution_range_valid"
            ),
            models.CheckConstraint(condition=Q(valid_to__gte=F("valid_from")), name="resolution_dates_valid"),
            models.UniqueConstraint(
                fields=["property", "document_kind"],
                condition=Q(is_active=True),
                name="resolution_one_active_per_kind",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.prefix} {self.from_number}–{self.to_number}"

    @builtins.property  # the `property` FK shadows the builtin inside the class body
    def next_number(self) -> int:
        return max(self.current_number + 1, self.from_number)

    @builtins.property
    def remaining(self) -> int:
        return max(self.to_number - self.next_number + 1, 0)


class Invoice(BaseModel):
    """An electronic invoice or credit note. Amounts: `subtotal` (net) + `tax_total` = `total`."""

    class Kind(models.TextChoices):
        INVOICE = "invoice", "Factura"
        CREDIT_NOTE = "credit_note", "Nota crédito"

    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        ISSUED = "issued", "Emitida"  # received by the provider, DIAN validation pending
        ACCEPTED = "accepted", "Aceptada"  # validated by the DIAN
        REJECTED = "rejected", "Rechazada"
        CANCELLED = "cancelled", "Anulada"  # annulled by a credit note
        ERROR = "error", "Error"  # technical error; retried by compliance.issue_pending_invoices

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="invoices")
    reservation = models.ForeignKey(
        Reservation, null=True, blank=True, on_delete=models.RESTRICT, related_name="invoices"
    )
    folio = models.ForeignKey(Folio, on_delete=models.RESTRICT, related_name="invoices")
    resolution = models.ForeignKey(
        InvoiceResolution, null=True, blank=True, on_delete=models.RESTRICT, related_name="invoices"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.INVOICE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    number = models.PositiveBigIntegerField(null=True, blank=True)
    prefix = models.CharField(max_length=10, blank=True)
    full_number = models.CharField(max_length=40, blank=True)  # prefix + number (or the provider's number)
    issue_date = models.DateField()
    currency = models.CharField(max_length=3, default="COP")
    customer = json_field()
    lines = json_field(default=list)
    subtotal = money_field(default=0)
    tax_total = money_field(default=0)
    total = money_field(default=0)
    exempt_note = models.CharField(max_length=255, blank=True)
    cufe = models.CharField(max_length=128, blank=True)  # CUFE (invoice) / CUDE (credit note): SHA-384 hex
    qr_data = models.TextField(blank=True)
    xml_file = models.FileField(
        upload_to=invoice_upload_to, storage=ComplianceStorage(), blank=True, max_length=255
    )
    pdf_file = models.FileField(
        upload_to=invoice_upload_to, storage=ComplianceStorage(), blank=True, max_length=255
    )
    mode = models.CharField(max_length=10, choices=IntegrationMode.choices, default=IntegrationMode.SIMULATED)
    environment = models.CharField(
        max_length=20,
        choices=InvoiceResolution.Environment.choices,
        default=InvoiceResolution.Environment.TEST,
    )
    provider = models.CharField(max_length=30, blank=True)
    provider_ref = models.CharField(max_length=120, blank=True)
    provider_response = json_field()
    related_invoice = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.RESTRICT, related_name="credit_notes"
    )
    reason = models.TextField(blank=True)  # credit notes
    issued_at = models.DateTimeField(null=True, blank=True)
    # P4: invoices to a company with credit are "a crédito": due `payment_terms_days` after the issue date.
    due_date = models.DateField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    charges = models.ManyToManyField(Charge, blank=True, related_name="invoices")  # what an invoice covers

    class Meta:
        ordering = ["-issue_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["property", "kind", "prefix", "number"],
                condition=Q(number__isnull=False),
                name="invoice_number_unique",
            )
        ]
        indexes = [
            models.Index(fields=["property", "status"], name="invoice_property_status_idx"),
            models.Index(fields=["property", "-issue_date"], name="invoice_property_date_idx"),
        ]

    def __str__(self) -> str:
        return self.full_number or f"{self.get_kind_display()} (borrador)"


class SireReport(BaseModel):
    """A SIRE bulk-upload file (foreigners' check-ins E / check-outs S) for `[period_start, period_end]`."""

    class Status(models.TextChoices):
        GENERATED = "generated", "Generado"
        SUBMITTED = "submitted", "Reportado"
        ACKNOWLEDGED = "acknowledged", "Con acuse"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="sire_reports")
    period_start = models.DateField()
    period_end = models.DateField()  # inclusive
    file = models.FileField(upload_to=sire_upload_to, storage=ComplianceStorage(), blank=True, max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.GENERATED)
    records_count = models.PositiveIntegerField(default=0)  # complete rows written to the file
    missing = json_field(default=list)
    mode = models.CharField(max_length=10, choices=IntegrationMode.choices, default=IntegrationMode.SIMULATED)
    generated_at = models.DateTimeField(default=timezone.now)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    ack_code = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["-period_end", "-generated_at"]
        constraints = [
            models.CheckConstraint(condition=Q(period_end__gte=F("period_start")), name="sire_period_valid")
        ]

    def __str__(self) -> str:
        return f"SIRE {self.period_start}→{self.period_end} ({self.status})"


class SireRecord(BaseModel):
    """One movement of one foreign guest. Incomplete rows stay out of the file (see `missing_fields`)."""

    class Movement(models.TextChoices):
        ENTRY = "E", "Entrada"
        EXIT = "S", "Salida"

    report = models.ForeignKey(SireReport, on_delete=models.CASCADE, related_name="records")
    guest = models.ForeignKey(Guest, on_delete=models.RESTRICT, related_name="sire_records")
    stay = models.ForeignKey(Stay, on_delete=models.RESTRICT, related_name="sire_records")
    movement = models.CharField(max_length=1, choices=Movement.choices)
    movement_date = models.DateField()
    complete = models.BooleanField(default=True)
    missing_fields = json_field(default=list)
    data = json_field()  # the row by column key (see apps/compliance/services/sire.py)

    class Meta:
        ordering = ["movement_date", "movement", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["report", "stay", "guest", "movement"], name="sire_record_unique_movement"
            )
        ]

    def __str__(self) -> str:
        return f"{self.movement} {self.movement_date} · {self.guest}"


class TraRegistration(BaseModel):
    """TRA (Tarjeta de Registro Alojamiento) of one guest of one stay. Companions point to the main guest."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        REGISTERED = "registered", "Registrado"
        ERROR = "error", "Error"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="tra_registrations")
    reservation = models.ForeignKey(Reservation, on_delete=models.RESTRICT, related_name="tra_registrations")
    stay = models.ForeignKey(Stay, on_delete=models.RESTRICT, related_name="tra_registrations")
    guest = models.ForeignKey(Guest, on_delete=models.RESTRICT, related_name="tra_registrations")
    is_main = models.BooleanField(default=False)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="companions"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    tra_number = models.CharField(max_length=60, blank=True)
    mode = models.CharField(max_length=10, choices=IntegrationMode.choices, default=IntegrationMode.SIMULATED)
    payload = json_field()
    response = json_field()
    missing_fields = json_field(default=list)
    registered_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["stay", "guest"], name="tra_stay_guest_unique")]
        indexes = [models.Index(fields=["property", "status"], name="tra_property_status_idx")]

    def __str__(self) -> str:
        return f"TRA {self.guest} · {self.status}"
