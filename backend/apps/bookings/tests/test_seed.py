"""Bookings demo seed (plan B2b › Seed), run on data created here (the inventory, rates and guests seeders are
written in parallel; B-INT runs the whole chain).

Reservations from −60 to +90 days through the contract services, states coherent with the dates, mixed sources
(OTA with booksim/airsim), a group, dorm beds, VIPs, arrivals and departures today; InventoryDay consistent.

Seeding 150 days takes a while, so the module seeds ONCE inside a transaction that is rolled back when the
module ends; every test runs in its own savepoint on top of it (pytest-django nests the test atomics).
"""

import random
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from django.db import transaction

from apps.bookings import seed
from apps.bookings.models import InventoryDay, Reservation, ReservationGroup, Stay
from apps.bookings.services.inventory import rebuild_inventory
from apps.bookings.tests.helpers import build_hotel
from apps.core.seed import SeedContext
from apps.core.tests.factories import OrganizationFactory, PropertyFactory
from apps.finance.models import Charge
from apps.guests.tests.factories import ForeignGuestFactory, GuestFactory

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 1)
WINDOW_START, WINDOW_END = TODAY - timedelta(days=60), TODAY + timedelta(days=90)


@pytest.fixture(scope="module")
def seeded(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock(), transaction.atomic():
        organization = OrganizationFactory(status="active")
        # a fixed slug keeps the demo's dice (seeded per property slug) independent of the test order
        hotel = build_hotel(PropertyFactory(organization=organization, slug="hotel-demo-seed"))
        guests = [GuestFactory(organization=organization) for _ in range(12)]
        guests += [ForeignGuestFactory(organization=organization) for _ in range(6)]
        GuestFactory(organization=organization, is_vip=True)
        ctx = SeedContext(
            today=TODAY,
            rng=random.Random(20260925),
            orgs={"aurora": organization},
            properties={"aurora": hotel.prop},
            data={"guests": {"aurora": [guest.pk for guest in guests]}},
        )
        seed.seed(ctx)
        yield SimpleNamespace(hotel=hotel, ctx=ctx)
        transaction.set_rollback(True)


@pytest.fixture
def hotel(seeded):
    return seeded.hotel


@pytest.fixture
def demo(seeded):
    return seeded.ctx


def stays(hotel):
    return Stay.objects.filter(reservation__property=hotel.prop).select_related("reservation", "room", "bed")


def test_skips_a_property_without_inventory_or_rates(prop):
    ctx = SeedContext(today=TODAY, rng=random.Random(1), properties={"aurora": prop}, orgs={}, data={})
    seed.seed(ctx)
    assert not Reservation.objects.filter(property=prop).exists()


def test_creates_reservations_around_today_with_realistic_occupancy(hotel, demo):
    all_stays = list(stays(hotel))
    assert min(stay.checkin_date for stay in all_stays) >= WINDOW_START
    assert max(stay.checkin_date for stay in all_stays) < WINDOW_END
    assert min(stay.checkin_date for stay in all_stays) <= TODAY - timedelta(days=50)
    assert max(stay.checkout_date for stay in all_stays) >= TODAY + timedelta(days=80)

    sold = [stay for stay in all_stays if stay.status not in ("cancelled", "no_show")]
    units, days = 8, 150  # 3 DBL + 1 STE rooms, 4 dorm beds · −60 → +90
    nights = sum(len([n for n in stay.nights if WINDOW_START <= n < WINDOW_END]) for stay in sold)
    assert 0.5 <= nights / (units * days) <= 0.9


def test_states_follow_the_dates(hotel, demo):
    for stay in stays(hotel):
        if stay.checkout_date < TODAY:
            assert stay.status in ("checked_out", "cancelled", "no_show"), stay
        elif stay.checkin_date < TODAY:
            assert stay.status in ("checked_in", "cancelled"), stay
        elif stay.checkin_date == TODAY:
            assert stay.status in ("confirmed", "tentative"), stay
        else:
            assert stay.status in ("confirmed", "tentative", "cancelled"), stay
    statuses = set(stays(hotel).values_list("status", flat=True))
    assert {"checked_out", "checked_in", "confirmed", "tentative", "cancelled", "no_show"} <= statuses


def test_in_house_guests_are_charged_until_yesterday(hotel, demo):
    in_house = list(stays(hotel).filter(status="checked_in"))
    assert in_house
    for stay in in_house:
        posted = set(Charge.objects.filter(stay=stay, kind="room").values_list("night_date", flat=True))
        assert posted == {night for night in stay.nights if night < TODAY}
        assert stay.room is not None and stay.checked_in_at is not None


def test_past_stays_were_checked_out_with_every_night_charged(hotel, demo):
    past = list(stays(hotel).filter(status="checked_out"))
    assert past
    for stay in past[:15]:
        posted = sorted(Charge.objects.filter(stay=stay, kind="room").values_list("night_date", flat=True))
        assert posted == stay.nights
        assert stay.checked_out_at.date() <= stay.checkout_date


def test_cancellations_are_dated_when_they_happened(hotel, demo):
    """History is not all "today": the service stamps `cancelled_at` with the moment the seed runs, so the
    seed moves it back. A past cancellation happened on its arrival day at the latest (a late cancellation,
    the reason it paid a penalty); a future one between the booking and today. (The finance seed then dates
    the penalty charge on that same business date.)"""
    tz = ZoneInfo(hotel.prop.timezone)
    cancelled = list(Reservation.objects.filter(property=hotel.prop, status="cancelled"))
    assert any(r.checkin_date < TODAY for r in cancelled) and any(r.checkin_date > TODAY for r in cancelled)
    for reservation in cancelled:
        assert reservation.created_at <= reservation.cancelled_at, reservation.code
        assert reservation.cancelled_at.astimezone(tz).date() <= min(reservation.checkin_date, TODAY), (
            reservation.code
        )


def test_today_has_arrivals_ready_and_unassigned_and_departures(hotel, demo):
    arrivals = list(stays(hotel).filter(checkin_date=TODAY, status__in=["confirmed", "tentative"]))
    assert any(stay.room is None for stay in arrivals)
    assert any(
        stay.room is not None and stay.room.housekeeping_status in ("clean", "inspected") for stay in arrivals
    )
    assert stays(hotel).filter(checkout_date=TODAY, status="checked_in").exists()
    assert any(stay.reservation.booker.is_vip for stay in stays(hotel).filter(checkin_date__gte=TODAY))


def test_sources_channels_groups_and_dorm_beds(hotel, demo):
    reservations = Reservation.objects.filter(property=hotel.prop)
    sources = set(reservations.values_list("source", flat=True))
    assert {"front_desk", "ota", "marketplace", "booking_engine"} <= sources
    assert set(reservations.filter(source="ota").values_list("channel_code", flat=True)) <= {
        "booksim",
        "airsim",
    }
    assert reservations.filter(source="ota").exclude(external_id="").exists()
    group = ReservationGroup.objects.filter(property=hotel.prop).first()
    assert group is not None and group.reservations.count() >= 2
    dorm_stays = stays(hotel).filter(room_type=hotel.dorm_type).exclude(status__in=["cancelled", "no_show"])
    assert dorm_stays.exists() and not dorm_stays.filter(checkin_date__lt=TODAY, bed__isnull=True).exists()


def test_totals_are_priced_and_the_inventory_is_consistent(hotel, demo):
    assert not stays(hotel).filter(total_amount__lte=Decimal("0")).exists()
    result = rebuild_inventory(hotel.prop, WINDOW_START, WINDOW_END + timedelta(days=7))
    assert (result.created, result.updated, result.drift) == (0, 0, [])  # materialized and exact
    assert InventoryDay.objects.filter(property=hotel.prop, date=WINDOW_START - timedelta(days=7)).exists()


def test_shares_what_it_created_and_is_idempotent(hotel, demo):
    shared = demo.data["bookings"]["aurora"]
    assert len(shared["reservations"]) == Reservation.objects.filter(property=hotel.prop).count()
    assert shared["arrivals_today"] and shared["in_house"] and shared["departures_today"]
    before = Reservation.objects.count()
    seed.seed(demo)
    assert Reservation.objects.count() == before
