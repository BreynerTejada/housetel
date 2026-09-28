"""OTA simulator (`/app/simulators/ota`): BookSim/AirSim (and the simulated Channex) show the ARI they
received and sell from it; their bookings reach the PMS through `import_booking`, like a real channel.
BookSim/AirSim deliver each booking at once; the simulated Channex keeps them until the PMS pulls them."""

from decimal import Decimal

import pytest

from apps.bookings.models import Reservation
from apps.bookings.services.reservations import cancel_reservation, create_reservation
from apps.bookings.tests.helpers import guest_input, oct_, stay_request
from apps.bookings.types import ReservationRequest
from apps.core import integrations
from apps.core.models import Alert
from apps.distribution.models import ExternalReservationMap, SimOtaBooking, SimOtaInventory
from apps.distribution.services import simulator
from apps.distribution.services.pull import pull_bookings
from apps.distribution.services.queue import full_sync, process_queue
from apps.distribution.services.simulator import SimulatorError
from apps.distribution.tests.factories import connect
from apps.rates.services.quote import set_daily_rates

pytestmark = pytest.mark.django_db

GUEST = {"first_name": "Lucía", "last_name": "Martínez", "email": "lucia@example.com", "country": "CO"}


def cell(connection, room, rate, day) -> SimOtaInventory:
    return SimOtaInventory.objects.get(
        connection=connection, external_room_id=room, external_rate_id=rate, date=day
    )


def sell(connection, checkin, checkout, *, room="BS-DBL", rate="BS-BAR", adults=2, **kwargs):
    return simulator.create_booking(
        connection,
        external_room_id=room,
        external_rate_id=rate,
        checkin=checkin,
        checkout=checkout,
        adults=adults,
        guest=kwargs.pop("guest", GUEST),
        **kwargs,
    )


@pytest.fixture
def synced(hotel):
    """BookSim (DBL, STE ↔ BAR with a 10 % markup) after its first full sync."""
    connection = connect(hotel, "booksim", markup="10")
    full_sync(connection)
    return connection


def test_a_booksim_booking_enters_the_pms_through_the_channel_path(hotel, synced):
    booking = sell(synced, oct_(10), oct_(12))

    booking.refresh_from_db()
    assert (booking.status, booking.pms_status, booking.revision) == ("new", "imported", 1)
    reservation = ExternalReservationMap.objects.get(
        connection=synced, external_id=booking.external_id
    ).reservation
    assert (reservation.source, reservation.channel_code, reservation.external_id) == (
        "ota",
        "booksim",
        booking.external_id,
    )
    assert reservation.booker.full_name == "Lucía Martínez"
    stay = reservation.stays.get()
    assert (stay.room_type, stay.checkin_date, stay.checkout_date, stay.adults) == (
        hotel.dbl,
        oct_(10),
        oct_(12),
        2,
    )
    # the OTA sold at the price it received (320.000 + 10 %), which the PMS keeps
    assert [night["net"] for night in stay.nightly_rates] == ["352000.00", "352000.00"]
    assert booking.payload["total"] == "704000.00"
    assert booking.external_id.startswith("BS-")


