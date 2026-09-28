"""Corporate clients and receivables (pilot plan, task P4).

- `Company`: a customer company of the organization (corporate account, travel agency, public entity) with
  its DIAN identity (NIT + DV, VAT responsibility, fiscal responsibilities) and its credit terms.
- `ReservationBilling`: who a reservation is billed to and which kinds of charges go to the company folio
  (routing rules). No row = billed to the guest.
- `AccountPayment` + `AccountPaymentAllocation`: money a company pays "a cuenta"; every allocation is a
  finance `Payment` recorded on one of its company folios (the folio balances stay the single source of
  truth). What is not allocated is the company's credit (saldo a favor) until someone applies it.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.fields import json_field, money_field
from apps.core.models import BaseModel, Organization, Property

# DIAN fiscal responsibilities (anexo técnico de factura electrónica, tabla 13.2.6.1).
TAX_RESPONSIBILITIES = {
    "O-13": "Gran contribuyente",
    "O-15": "Autorretenedor",
    "O-23": "Agente de retención IVA",
    "O-47": "Régimen simple de tributación",
    "R-99-PN": "No aplica – Otros",
}


class Company(BaseModel):
    class Kind(models.TextChoices):
        CORPORATE = "corporate", "Corporativo"
        TRAVEL_AGENCY = "travel_agency", "Agencia de viajes"
        GOVERNMENT = "government", "Entidad pública"
        OTHER = "other", "Otro"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="companies")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.CORPORATE)
    legal_name = models.CharField(max_length=200)  # razón social
    trade_name = models.CharField(max_length=200, blank=True)  # nombre comercial
    nit = models.CharField(max_length=15)  # digits only, without the check digit
    dv = models.CharField(max_length=1)  # dígito de verificación (validated against the NIT)
    vat_responsible = models.BooleanField(default=True)  # responsable de IVA (48) / no responsable (49)
    tax_responsibilities = json_field(default=list)  # DIAN codes, see TAX_RESPONSIBILITIES
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=2, default="CO")
    billing_email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    credit_enabled = models.BooleanField(default=False)
    credit_limit = money_field(null=True, blank=True)  # cupo; null = no limit
    payment_terms_days = models.PositiveSmallIntegerField(default=30)  # plazo
    contacts = json_field(default=list)  # [{"name", "role", "email", "phone"}]
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["legal_name"]
        verbose_name_plural = "companies"
        constraints = [
            models.UniqueConstraint(fields=["organization", "nit"], name="company_org_nit_unique"),
        ]
        indexes = [models.Index(fields=["organization", "is_active"], name="company_org_active_idx")]

    def __str__(self) -> str:
        return self.legal_name

    @property
    def display_name(self) -> str:
        return self.trade_name or self.legal_name


class ReservationBilling(BaseModel):
    """Billing of one reservation. With `bill_to=company`, charges whose category is in `routing` go to the
    company folio (`corporate.services.target_folio`); everything else stays on the guest folio."""

    class BillTo(models.TextChoices):
        GUEST = "guest", "Huésped"
        COMPANY = "company", "Empresa"

    class Route(models.TextChoices):
        LODGING = "lodging", "Alojamiento"  # room nights (with their IVA) and cancellation / no-show fees
        LODGING_TAXES = "lodging_taxes", "Impuestos y tasas del alojamiento"  # `tax` charges posted apart
        EXTRAS = "extras", "Extras y consumos"  # extras, fees, other
        ALL = "all", "Todo"  # every charge, adjustments included

    reservation = models.OneToOneField(
        "bookings.Reservation", on_delete=models.CASCADE, related_name="billing"
    )
    bill_to = models.CharField(max_length=10, choices=BillTo.choices, default=BillTo.GUEST)
    company = models.ForeignKey(
        Company, null=True, blank=True, on_delete=models.PROTECT, related_name="reservation_billings"
    )
    routing = json_field(default=list)  # subset of Route values
    purchase_order = models.CharField(max_length=60, blank=True)  # orden de compra / voucher de la agencia
    notes = models.TextField(blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(bill_to="guest") | Q(company__isnull=False), name="billing_company_required"
            )
        ]

    def __str__(self) -> str:
        return f"Facturación {self.reservation_id}: {self.bill_to}"


class AccountPayment(BaseModel):
    """A payment a company made "a cuenta" at one property (usually a bank transfer)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Vigente"
        VOIDED = "voided", "Anulado"

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="account_payments")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="account_payments")
    amount = money_field()
    method = models.CharField(max_length=20)  # finance Payment.Method (manual methods)
    reference = models.CharField(max_length=120, blank=True)
    received_on = models.DateField()
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    void_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-received_on", "-created_at"]
        indexes = [models.Index(fields=["company", "property"], name="account_payment_company_idx")]

    def __str__(self) -> str:
        return f"Pago a cuenta {self.company} {self.amount}"


class AccountPaymentAllocation(BaseModel):
    """The part of an account payment applied to one company folio (= one finance Payment on that folio)."""

    account_payment = models.ForeignKey(AccountPayment, on_delete=models.CASCADE, related_name="allocations")
    folio = models.ForeignKey("finance.Folio", on_delete=models.PROTECT, related_name="account_allocations")
    payment = models.OneToOneField(
        "finance.Payment", on_delete=models.PROTECT, related_name="account_allocation"
    )
    amount = money_field()

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Aplicación {self.amount} → {self.folio_id}"
