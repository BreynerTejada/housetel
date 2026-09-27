"""`post_room_charges` (plan §C): one `room` charge per night before `until_date` not posted yet (idempotent),
net amount + the lodging tax (exempt for foreign non-residents), business date = the night.

Conftest hotel: DBL 320.000 net + 60.800 IVA per night.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.bookings.models import Reservation, Stay
from apps.bookings.services.charges import post_room_charges
from apps.bookings.services.reservations import assign_room
from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.bookings.tests.helpers import book, entry, foreign_input, oct_
from apps.finance.models import Charge, Folio

pytestmark = pytest.mark.django_db


def new_stay(hotel, checkin=None, checkout=None, **kwargs):
    return book(hotel, checkin or oct_(1), checkout or oct_(4), **kwargs).stays.get()


def posted(stay):
    return list(
        Charge.objects.filter(stay=stay, kind="room", voided_at__isnull=True)
        .order_by("night_date")
        .values_list("night_date", "amount", "tax_amount")
    )


def test_posts_one_charge_per_night_before_the_until_date(hotel, owner):
    stay = new_stay(hotel)
    assign_room(stay, hotel.rooms["101"])

    charges = post_room_charges(stay, until_date=oct_(3), actor=owner, source="user")

    assert [charge.night_date for charge in charges] == [oct_(1), oct_(2)]
    first = charges[0]
    assert (first.kind, first.amount, first.tax, first.tax_amount) == (
        "room",
        Decimal("320000"),
        hotel.iva,
        Decimal("60800"),
    )
    assert (first.business_date, first.stay, first.posted_by, first.source) == (oct_(1), stay, owner, "user")
    assert first.folio == Folio.objects.get(reservation=stay.reservation, stay=None)
    assert "101" in first.description


def test_is_idempotent(hotel):
    stay = new_stay(hotel)
    post_room_charges(stay, until_date=oct_(3))
    assert post_room_charges(stay, until_date=oct_(3)) == []
    assert [charge.night_date for charge in post_room_charges(stay, until_date=oct_(9))] == [oct_(3)]
    assert posted(stay) == [(oct_(day), Decimal("320000"), Decimal("60800")) for day in (1, 2, 3)]
    assert Charge.objects.get(night_date=oct_(1)).source == "automation"


def test_foreign_non_residents_are_charged_without_iva(hotel):
    stay = new_stay(hotel, booker=foreign_input())
    (charge,) = post_room_charges(stay, until_date=oct_(2))
    assert (charge.amount, charge.tax, charge.tax_amount) == (Decimal("320000"), hotel.iva, Decimal("0"))


def test_a_voided_night_is_posted_again(hotel):
    stay = new_stay(hotel)
    post_room_charges(stay, until_date=oct_(2))
    Charge.objects.filter(stay=stay).update(voided_at=timezone.now(), void_reason="Error")
    assert len(post_room_charges(stay, until_date=oct_(2))) == 1


@pytest.mark.parametrize("status", ["cancelled", "no_show"])
def test_cancelled_and_no_show_stays_get_nothing(hotel, status):
    stay = new_stay(hotel)
    Stay.objects.filter(pk=stay.pk).update(status=status)
    assert post_room_charges(stay, until_date=oct_(9)) == []


def test_an_included_tax_is_taken_out_of_the_night(hotel):
    hotel.iva.included_in_price = True
    hotel.iva.save()
    hotel.dbl.rate_defaults.update(price=Decimal("380800"))
    (charge,) = post_room_charges(new_stay(hotel), until_date=oct_(2))
    assert (charge.amount, charge.tax_amount) == (Decimal("320000"), Decimal("60800"))


def test_the_charges_add_up_to_the_stay_total(hotel):
    stay = new_stay(hotel, oct_(1), oct_(3))
    charges = post_room_charges(stay, until_date=oct_(3))
    assert (
        sum(charge.amount + charge.tax_amount for charge in charges)
        == Stay.objects.get(pk=stay.pk).total_amount
    )


def test_when_the_guest_turns_out_exempt_the_posted_night_follows_the_charge(hotel):
    stay = new_stay(hotel, oct_(1), oct_(3))  # booked as a resident: 380.800 per night
    booker = stay.reservation.booker
    booker.nationality, booker.country_of_residence = "US", "US"
    booker.save()

    post_room_charges(stay, until_date=oct_(2))

    stay = Stay.objects.get(pk=stay.pk)
    assert stay.nightly_rates[0] == entry(oct_(1), 320000, 320000, 0)
    assert stay.nightly_rates[1] == entry(oct_(2), 380800, 320000, 60800)  # not posted yet
    assert stay.total_amount == Decimal("700800")
    assert Reservation.objects.get(pk=stay.reservation_id).total_amount == Decimal("700800")


def test_a_stay_without_night_breakdown_splits_its_total(hotel):
    reservation = ReservationFactory(property=hotel.prop, checkin_date=oct_(1), checkout_date=oct_(3))
    stay = StayFactory(
        reservation=reservation, room_type=hotel.dbl, rate_plan=hotel.plan, total_amount=Decimal("761600")
    )

    charges = post_room_charges(stay, until_date=oct_(3))

    assert [(charge.amount, charge.tax_amount) for charge in charges] == [
        (Decimal("320000"), Decimal("60800"))
    ] * 2
    assert Folio.objects.filter(reservation=reservation).count() == 1