def test_a_rate_change_in_the_pms_reaches_the_ota_after_the_push(
    hotel, synced, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        set_daily_rates(
            property=hotel.prop,
            room_type=hotel.dbl,
            rate_plan=hotel.plan,
            start=oct_(10),
            end=oct_(11),
            price=Decimal("300000"),
        )
    assert cell(synced, "BS-DBL", "BS-BAR", oct_(10)).price == Decimal("352000.00")  # not pushed yet

    process_queue(hotel.prop)  # what the debounced Celery task runs

    assert cell(synced, "BS-DBL", "BS-BAR", oct_(10)).price == Decimal("330000.00")
    assert cell(synced, "BS-DBL", "BS-BAR", oct_(11)).price == Decimal("352000.00")


def test_a_booking_lowers_the_availability_the_ota_sees_after_the_push(
    hotel, synced, django_capture_on_commit_callbacks
):
    assert cell(synced, "BS-STE", "BS-BAR", oct_(10)).available == 1

    with django_capture_on_commit_callbacks(execute=True):
        sell(synced, oct_(10), oct_(11), room="BS-STE")
    process_queue(hotel.prop)

    assert cell(synced, "BS-STE", "BS-BAR", oct_(10)).available == 0


def test_the_ota_only_sells_what_it_received(hotel):
    connection = connect(hotel, "booksim")
    with pytest.raises(SimulatorError) as error:
        sell(connection, oct_(10), oct_(12))
    assert error.value.code == "ota_not_sellable"
    assert "sincronización" in error.value.message


def test_the_ota_refuses_sold_out_and_stop_sell_nights(hotel, synced):
    SimOtaInventory.objects.filter(connection=synced, external_room_id="BS-STE", date=oct_(10)).update(
        available=0
    )
    SimOtaInventory.objects.filter(connection=synced, external_room_id="BS-DBL", date=oct_(11)).update(
        stop_sell=True
    )

    for room in ("BS-STE", "BS-DBL"):
        with pytest.raises(SimulatorError) as error:
            sell(synced, oct_(10), oct_(12), room=room)
        assert error.value.code == "ota_not_sellable"
        assert error.value.extra["reasons"]
    assert not SimOtaBooking.objects.exists()


def test_the_ota_applies_minimum_stay_and_closed_to_arrival(hotel, synced):
    SimOtaInventory.objects.filter(connection=synced, date=oct_(10)).update(min_los=3)
    SimOtaInventory.objects.filter(connection=synced, date=oct_(15)).update(closed_to_arrival=True)

    for checkin, checkout in ((oct_(10), oct_(12)), (oct_(15), oct_(16))):
        with pytest.raises(SimulatorError):
            sell(synced, checkin, checkout)
    assert sell(synced, oct_(10), oct_(13)).pms_status == "imported"


def test_forcing_a_sale_simulates_an_overbooking(hotel, synced):
    create_reservation(
        ReservationRequest(
            property=hotel.prop,
            booker=guest_input(),
            stays=[stay_request(hotel, oct_(10), oct_(12), room_type=hotel.ste)],
            source="phone",
        )
    )
    SimOtaInventory.objects.filter(connection=synced, external_room_id="BS-STE").update(available=0)

    booking = sell(synced, oct_(10), oct_(12), room="BS-STE", force=True)

    booking.refresh_from_db()
    assert (booking.pms_status, booking.payload["forced"]) == ("imported", True)
    assert Alert.objects.filter(kind="overbooking", resolved_at__isnull=True).exists()


def test_a_modification_and_a_cancellation_in_the_ota_update_the_pms(hotel, synced):
    booking = sell(synced, oct_(10), oct_(12))

    modified = simulator.modify_booking(synced, booking.external_id, checkout=oct_(14), adults=1)
    assert (modified.status, modified.revision, modified.pms_status) == ("modified", 2, "imported")
    reservation = Reservation.objects.get(external_id=booking.external_id)
    stay = reservation.stays.get()
    assert (stay.checkout_date, stay.adults) == (oct_(14), 1)

    cancelled = simulator.cancel_booking(synced, booking.external_id)
    reservation.refresh_from_db()
    assert (cancelled.status, cancelled.revision) == ("cancelled", 3)
    assert (reservation.status, reservation.cancellation_fee) == ("cancelled", Decimal("0.00"))


def test_a_modification_keeps_the_nights_the_booking_already_holds(hotel, synced):
    booking = sell(synced, oct_(10), oct_(12), room="BS-STE")
    # after the push the OTA sees the suite as sold on the nights this very booking holds
    SimOtaInventory.objects.filter(connection=synced, external_room_id="BS-STE", date__lt=oct_(12)).update(
        available=0
    )

    modified = simulator.modify_booking(synced, booking.external_id, checkout=oct_(13))

    assert modified.pms_status == "imported"
    assert [night["date"] for night in modified.payload["rooms"][0]["nightly_rates"]] == [
        "2026-10-10",
        "2026-10-11",
        "2026-10-12",
    ]


def test_a_cancelled_booking_cannot_be_modified(hotel, synced):
    booking = sell(synced, oct_(10), oct_(12))
    simulator.cancel_booking(synced, booking.external_id)

    with pytest.raises(SimulatorError) as error:
        simulator.modify_booking(synced, booking.external_id, checkout=oct_(13))
    assert error.value.code == "booking_cancelled"


def test_a_failed_delivery_is_kept_and_can_be_delivered_again(hotel, synced):
    booking = sell(synced, oct_(10), oct_(12), room="BS-STE")
    blocker = create_reservation(
        ReservationRequest(
            property=hotel.prop,
            booker=guest_input(),
            stays=[stay_request(hotel, oct_(12), oct_(14), room_type=hotel.ste)],
            source="phone",
        )
    )

    failed = simulator.modify_booking(synced, booking.external_id, checkout=oct_(14), force=True)
    assert failed.pms_status == "failed"
    assert failed.pms_message  # why the PMS refused it

    cancel_reservation(blocker, reason="Liberar la suite", waive_fee=True)
    result = simulator.deliver(synced, failed)

    failed.refresh_from_db()
    assert (result.action, failed.pms_status) == ("modified", "imported")
    assert Reservation.objects.get(external_id=booking.external_id).stays.get().checkout_date == oct_(14)


def test_the_simulated_channex_keeps_bookings_until_the_pms_pulls_them(hotel):
    connection = connect(hotel, "channex", markup="0")  # channel_channex defaults to simulated
    full_sync(connection)

    booking = sell(connection, oct_(10), oct_(12), room="CH-DBL", rate="CH-BAR")

    assert booking.pms_status == "pending"
    assert not Reservation.objects.filter(channel_code="channex").exists()

    summary = pull_bookings(hotel.prop)

    booking.refresh_from_db()
    assert (summary["created"], summary["acknowledged"], booking.pms_status) == (1, 1, "imported")
    assert Reservation.objects.get(channel_code="channex").external_id == booking.external_id
    assert pull_bookings(hotel.prop)["created"] == 0  # acknowledged: not offered again


def test_a_channex_booking_the_pms_cannot_apply_stays_in_the_feed_as_failed(hotel):
    connection = connect(hotel, "channex")
    full_sync(connection)
    booking = sell(connection, oct_(10), oct_(12), room="CH-DBL", rate="CH-BAR")
    connection.room_mappings.filter(external_room_id="CH-DBL").update(external_room_id="CH-DOUBLE")

    summary = pull_bookings(hotel.prop)

    booking.refresh_from_db()
    assert (summary["failed"], summary["acknowledged"], booking.pms_status) == (1, 0, "failed")
    assert "CH-DBL" in booking.pms_message
    connection.room_mappings.filter(external_room_id="CH-DOUBLE").update(external_room_id="CH-DBL")
    assert pull_bookings(hotel.prop)["created"] == 1
    booking.refresh_from_db()
    assert booking.pms_status == "imported" and booking.pms_message.startswith("Descargada por el PMS")


def test_only_simulated_connections_have_a_simulator(hotel):
    ical = connect(hotel, "ical", plans=[])
    with pytest.raises(SimulatorError) as error:
        simulator.ota_inventory(ical, oct_(1), oct_(8))
    assert error.value.code == "not_simulated"

    setting = integrations.get_setting(hotel.prop, "channel_channex")
    setting.mode = "real"
    setting.save(update_fields=["mode"])
    channex = connect(hotel, "channex")
    with pytest.raises(SimulatorError):
        sell(channex, oct_(10), oct_(11), room="CH-DBL", rate="CH-BAR")


def test_the_ota_grid_shows_what_the_current_mappings_received(hotel, synced):
    synced.rate_mappings.create(rate_plan=None, external_rate_id="BS-OLD")  # its plan was deleted

    grid = simulator.ota_inventory(synced, oct_(10), oct_(12))

    assert grid["dates"] == ["2026-10-10", "2026-10-11"]
    assert [room["external_room_id"] for room in grid["rooms"]] == ["BS-DBL", "BS-STE"]
    dbl = grid["rooms"][0]
    assert dbl["room_type"]["code"] == "DBL"
    rates = {rate["external_rate_id"]: rate for rate in dbl["rates"]}
    assert rates["BS-BAR"]["markup_percent"] == "10.00"
    first = rates["BS-BAR"]["cells"][0]
    assert (first["date"], first["available"], first["price"], first["stop_sell"]) == (
        "2026-10-10",
        3,
        "352000.00",
        False,
    )
    assert rates["BS-OLD"]["cells"] == [None, None]  # never received anything
    assert grid["last_update"] is not None


def test_a_guest_is_invented_when_none_is_given(hotel, synced):
    booking = simulator.create_booking(
        synced,
        external_room_id="BS-DBL",
        external_rate_id="BS-BAR",
        checkin=oct_(20),
        checkout=oct_(21),
        adults=1,
    )

    reservation = Reservation.objects.get(external_id=booking.external_id)
    assert reservation.booker.first_name and reservation.booker.last_name
    assert booking.payload["guest"]["first_name"] == reservation.booker.first_name


def test_dorm_beds_are_sold_per_guest(hotel):
    connection = connect(hotel, "airsim", room_types=[hotel.dorm_type])
    full_sync(connection)

    booking = sell(connection, oct_(10), oct_(11), room="AS-DORM", rate="AS-BAR", adults=3)

    reservation = Reservation.objects.get(external_id=booking.external_id)
    assert reservation.stays.count() == 3
    assert booking.payload["rooms"][0]["nightly_rates"] == [{"date": "2026-10-10", "amount": "195000.00"}]
    # each bed keeps the price the OTA received for one bed
    assert {stay.nightly_rates[0]["net"] for stay in reservation.stays.all()} == {"65000.00"}
    with pytest.raises(SimulatorError):  # 4 beds, 3 taken in the PMS but the OTA still sees 4 → 5 is too many
        sell(connection, oct_(10), oct_(11), room="AS-DORM", rate="AS-BAR", adults=5)
    assert booking.external_id.startswith("AS-")
