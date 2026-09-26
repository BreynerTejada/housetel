from decimal import Decimal

import pytest

from apps.finance.models import Charge, Folio
from apps.finance.tests.factories import ChargeFactory, FolioFactory

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
