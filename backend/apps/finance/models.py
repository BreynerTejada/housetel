"""Finance (spec §4 + plan Global Constraints).

`Charge.amount` is NET; `Charge.tax_amount` goes apart; charge total = amount + tax_amount. Charges are never
deleted, only voided with a reason. Folio balance = Σ non-voided charges (amount + tax) − Σ approved payments
+ Σ approved refunds.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.bookings.models import Reservation, Stay
from apps.core.fields import json_field, money_field
from apps.core.models import BaseModel, Property
from apps.guests.models import Guest
from apps.rates.models import Extra, Tax


class Folio(BaseModel):
    class FolioType(models.TextChoices):
        GUEST = "guest", "Huésped"
        MASTER = "master", "Maestro"
        HOUSE = "house", "Casa"
        COMPANY = "company", "Empresa"  # P4: the company's part of a reservation, or an opening AR balance

    class Status(models.TextChoices):
        OPEN = "open", "Abierto"
        CLOSED = "closed", "Cerrado"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="folios")
    reservation = models.ForeignKey(
        Reservation, null=True, blank=True, on_delete=models.RESTRICT, related_name="folios"
    )
    stay = models.ForeignKey(Stay, null=True, blank=True, on_delete=models.RESTRICT, related_name="folios")
    guest = models.ForeignKey(Guest, null=True, blank=True, on_delete=models.SET_NULL, related_name="folios")
    # P4: company folios (`folio_type=company`) belong to a corporate client; they are its receivables.
    company = models.ForeignKey(
        "corporate.Company", null=True, blank=True, on_delete=models.PROTECT, related_name="folios"
    )
    folio_type = models.CharField(max_length=10, choices=FolioType.choices, default=FolioType.GUEST)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    currency = models.CharField(max_length=3, default="COP")
    closed_at = models.DateTimeField(null=True, blank=True)
    # P4: a free label for folios without reservation (e.g. the legacy invoice number of an opening balance).
    label = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["property", "status"], name="folio_property_status_idx"),
            models.Index(fields=["company", "status"], name="folio_company_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(folio_type="company") | Q(company__isnull=False), name="folio_company_required"
            ),
            models.UniqueConstraint(
                fields=["reservation", "company"],
                condition=Q(folio_type="company", reservation__isnull=False),
                name="folio_one_company_folio_per_reservation",
            ),
        ]

    def __str__(self) -> str:
        return f"Folio {self.reservation.code if self.reservation else self.folio_type} ({self.status})"


class Charge(BaseModel):
    class Kind(models.TextChoices):
        ROOM = "room", "Alojamiento"
        EXTRA = "extra", "Extra"
        TAX = "tax", "Impuesto"
        FEE = "fee", "Cargo"
        CANCELLATION_FEE = "cancellation_fee", "Penalidad de cancelación"
        ADJUSTMENT = "adjustment", "Ajuste"
        OTHER = "other", "Otro"

    folio = models.ForeignKey(Folio, on_delete=models.CASCADE, related_name="charges")
    business_date = models.DateField()
    kind = models.CharField(max_length=20, choices=Kind.choices)
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = money_field()  # net, per unit
    amount = money_field()  # net total = unit_price × quantity
    tax = models.ForeignKey(Tax, null=True, blank=True, on_delete=models.SET_NULL, related_name="charges")
    tax_amount = money_field(default=0)  # 0 with `tax` set = exempt (e.g. foreign non-resident)
    stay = models.ForeignKey(Stay, null=True, blank=True, on_delete=models.SET_NULL, related_name="charges")
    night_date = models.DateField(null=True, blank=True)
    extra = models.ForeignKey(Extra, null=True, blank=True, on_delete=models.SET_NULL, related_name="charges")
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    source = models.CharField(
        max_length=20, default="user"
    )  # user | automation | channel | guest | ai | system
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    void_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["business_date", "created_at"]
        indexes = [
            models.Index(fields=["folio", "kind"], name="charge_folio_kind_idx"),
            models.Index(fields=["stay", "night_date"], name="charge_stay_night_idx"),
            models.Index(fields=["business_date"], name="charge_business_date_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.description}: {self.total}"

    @property
    def total(self):
        return self.amount + self.tax_amount

    @property
    def is_voided(self) -> bool:
        return self.voided_at is not None


class Payment(BaseModel):
    class Method(models.TextChoices):
        CASH = "cash", "Efectivo"
        CARD_TERMINAL = "card_terminal", "Datáfono"
        BANK_TRANSFER = "bank_transfer", "Transferencia"
        WOMPI_CARD = "wompi_card", "Wompi · tarjeta"
        WOMPI_PSE = "wompi_pse", "Wompi · PSE"
        WOMPI_NEQUI = "wompi_nequi", "Wompi · Nequi"
        WOMPI_OTHER = "wompi_other", "Wompi · otro"
        OTA_COLLECT = "ota_collect", "Cobrado por la OTA"
        OTHER = "other", "Otro"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobado"
        DECLINED = "declined", "Rechazado"
        VOIDED = "voided", "Anulado"
        ERROR = "error", "Error"

    folio = models.ForeignKey(Folio, on_delete=models.CASCADE, related_name="payments")
    amount = money_field()
    method = models.CharField(max_length=20, choices=Method.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    provider = models.CharField(max_length=30, default="manual")
    provider_reference = models.CharField(max_length=120, blank=True)
    provider_payload = json_field()
    business_date = models.DateField()
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    notes = models.TextField(blank=True)
    # B4 additions. An online payment belongs to exactly one PaymentIntent (idempotent sync); manual payments
    # taken while the user has an open cash shift are linked to it (shift totals / expected cash).
    intent = models.OneToOneField(
        "PaymentIntent", null=True, blank=True, on_delete=models.SET_NULL, related_name="payment"
    )
    cash_shift = models.ForeignKey(
        "CashShift", null=True, blank=True, on_delete=models.SET_NULL, related_name="payments"
    )
    voided_at = models.DateTimeField(null=True, blank=True)  # manual payment recorded by mistake
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    void_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["provider", "provider_reference"], name="payment_provider_ref_idx")]
        constraints = [
            # A provider transaction is recorded once (manual references are free text and may repeat).
            models.UniqueConstraint(
                fields=["provider", "provider_reference"],
                condition=~Q(provider="manual") & ~Q(provider_reference=""),
                name="payment_provider_reference_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.method} {self.amount} ({self.status})"


class Refund(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobado"
        FAILED = "failed", "Fallido"

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="refunds")
    amount = money_field()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    provider_reference = models.CharField(max_length=120, blank=True)
    reason = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # B4 additions. `pending` refunds wait for a manual step (e.g. PSE/Nequi transfer back to the guest);
    # `instructions` says what to do and `completed_at` is set when they become approved/failed.
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    business_date = models.DateField(null=True, blank=True)
    cash_shift = models.ForeignKey(
        "CashShift", null=True, blank=True, on_delete=models.SET_NULL, related_name="refunds"
    )
    instructions = models.TextField(blank=True)
    provider_payload = json_field()
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Reembolso {self.amount} ({self.status})"


class PaymentIntent(BaseModel):
    class Mode(models.TextChoices):
        REAL = "real", "Real"
        SIMULATED = "simulated", "Simulado"

    class Status(models.TextChoices):
        CREATED = "created", "Creado"
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobado"
        DECLINED = "declined", "Rechazado"
        EXPIRED = "expired", "Expirado"
        ERROR = "error", "Error"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="payment_intents")
    folio = models.ForeignKey(Folio, on_delete=models.CASCADE, related_name="payment_intents")
    amount = money_field()
    currency = models.CharField(max_length=3, default="COP")
    provider = models.CharField(max_length=30)
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.SIMULATED)
    reference = models.CharField(max_length=64, unique=True)
    checkout_url = models.CharField(max_length=1000, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CREATED)
    expires_at = models.DateTimeField(null=True, blank=True)
    return_url = models.CharField(max_length=1000, blank=True)
    payload = json_field()
    # B4 additions: what the provider reported on the last active verification.
    provider_transaction_id = models.CharField(max_length=120, blank=True)
    method = models.CharField(max_length=20, blank=True)  # Payment.Method value once known
    status_message = models.CharField(max_length=255, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["property", "status"], name="intent_property_status_idx")]

    def __str__(self) -> str:
        return f"{self.reference} ({self.status})"


class CashShift(BaseModel):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="cash_shifts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cash_shifts")
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_float = money_field(default=0)
    expected_cash = money_field(null=True, blank=True)
    counted_cash = money_field(null=True, blank=True)
    difference = money_field(null=True, blank=True)
    notes = models.TextField(blank=True)
    # B4 additions: who closed it and the optional count by denomination ({"50000": 3, "2000": 5}).
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    denominations = json_field()

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["property", "user"],
                condition=Q(closed_at__isnull=True),
                name="cash_shift_one_open_per_user",
            )
        ]

    def __str__(self) -> str:
        return f"Caja {self.user} {self.opened_at:%Y-%m-%d %H:%M}"
