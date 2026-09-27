from datetime import timedelta
from decimal import Decimal

import factory
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.bookings.tests.factories import ReservationFactory
from apps.core.tests.factories import PropertyFactory
from apps.finance.models import CashShift, Charge, Folio, Payment, PaymentIntent, Refund


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


class RefundFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Refund

    payment = factory.SubFactory(PaymentFactory)
    amount = Decimal("10000")
    status = Refund.Status.APPROVED
    reason = "Reembolso de prueba"
    business_date = factory.LazyAttribute(lambda o: o.payment.folio.property.business_date)


class PaymentIntentFactory(factory.django.DjangoModelFactory):
    """A simulated payment link of a folio (status `created`)."""

    class Meta:
        model = PaymentIntent

    folio = factory.SubFactory(FolioFactory)
    property = factory.LazyAttribute(lambda o: o.folio.property)
    amount = Decimal("150000")
    currency = "COP"
    provider = "simulated"
    mode = PaymentIntent.Mode.SIMULATED
    reference = factory.Sequence(lambda n: f"HT-TEST{n:04d}-PAY")
    checkout_url = factory.LazyAttribute(lambda o: f"http://localhost:5173/sim/pay/{o.reference}")
    status = PaymentIntent.Status.CREATED
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(hours=24))


class CashShiftFactory(factory.django.DjangoModelFactory):
    """An open cash shift (closed_at null)."""

    class Meta:
        model = CashShift

    property = factory.SubFactory(PropertyFactory)
    user = factory.SubFactory(UserFactory)
    opening_float = Decimal("200000")
