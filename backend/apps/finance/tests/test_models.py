from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.tests.factories import PropertyFactory
from apps.finance.models import Charge, Folio, Payment
from apps.finance.tests.factories import (
    CashShiftFactory,
    ChargeFactory,
    FolioFactory,
    PaymentFactory,
    PaymentIntentFactory,
)

pytestmark = pytest.mark.django_db


def test_charge_total_is_net_amount_plus_tax():
    charge = Charge(amount=Decimal("294118"), tax_amount=Decimal("55882"))
    assert charge.total == Decimal("350000")


def test_charge_is_not_voided_by_default(prop):
    charge = ChargeFactory(folio__reservation__property=prop)
    assert charge.voided_at is None and charge.is_voided is False


def test_folio_defaults(prop):
    folio = Folio.objects.get(pk=FolioFactory(reservation__property=prop).pk)
    assert (folio.folio_type, folio.status, folio.currency, folio.closed_at) == ("guest", "open", "COP", None)
    assert folio.property == prop and folio.guest == folio.reservation.booker


class TestCashShiftConstraints:
    def test_a_user_has_at_most_one_open_shift_per_property(self, prop, owner):
        CashShiftFactory(property=prop, user=owner)
        with pytest.raises(IntegrityError), transaction.atomic():
            CashShiftFactory(property=prop, user=owner)

    def test_closed_shifts_and_other_properties_do_not_count(self, prop, owner):
        first = CashShiftFactory(property=prop, user=owner)
        first.closed_at = timezone.now()
        first.save()
        CashShiftFactory(property=prop, user=owner)  # a new open shift after closing
        CashShiftFactory(property=PropertyFactory(organization=prop.organization), user=owner)
        assert owner.cash_shifts.filter(closed_at__isnull=True).count() == 2


class TestPaymentConstraints:
    def test_provider_references_are_unique_per_provider(self, prop):
        folio = FolioFactory(reservation__property=prop)
        PaymentFactory(folio=folio, provider="wompi", provider_reference="1234-1610641025-49201")
        with pytest.raises(IntegrityError), transaction.atomic():
            PaymentFactory(folio=folio, provider="wompi", provider_reference="1234-1610641025-49201")

    def test_manual_and_blank_references_may_repeat(self, prop):
        folio = FolioFactory(reservation__property=prop)
        PaymentFactory(folio=folio, provider="manual", provider_reference="RECIBO-1")
        PaymentFactory(folio=folio, provider="manual", provider_reference="RECIBO-1")
        PaymentFactory(folio=folio, provider="simulated", provider_reference="")
        PaymentFactory(folio=folio, provider="simulated", provider_reference="")
        PaymentFactory(folio=folio, provider="simulated", provider_reference="SIM-1")
        PaymentFactory(folio=folio, provider="wompi", provider_reference="SIM-1")  # other provider
        assert Payment.objects.filter(folio=folio).count() == 6

    def test_an_intent_is_paid_by_at_most_one_payment(self, prop):
        intent = PaymentIntentFactory(folio__reservation__property=prop)
        PaymentFactory(folio=intent.folio, intent=intent, provider="simulated", provider_reference="SIM-A")
        with pytest.raises(IntegrityError), transaction.atomic():
            PaymentFactory(
                folio=intent.folio, intent=intent, provider="simulated", provider_reference="SIM-B"
            )
