from decimal import Decimal

import factory

from apps.bookings.tests.factories import ReservationFactory
from apps.core.tests.factories import PropertyFactory
from apps.finance.models import Charge, Folio, Payment


class FolioFactory(factory.django.DjangoModelFactory):
    """Guest folio of a reservation. For a house folio: `FolioFactory(reservation=None, property=prop)`."""

    class Meta:
        model = Folio

    reservation = factory.SubFactory(ReservationFactory)
    property = factory.LazyAttribute(lambda o: o.reservation.property if o.reservation else PropertyFactory())
    guest = factory.LazyAttribute(lambda o: o.reservation.booker if o.reservation else None)
    folio_type = Folio.FolioType.GUEST
    status = Folio.Status.OPEN
    currency = "COP"


class ChargeFactory(factory.django.DjangoModelFactory):
    """`amount` is net; `tax_amount` goes apart (total = amount + tax_amount)."""

    class Meta:
        model = Charge

    folio = factory.SubFactory(FolioFactory)
    business_date = factory.LazyAttribute(lambda o: o.folio.property.business_date)
    kind = Charge.Kind.EXTRA
    description = "Cargo de prueba"
    quantity = 1
    unit_price = Decimal("100000")
    amount = factory.LazyAttribute(lambda o: o.unit_price * o.quantity)
    tax_amount = Decimal("0")
    source = "user"


class PaymentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Payment

    folio = factory.SubFactory(FolioFactory)
    amount = Decimal("100000")
    method = Payment.Method.CASH
    status = Payment.Status.APPROVED
    provider = "manual"
    business_date = factory.LazyAttribute(lambda o: o.folio.property.business_date)
