import uuid
from datetime import time
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.timezone import localdate, now

from apps.core.fields import i18n_field, json_field

USER_MODEL = settings.AUTH_USER_MODEL


class BaseModel(models.Model):
    """Abstract base of every business model: UUID primary key + timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Organization(BaseModel):
    """Tenant (a hotel company or a chain)."""

    class Status(models.TextChoices):
        TRIAL = "trial", "Prueba"
        ACTIVE = "active", "Activa"
        PAST_DUE = "past_due", "En mora"
        SUSPENDED = "suspended", "Suspendida"
        CANCELLED = "cancelled", "Cancelada"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    legal_name = models.CharField(max_length=200, blank=True)
    nit = models.CharField(max_length=30, blank=True)
    country = models.CharField(max_length=2, default="CO")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIAL)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    settings = json_field()

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Property(BaseModel):
    """A hotel / hostel. Every business table is scoped by property (or organization)."""

    class PropertyType(models.TextChoices):
        HOTEL = "hotel", "Hotel"
        HOSTEL = "hostel", "Hostal"
        BOUTIQUE = "boutique", "Hotel boutique"
        APARTHOTEL = "aparthotel", "Aparthotel"
        GLAMPING = "glamping", "Glamping"

    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        INACTIVE = "inactive", "Inactiva"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="properties")
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    property_type = models.CharField(max_length=20, choices=PropertyType.choices, default=PropertyType.HOTEL)
    description = i18n_field()
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=2, default="CO")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    timezone = models.CharField(max_length=64, default="America/Bogota")
    currency = models.CharField(max_length=3, default="COP")
    default_language = models.CharField(max_length=5, default="es")
    check_in_time = models.TimeField(default=time(15, 0))
    check_out_time = models.TimeField(default=time(12, 0))
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    rnt_number = models.CharField(max_length=30, blank=True)
    nit = models.CharField(max_length=30, blank=True)
    legal_name = models.CharField(max_length=200, blank=True)
    star_rating = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    house_rules = i18n_field()
    business_date = models.DateField(default=localdate)
    marketplace_listed = models.BooleanField(default=False)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("10.00"))
    branding = json_field()  # {"primary_color": "#B4583B", "logo": "<url>"}
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    settings = json_field()

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "properties"

    def __str__(self) -> str:
        return self.name


class AuditEvent(BaseModel):
    """Who did what. `organization` / `property` are null only for platform-level events."""

    class Source(models.TextChoices):
        USER = "user", "Usuario"
        AUTOMATION = "automation", "Automatización"
        AI = "ai", "IA"
        CHANNEL = "channel", "Canal"
        GUEST = "guest", "Huésped"
        SYSTEM = "system", "Sistema"
        API = "api", "API"

    organization = models.ForeignKey(
        Organization, null=True, blank=True, on_delete=models.CASCADE, related_name="audit_events"
    )
    property = models.ForeignKey(
        Property, null=True, blank=True, on_delete=models.CASCADE, related_name="audit_events"
    )
    actor = models.ForeignKey(USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actor_label = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.USER)
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    summary = models.TextField(blank=True)
    changes = json_field()
    reversible = models.BooleanField(default=False)
    undo_data = json_field()
    undone_at = models.DateTimeField(null=True, blank=True)
    undone_by = models.ForeignKey(
        USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    request_id = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["property", "-created_at"], name="audit_property_created_idx"),
            models.Index(fields=["organization", "-created_at"], name="audit_org_created_idx"),
            models.Index(fields=["target_type", "target_id"], name="audit_target_idx"),
            models.Index(fields=["action"], name="audit_action_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} · {self.target_type}:{self.target_id}"


class Alert(BaseModel):
    """Operational alert. At most one open alert per (property, dedupe_key); property null = platform."""

    class Severity(models.TextChoices):
        INFO = "info", "Información"
        WARNING = "warning", "Advertencia"
        CRITICAL = "critical", "Crítica"

    property = models.ForeignKey(
        Property, null=True, blank=True, on_delete=models.CASCADE, related_name="alerts"
    )
    kind = models.CharField(max_length=64)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.INFO)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    link = models.CharField(max_length=500, blank=True)
    dedupe_key = models.CharField(max_length=200)
    source = models.CharField(max_length=50, default="system")
    data = json_field()
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["property", "dedupe_key"],
                condition=Q(resolved_at__isnull=True),
                nulls_distinct=False,
                name="alert_open_unique",
            )
        ]
        indexes = [models.Index(fields=["property", "resolved_at"], name="alert_property_resolved_idx")]

    def __str__(self) -> str:
        return f"[{self.severity}] {self.title}"


class IntegrationSetting(BaseModel):
    """Per-property (or platform, property null) configuration of an external integration."""

    class Kind(models.TextChoices):
        PAYMENTS = "payments", "Pagos"
        CHANNEL_ICAL = "channel_ical", "Canal iCal"
        CHANNEL_CHANNEX = "channel_channex", "Channex"
        EINVOICE = "einvoice", "Factura electrónica"
        SIRE = "sire", "SIRE"
        TRA = "tra", "TRA"
        EMAIL = "email", "Email"
        WHATSAPP = "whatsapp", "WhatsApp"
        LLM = "llm", "IA (LLM)"
        SAAS_BILLING = "saas_billing", "Cobro SaaS"

    class Mode(models.TextChoices):
        REAL = "real", "Real"
        SIMULATED = "simulated", "Simulado"

    class Status(models.TextChoices):
        UNKNOWN = "unknown", "Desconocido"
        OK = "ok", "OK"
        ERROR = "error", "Error"

    property = models.ForeignKey(
        Property, null=True, blank=True, on_delete=models.CASCADE, related_name="integration_settings"
    )
    kind = models.CharField(max_length=30, choices=Kind.choices)
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.SIMULATED)
    enabled = models.BooleanField(default=True)
    config = json_field()
    secrets_encrypted = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UNKNOWN)
    status_message = models.TextField(blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["kind"]
        constraints = [
            models.UniqueConstraint(
                fields=["property", "kind"], nulls_distinct=False, name="integration_setting_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.kind} ({self.mode})"


class AutomationSetting(BaseModel):
    """Per-property override of a registered automation (property null = platform scope)."""

    property = models.ForeignKey(
        Property, null=True, blank=True, on_delete=models.CASCADE, related_name="automation_settings"
    )
    code = models.CharField(max_length=100)
    enabled = models.BooleanField(default=True)
    params = json_field()

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["property", "code"], nulls_distinct=False, name="automation_setting_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.code} ({'on' if self.enabled else 'off'})"


class AutomationRun(BaseModel):
    """One execution of an automation (property null = platform scope)."""

    class Status(models.TextChoices):
        RUNNING = "running", "En ejecución"
        SUCCESS = "success", "Éxito"
        PARTIAL = "partial", "Parcial"
        FAILED = "failed", "Falló"
        SKIPPED = "skipped", "Omitida"

    property = models.ForeignKey(
        Property, null=True, blank=True, on_delete=models.CASCADE, related_name="automation_runs"
    )
    code = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(default=now)
    finished_at = models.DateTimeField(null=True, blank=True)
    summary = models.TextField(blank=True)
    details = json_field()
    triggered_by = models.ForeignKey(
        USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["property", "code", "-started_at"], name="automation_run_lookup_idx")]

    def __str__(self) -> str:
        return f"{self.code} · {self.status}"
