"""Distribution demo seed: BookSim and AirSim (simulated, mapped) with their first full sync, an iCal
export for the hostel, and the OTA reservations of the bookings seed linked to their connection (and
visible in the OTA simulator)."""

import random

import pytest

from apps.bookings.services.reservations import cancel_reservation, create_reservation
from apps.bookings.tests.helpers import build_hotel, guest_input, oct_, stay_request
from apps.bookings.types import ReservationRequest
from apps.core.seed import SeedContext
from apps.core.tests.factories import PropertyFactory
from apps.distribution import seed as distribution_seed
from apps.distribution.models import (
    AriUpdate,
    ChannelConnection,
    ExternalReservationMap,
    RoomMapping,
    SimOtaBooking,
    SimOtaInventory,
)
from apps.distribution.services import simulator
from apps.distribution.services.importer import import_booking

pytestmark = pytest.mark.django_db


def ota_booking(hotel, channel, external_id, checkin, checkout, *, room_type=None, adults=2):
    return create_reservation(
        ReservationRequest(
            property=hotel.prop,
            booker=guest_input(),
            stays=[stay_request(hotel, checkin, checkout, room_type=room_type or hotel.dbl, adults=adults)],
            source="ota",
            channel_code=channel,
            external_id=external_id,
            enforce_restrictions=False,
            guarantee="ota",
        ),
        source_label="system",
    )


@pytest.fixture
def world(hotel, organization):
    hostel = build_hotel(PropertyFactory(organization=organization))
    booked = ota_booking(hotel, "booksim", "BO-11111111", oct_(10), oct_(12))
    cancelled = ota_booking(hotel, "airsim", "AI-22222222", oct_(15), oct_(16), room_type=hotel.ste)
    cancel_reservation(cancelled, reason="Cancelada en AirSim", waive_fee=True, source="channel")
    dorm_party = ota_booking(
        hostel, "booksim", "BO-33333333", oct_(20), oct_(22), room_type=hostel.dorm_type, adults=3
    )
    empty = PropertyFactory(organization=organization)  # no categories yet: skipped
    ctx = SeedContext(
        today=oct_(1),
        rng=random.Random(20260925),
        properties={"aurora": hotel.prop, "andino_mde": empty, "andino_bog": hostel.prop},
    )
    return {
        "ctx": ctx,
        "hotel": hotel,
        "hostel": hostel,
        "booked": booked,
        "cancelled": cancelled,
        "dorm_party": dorm_party,
    }


def test_the_hotels_get_booksim_and_airsim_mapped_and_synced(world):
    distribution_seed.seed(world["ctx"])

    hotel = world["hotel"]
    connections = ChannelConnection.objects.filter(property=hotel.prop).order_by("channel_code")
    assert [(c.channel_code, c.status) for c in connections] == [("airsim", "active"), ("booksim", "active")]
    booksim = connections.get(channel_code="booksim")
    assert sorted(booksim.room_mappings.values_list("external_room_id", flat=True)) == [
        "BS-DBL",
        "BS-DORM",
        "BS-STE",
    ]
    assert list(booksim.rate_mappings.values_list("external_rate_id", "markup_percent")) == [("BS-BAR", 15)]
    # first full sync: 365 nights per room and rate, nothing left in the queue
    assert SimOtaInventory.objects.filter(connection=booksim, external_room_id="BS-DBL").count() == 365
    assert not AriUpdate.objects.exclude(status="sent").exists()
    assert booksim.last_sync_at is not None


def test_the_ota_reservations_are_linked_and_visible_in_the_simulator(world):
    distribution_seed.seed(world["ctx"])

    booksim = ChannelConnection.objects.get(property=world["hotel"].prop, channel_code="booksim")
    link = ExternalReservationMap.objects.get(connection=booksim, external_id="BO-11111111")
    assert link.reservation == world["booked"]
    sim = SimOtaBooking.objects.get(connection=booksim, external_id="BO-11111111")
    assert (sim.status, sim.pms_status) == ("new", "imported")
    room = sim.payload["rooms"][0]
    assert (room["external_room_id"], room["external_rate_id"], room["checkin"], room["adults"]) == (
        "BS-DBL",
        "BS-BAR",
        "2026-10-10",
        2,
    )
    assert [night["amount"] for night in room["nightly_rates"]] == ["320000.00", "320000.00"]
    airsim = ChannelConnection.objects.get(property=world["hotel"].prop, channel_code="airsim")
    assert SimOtaBooking.objects.get(connection=airsim, external_id="AI-22222222").status == "cancelled"

    # delivering the same booking again changes nothing in the PMS
    assert import_booking(booksim, simulator.to_inbound(sim)).action == "unchanged"


def test_a_dorm_party_is_one_channel_room_for_all_its_beds(world):
    distribution_seed.seed(world["ctx"])

    booksim = ChannelConnection.objects.get(property=world["hostel"].prop, channel_code="booksim")
    sim = SimOtaBooking.objects.get(connection=booksim, external_id="BO-33333333")
    (room,) = sim.payload["rooms"]
    assert (room["external_room_id"], room["adults"]) == ("BS-DORM", 3)
    assert room["nightly_rates"][0]["amount"] == "195000.00"  # 3 beds × 65.000
    assert import_booking(booksim, simulator.to_inbound(sim)).action == "unchanged"


def test_the_hostel_exports_its_calendars(world):
    distribution_seed.seed(world["ctx"])

    ical = ChannelConnection.objects.get(property=world["hostel"].prop, channel_code="ical")
    assert ical.name == "Airbnb"
    calendars = RoomMapping.objects.filter(connection=ical)
    assert calendars.count() == 3 and not calendars.exclude(ical_import_url="").exists()


def test_the_seed_is_idempotent_and_skips_hotels_without_categories(world):
    distribution_seed.seed(world["ctx"])
    counts = (
        ChannelConnection.objects.count(),
        SimOtaInventory.objects.count(),
        SimOtaBooking.objects.count(),
        ExternalReservationMap.objects.count(),
    )

    distribution_seed.seed(world["ctx"])

    assert (
        ChannelConnection.objects.count(),
        SimOtaInventory.objects.count(),
        SimOtaBooking.objects.count(),
        ExternalReservationMap.objects.count(),
    ) == counts
    assert not ChannelConnection.objects.filter(property=world["ctx"].properties["andino_mde"]).exists()
