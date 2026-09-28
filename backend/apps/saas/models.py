"""SaaS models (task C11): plans, subscriptions, platform invoices and marketplace commissions.

Date conventions:
- `Subscription.current_period_start/end` are semi-open `[start, end)`; `current_period_end` = renewal date.
- `PlatformInvoice.period_start/end` and `CommissionSettlement.period_start/end` are **inclusive** (they are
  documents people read: "1 sep – 30 sep").
"""

from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.fields import i18n_field, json_field, money_field
from apps.core.models import BaseModel, Organization, Property


class Plan(BaseModel):
    """A Housetel plan. Every feature is included; plans only differ by size (units / properties)."""

    code = models.SlugField(max_length=40, unique=True)
    name = i18n_field()
    description = i18n_field()
    max_units = models.PositiveIntegerField(null=True, blank=True)  # null = unlimited
    max_properties = models.PositiveIntegerField(null=True, blank=True)  # null = unlimited
    price_monthly = money_field()
    price_yearly = money_field()
    is_active = models.BooleanField(default=True)
    sort = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort", "price_monthly"]

    def __str__(self) -> str:
        return self.code

    def price_for(self, cycle: str) -> Decimal:
        return self.price_yearly if cycle == Subscription.Cycle.YEARLY else self.price_monthly


class Subscription(BaseModel):
    class Status(models.TextChoices):
        TRIALING = "trialing", "En prueba"
        ACTIVE = "active", "Activa"
        PAST_DUE = "past_due", "En mora"
        SUSPENDED = "suspended", "Suspendida"
        CANCELLED = "cancelled", "Cancelada"

    class Cycle(models.TextChoices):
        MONTHLY = "monthly", "Mensual"
        YEARLY = "yearly", "Anual"

    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIALING)
    billing_cycle = models.CharField(max_length=10, choices=Cycle.choices, default=Cycle.MONTHLY)
    current_period_start = models.DateField(null=True, blank=True)
    current_period_end = models.DateField(null=True, blank=True)  # exclusive = next renewal date
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    # {"type": "card", "brand": "VISA", "last4": "4242", "exp_month": 12, "exp_year": 2030, "holder": "…",
    #  "simulated": true} or, in real mode, {"wompi_payment_source_id": 1234, …}
    payment_source = json_field()
    retries = models.PositiveSmallIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    past_due_since = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["organization__name"]

    def __str__(self) -> str:
        return f"{self.organization} · {self.plan.code} ({self.status})"

    @property
    def monthly_amount(self) -> Decimal:
        """Monthly-equivalent price (MRR contribution) of the current plan and cycle."""
        if self.billing_cycle == self.Cycle.YEARLY:
            return (self.plan.price_yearly / 12).quantize(Decimal("1"))
        return self.plan.price_monthly


class PlatformInvoice(BaseModel):
    """What Housetel charges an organization (subscription and/or marketplace commissions) + IVA 19 %."""

    class Kind(models.TextChoices):
        SUBSCRIPTION = "subscription", "Suscripción"
        COMMISSIONS = "commissions", "Comisiones"
        OTHER = "other", "Otro"

    class Status(models.TextChoices):
        OPEN = "open", "Abierta"
        PAID = "paid", "Pagada"
        VOID = "void", "Anulada"
        FAILED = "failed", "Cobro fallido"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="platform_invoices")
    number = models.CharField(max_length=30, unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.SUBSCRIPTION)
    period_start = models.DateField()
    period_end = models.DateField()  # inclusive
    # [{"kind": "plan"|"commission"|"adjustment", "description": {"es", "en"}, "quantity": 1,
    #   "unit_price": "349000.00", "amount": "349000.00", "property_id"?: "…", "settlement_id"?: "…"}]
    lines = json_field(default=list)
    currency = models.CharField(max_length=3, default="COP")
    subtotal = money_field(default=Decimal("0"))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("19.00"))
    tax = money_field(default=Decimal("0"))
    total = money_field(default=Decimal("0"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    issued_at = models.DateTimeField(default=timezone.now)
    due_date = models.DateField()
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=120, blank=True)
    payment_method = models.CharField(max_length=40, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    payment_payload = json_field()  # provider data (checkout reference, transaction id…)
    pdf = models.FileField(upload_to="platform-invoices/", blank=True)

    class Meta:
        ordering = ["-issued_at", "-number"]
        indexes = [models.Index(fields=["organization", "status"], name="saas_invoice_org_status_idx")]

    def __str__(self) -> str:
        return self.number


class CommissionSettlement(BaseModel):
    """Monthly settlement of an organization's marketplace commissions (one per organization and month)."""

    class Status(models.TextChoices):
        OPEN = "open", "Abierta"
        INVOICED = "invoiced", "Facturada"
        PAID = "paid", "Pagada"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="commission_settlements"
    )
    period_start = models.DateField()
    period_end = models.DateField()  # inclusive
    total = money_field(default=Decimal("0"))
    commissions_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    invoice = models.ForeignKey(
        PlatformInvoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="settlements"
    )

    class Meta:
        ordering = ["-period_start", "organization__name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "period_start"], name="saas_settlement_org_month")
        ]

    def __str__(self) -> str:
        return f"{self.organization} · {self.period_start:%Y-%m}"


class Commission(BaseModel):
    """Housetel's commission on a marketplace reservation (base = lodging net of taxes × commission rate).

    `accrual_date` decides the settlement month: the checkout date of a stay, or the cancellation date when
    the commission is recalculated over a cancellation / no-show fee."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        SETTLED = "settled", "Liquidada"
        REVERSED = "reversed", "Revertida"

    class Basis(models.TextChoices):
        STAY = "stay", "Alojamiento"
        FEE = "fee", "Penalidad"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="commissions")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="commissions")
    reservation = models.OneToOneField(
        "bookings.Reservation", on_delete=models.CASCADE, related_name="saas_commission"
    )
    basis = models.CharField(max_length=10, choices=Basis.choices, default=Basis.STAY)
    base_amount = money_field(default=Decimal("0"))
    rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("10.00"))
    amount = money_field(default=Decimal("0"))
    currency = models.CharField(max_length=3, default="COP")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    accrual_date = models.DateField()
    settlement = models.ForeignKey(
        CommissionSettlement, null=True, blank=True, on_delete=models.SET_NULL, related_name="commissions"
    )
    reversed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-accrual_date", "-created_at"]
        indexes = [
            models.Index(fields=["organization", "status", "accrual_date"], name="saas_comm_org_status_idx"),
            models.Index(fields=["accrual_date"], name="saas_comm_accrual_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.reservation_id} · {self.amount}"
