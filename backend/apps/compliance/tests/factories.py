"""Compliance factories and builders for folios ready to invoice."""

from datetime import timedelta
from decimal import Decimal

import factory
from django.utils import timezone

from apps.bookings.tests.factories import ReservationFactory
from apps.compliance.models import ComplianceSettings, Invoice, InvoiceResolution
from apps.core.tests.factories import PropertyFactory
from apps.finance.tests.factories import FolioFactory

LODGING_LINE = {
    "code": "ALOJ-DBL",
    "kind": "room",
    "description": "Alojamiento Estándar · 2 noches",
    "quantity": 2,
    "unit_price": "320000.00",
    "net": "640000.00",
    "tax_code": "01",
    "tax_status": "taxed",
    "tax_rate": "19.00",
    "tax_amount": "121600.00",
    "total": "761600.00",
    "charge_ids": [],
}
PERSON_CUSTOMER = {
    "guest_id": None,
    "email": "laura@example.com",
    "phone": "+573001234567",
    "is_foreign_non_resident": False,
    "is_final_consumer": False,
    "name": "Laura Gómez",
    "document_type": "CC",
    "dian_document_code": "13",
    "document_number": "52123456",
    "dv": "",
    "legal_organization": "person",
    "address": "Cra 7 # 12-34",
    "city": "Bogotá",
    "country": "CO",
    "nationality": "CO",
}


class InvoiceResolutionFactory(factory.django.DjangoModelFactory):
    """Active DIAN test resolution SETT 1–5000, valid from a year ago to a year from the property's date."""

    class Meta:
        model = InvoiceResolution

    property = factory.SubFactory(PropertyFactory)
    document_kind = InvoiceResolution.DocumentKind.INVOICE
    prefix = "SETT"
    resolution_number = "18760000001"
    from_number = 1
    to_number = 5000
    current_number = 0
    valid_from = factory.LazyAttribute(lambda o: o.property.business_date - timedelta(days=365))
    valid_to = factory.LazyAttribute(lambda o: o.property.business_date + timedelta(days=365))
    technical_key = "fc8eac422eba16e22ffd8c6f94b3f40a6e38162c"
    environment = InvoiceResolution.Environment.TEST
    is_active = True


class ComplianceSettingsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ComplianceSettings
        django_get_or_create = ("property",)

    property = factory.SubFactory(PropertyFactory)
    sire_establishment_code = "123456"
    sire_city_code = "13001"


def post(
    folio,
    *,
    kind,
    amount,
    description,
    quantity=1,
    tax=None,
    tax_amount=Decimal("0"),
    stay=None,
    night_date=None,
    extra=None,
    business_date=None,
):
    """A charge written directly (tests control every number; `amount` is the net unit price)."""
    from apps.finance.models import Charge

    unit = Decimal(amount)
    return Charge.objects.create(
        folio=folio,
        business_date=business_date or folio.property.business_date,
        kind=kind,
        description=description,
        quantity=quantity,
        unit_price=unit,
        amount=unit * quantity,
        tax=tax,
        tax_amount=Decimal(tax_amount),
        stay=stay,
        night_date=night_date,
        extra=extra,
        source="user",
    )


class InvoiceFactory(factory.django.DjangoModelFactory):
    """An accepted simulated invoice SETT<n> for 2 nights × 320.000 + IVA (lines and totals hand-written)."""

    class Meta:
        model = Invoice

    property = factory.SubFactory(PropertyFactory)
    folio = factory.LazyAttribute(lambda o: FolioFactory(reservation=ReservationFactory(property=o.property)))
    reservation = factory.LazyAttribute(lambda o: o.folio.reservation)
    kind = Invoice.Kind.INVOICE
    status = Invoice.Status.ACCEPTED
    number = factory.Sequence(lambda n: n + 1)
    prefix = "SETT"
    full_number = factory.LazyAttribute(lambda o: f"{o.prefix}{o.number}")
    issue_date = factory.LazyAttribute(lambda o: o.property.business_date)
    issued_at = factory.LazyFunction(timezone.now)
    customer = factory.LazyFunction(lambda: dict(PERSON_CUSTOMER))
    lines = factory.LazyFunction(lambda: [dict(LODGING_LINE)])
    subtotal = Decimal("640000")
    tax_total = Decimal("121600")
    total = Decimal("761600")
    cufe = "9f" * 48
    qr_data = "NumFac=SETT1"
    mode = "simulated"
    environment = "test"
