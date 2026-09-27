"""`manage.py check_integrity`: read-only invariants of inventory and money across apps (B-INT; the phase
integrations re-run it after the full seed)."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.db.models import F

from apps.bookings.models import InventoryDay, Stay
from apps.bookings.services.charges import post_room_charges
from apps.bookings.services.reservations import cancel_reservation, check_in, check_out
from apps.bookings.tests.helpers import book, build_hotel, oct_
from apps.finance.models import Folio
from apps.finance.services import (
    close_settled_folios,
    get_or_create_folio,
    record_payment,
    reservation_balance,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def hotel(prop, django_capture_on_commit_callbacks):
    """A consistent hotel: a stay that checked out and paid, one in house, a future one with a deposit and a
    cancelled one (business date 2026-10-01)."""
    hotel = build_hotel(prop)
    with django_capture_on_commit_callbacks(execute=True):
        hotel.past = book(hotel, oct_(-9), oct_(-7))
        for stay in hotel.past.stays.all():
            check_in(stay, force=True)
            check_out(stay, force=True)
        folio = get_or_create_folio(hotel.past)
        record_payment(folio, amount=reservation_balance(hotel.past), method="card_terminal")
        close_settled_folios(hotel.past)

        hotel.in_house = book(hotel, oct_(-1), oct_(3))
        for stay in hotel.in_house.stays.all():
            check_in(stay, force=True)
            post_room_charges(stay, until_date=prop.business_date)

        hotel.future = book(hotel, oct_(10), oct_(12))
        record_payment(get_or_create_folio(hotel.future), amount=100000, method="bank_transfer")

        hotel.cancelled = book(hotel, oct_(15), oct_(17))
        cancel_reservation(hotel.cancelled, reason="Cambio de planes")
    return hotel


def run(**options) -> str:
    out = StringIO()
    call_command("check_integrity", stdout=out, **options)
    return out.getvalue()


def failing_run(**options) -> str:
    out = StringIO()
    with pytest.raises(CommandError):
        call_command("check_integrity", stdout=out, **options)
    return out.getvalue()


def test_a_consistent_hotel_passes(hotel):
    output = run()
    assert "FALLA" not in output
    assert hotel.prop.name in output


def test_inventory_drift_is_reported_without_repairing_it(hotel):
    row = InventoryDay.objects.filter(property=hotel.prop, date=oct_(2)).first()
    InventoryDay.objects.filter(pk=row.pk).update(sold_units=F("sold_units") + 1)
    corrupted = InventoryDay.objects.get(pk=row.pk).sold_units

    output = failing_run(property=hotel.prop.slug)

    assert "FALLA" in output and "inventario" in output.lower()
    assert InventoryDay.objects.get(pk=row.pk).sold_units == corrupted  # read-only: the drift is still there


def test_a_closed_folio_that_still_owes_is_reported(hotel):
    Folio.objects.filter(reservation=hotel.future).update(status=Folio.Status.CLOSED)
    assert "FALLA" in failing_run()


def test_a_stay_whose_total_does_not_match_its_nights_and_charges_is_reported(hotel):
    stay = hotel.past.stays.get()
    Stay.objects.filter(pk=stay.pk).update(total_amount=F("total_amount") + 1)
    output = failing_run()
    assert output.count("FALLA") >= 2  # nightly rates and room charges (and the reservation total)


def test_only_the_requested_property_is_checked(hotel, organization):
    from apps.core.tests.factories import PropertyFactory

    other = PropertyFactory(organization=organization, name="Otro Hotel")
    output = run(property=other.slug)
    assert "Otro Hotel" in output and hotel.prop.name not in output
