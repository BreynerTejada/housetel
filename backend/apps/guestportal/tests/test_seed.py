"""Guest portal demo seed: settings per hotel, ~40 % of the next 3 days' arrivals checked in online (every
requirement met, exactly like the real flow leaves them) and a few pending service requests."""

import random

import pytest

from apps.bookings.services.reservations import check_in
from apps.bookings.tests.helpers import book, foreign_input, oct_
from apps.core.models import Alert
from apps.core.seed import SeedContext
from apps.core.signals import guest_checked_in_online
from apps.core.tests.factories import PropertyFactory
from apps.guestportal import seed as portal_seed
from apps.guestportal.models import GuestPortalSettings, OnlineCheckin, ServiceRequest
from apps.guestportal.services.access import portal_settings
from apps.guestportal.services.checkin import missing_items

pytestmark = pytest.mark.django_db


@pytest.fixture
def world(hotel):
    """Business date Oct 1: 10 arrivals in the next 3 days (one foreign), one far away, one in house."""
    arrivals = [
        book(hotel, oct_(1 + day), oct_(2 + day), adults=1 + n % 2) for day in range(3) for n in range(3)
    ]
    arrivals.append(book(hotel, oct_(2), oct_(3), adults=1, room_type=hotel.ste, booker=foreign_input()))
    far = book(hotel, oct_(20), oct_(22))
    in_house = book(hotel, oct_(1), oct_(3), room_type=hotel.dorm_type, adults=1)
    check_in(in_house.stays.get())
    other = PropertyFactory(organization=hotel.prop.organization)  # a hotel without reservations
    ctx = SeedContext(
        today=oct_(1), rng=random.Random(20260925), properties={"aurora": hotel.prop, "andino_bog": other}
    )
    return {"ctx": ctx, "arrivals": arrivals, "far": far, "in_house": in_house, "other": other}


def test_the_seed_checks_in_online_about_forty_percent_of_the_next_arrivals(world, hotel):
    received = []
    guest_checked_in_online.connect(
        lambda sender, **kw: received.append(kw), weak=False, dispatch_uid="seed-t"
    )
    try:
        portal_seed.seed(world["ctx"])
    finally:
        guest_checked_in_online.disconnect(dispatch_uid="seed-t")

    completed = OnlineCheckin.objects.filter(status="completed")
    assert completed.count() == 4  # 40 % of 10
    assert {checkin.reservation_id for checkin in completed} <= {r.pk for r in world["arrivals"]}
    settings = portal_settings(hotel.prop)
    for checkin in completed.select_related("reservation__property", "reservation__booker"):
        assert missing_items(checkin.reservation, checkin, settings) == [], checkin.reservation.code
        assert checkin.signature and checkin.eta and checkin.accepted_terms_at
        assert checkin.reservation.eta == checkin.eta
    assert received == []  # historical data: nobody is notified


def test_the_seed_leaves_some_pending_requests_with_their_alerts(world, hotel):
    portal_seed.seed(world["ctx"])

    pending = ServiceRequest.objects.filter(status="requested")
    assert pending.exists()
    assert {request.kind for request in pending} >= {"late_checkout"}
    assert (
        Alert.objects.filter(kind="guestportal_request", resolved_at__isnull=True).count() == pending.count()
    )


def test_every_hotel_gets_its_settings(world, hotel):
    portal_seed.seed(world["ctx"])

    assert GuestPortalSettings.objects.filter(property__in=[hotel.prop, world["other"]]).count() == 2
    assert hotel.prop.name in GuestPortalSettings.objects.get(property=hotel.prop).terms["es"]


def test_the_seed_is_idempotent(world):
    portal_seed.seed(world["ctx"])
    counts = (
        OnlineCheckin.objects.count(),
        ServiceRequest.objects.count(),
        GuestPortalSettings.objects.count(),
    )

    portal_seed.seed(world["ctx"])

    assert (OnlineCheckin.objects.count(), ServiceRequest.objects.count(),
            GuestPortalSettings.objects.count()) == counts  # fmt: skip
