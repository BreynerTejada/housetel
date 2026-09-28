"""Channel bookings entering the PMS: `import_booking` is idempotent per external id (payload hash); new →
OTA reservation without rate restrictions and with the channel prices, modified → `modify_stay`, cancelled →
`cancel_reservation` without fee."""

from decimal import Decimal

import pytest

from apps.bookings.models import Reservation
from apps.bookings.services.reservations import create_reservation
from apps.bookings.tests.helpers import guest_input, oct_, stay_request
from apps.bookings.types import ReservationRequest
from apps.core.models import Alert, AuditEvent
from apps.distribution.models import ExternalReservationMap, SyncLog
from apps.distribution.services.importer import import_booking
from apps.distribution.types import InboundBooking, InboundRoom
from apps.rates.tests.factories import CancellationPolicyFactory, DailyRateFactory

pytestmark = pytest.mark.django_db

GUEST = {
    "first_name": "Ana",
    "last_name": "Pérez",
    "email": "ana.perez@example.com",
    "phone": "3001234567",
    "country": "CO",
}


def room(checkin, checkout, *, external_room_id="BS-DBL", adults=2, children=0, nightly=None):
    return InboundRoom(
        external_room_id=external_room_id,
        external_rate_id="BS-BAR",
        checkin=checkin,
        checkout=checkout,
        adults=adults,
        children=children,
        nightly_rates=nightly,
    )


def nightly(*pairs):
    return [{"date": day, "amount": amount} for day, amount in pairs]


def booking(external_id, *rooms, status="new", guest=None, **fields):
    return InboundBooking(
        external_id=external_id, status=status, guest=dict(guest or GUEST), rooms=list(rooms), **fields
    )


def test_a_new_booking_becomes_an_ota_reservation_priced_by_the_channel(hotel, booksim):
    prices = nightly(("2026-10-10", "300000"), ("2026-10-11", "310000"))

    result = import_booking(booksim, booking("BS-1001", room(oct_(10), oct_(12), nightly=prices)))

    assert result.action == "created"
    reservation = result.reservation
    assert (reservation.source, reservation.channel_code, reservation.external_id) == (
        "ota",
        "booksim",
        "BS-1001",
    )
    assert (reservation.status, reservation.guarantee) == ("confirmed", "ota")
    stay = reservation.stays.get()
    assert (stay.room_type, stay.rate_plan, stay.checkin_date, stay.checkout_date, stay.adults) == (
        hotel.dbl,
        hotel.plan,
        oct_(10),
        oct_(12),
        2,
    )
    assert [(night["date"], night["net"]) for night in stay.nightly_rates] == [
        ("2026-10-10", "300000.00"),
        ("2026-10-11", "310000.00"),
    ]
    assert (reservation.booker.first_name, reservation.booker.email) == ("Ana", "ana.perez@example.com")
    assert (
        ExternalReservationMap.objects.get(connection=booksim, external_id="BS-1001").reservation
        == reservation
    )
    log = SyncLog.objects.get(connection=booksim)
    assert (log.direction, log.kind, log.status, log.reservation, log.external_id) == (
        "in",
        "booking_new",
        "success",
        reservation,
        "BS-1001",
    )
    assert AuditEvent.objects.get(action="bookings.reservation_created").source == "channel"


def test_rate_restrictions_do_not_block_channel_bookings(hotel, booksim):
    DailyRateFactory(
        room_type=hotel.dbl, rate_plan=hotel.plan, date=oct_(10), price=Decimal("320000"), min_los=5
    )

    result = import_booking(booksim, booking("BS-1002", room(oct_(10), oct_(12))))

    assert result.action == "created"
    assert result.reservation.stays.get().total_amount == Decimal("761600.00")  # PMS price when none is sent


def test_the_same_payload_twice_changes_nothing(hotel, booksim):
    payload = booking("BS-1003", room(oct_(10), oct_(12)))
    first = import_booking(booksim, payload)

    again = import_booking(booksim, booking("BS-1003", room(oct_(10), oct_(12))))

    assert (again.action, again.reservation) == ("unchanged", first.reservation)
    assert Reservation.objects.count() == 1
    assert list(SyncLog.objects.order_by("created_at").values_list("status", flat=True)) == [
        "success",
        "skipped",
    ]


def test_a_modification_moves_dates_and_category(hotel, booksim):
    created = import_booking(booksim, booking("BS-1004", room(oct_(10), oct_(12))))

    result = import_booking(
        booksim, booking("BS-1004", room(oct_(10), oct_(13), external_room_id="BS-STE"), status="modified")
    )

    assert (result.action, result.reservation) == ("modified", created.reservation)
    stay = created.reservation.stays.get()
    assert (stay.room_type, stay.checkin_date, stay.checkout_date) == (hotel.ste, oct_(10), oct_(13))
    mapping = ExternalReservationMap.objects.get(external_id="BS-1004")
    assert mapping.last_status == "modified"
    assert SyncLog.objects.filter(kind="booking_modified", status="success").count() == 1


def test_a_cancellation_cancels_without_fee(hotel, booksim):
    policy = CancellationPolicyFactory(property=hotel.prop, non_refundable=True)
    hotel.plan.cancellation_policy = policy
    hotel.plan.save(update_fields=["cancellation_policy"])
    created = import_booking(booksim, booking("BS-1005", room(oct_(10), oct_(12))))

    result = import_booking(booksim, booking("BS-1005", room(oct_(10), oct_(12)), status="cancelled"))

    reservation = Reservation.objects.get(pk=created.reservation.pk)
    assert result.action == "cancelled"
    assert (reservation.status, reservation.cancellation_fee) == ("cancelled", Decimal("0.00"))
    assert AuditEvent.objects.get(action="bookings.reservation_cancelled").source == "channel"
    assert import_booking(
        booksim, booking("BS-1005", room(oct_(10), oct_(12)), status="cancelled")
    ).action == ("unchanged")


def test_cancelling_a_booking_the_pms_never_received_is_ignored(hotel, booksim):
    result = import_booking(booksim, booking("BS-404", room(oct_(10), oct_(12)), status="cancelled"))

    assert (result.action, result.reservation) == ("ignored", None)
    assert not Reservation.objects.exists()


def test_a_booking_without_availability_is_accepted_and_alerts_overbooking(hotel, booksim):
    create_reservation(
        ReservationRequest(
            property=hotel.prop,
            booker=guest_input(),
            stays=[stay_request(hotel, oct_(10), oct_(12), room_type=hotel.ste)],
            source="phone",
        )
    )

    result = import_booking(booksim, booking("BS-1006", room(oct_(10), oct_(12), external_room_id="BS-STE")))

    assert (result.action, result.overbooked) == ("created", True)
    alert = Alert.objects.get(kind="overbooking", resolved_at__isnull=True)
    assert alert.data["reservation_id"] == str(result.reservation.pk)
    assert SyncLog.objects.get(external_id="BS-1006").status == "warning"


def test_an_unmapped_room_fails_alerts_and_imports_once_it_is_mapped(hotel, booksim):
    payload = booking("BS-1007", room(oct_(10), oct_(12), external_room_id="BS-FAMILY"))

    failed = import_booking(booksim, payload)

    assert (failed.action, failed.code) == ("failed", "unmapped_room")
    assert not Reservation.objects.exists()
    alert = Alert.objects.get(resolved_at__isnull=True)
    assert (alert.kind, alert.severity, alert.dedupe_key) == (
        "channel_import_failed",
        "critical",
        f"distribution:import:{booksim.pk}:BS-1007",
    )
    assert SyncLog.objects.get().status == "error"

    booksim.room_mappings.filter(external_room_id="BS-DBL").update(external_room_id="BS-FAMILY")
    assert import_booking(booksim, payload).action == "created"
    assert not Alert.objects.filter(resolved_at__isnull=True).exists()


def test_a_modification_that_cannot_be_applied_fails_and_is_retried_later(hotel, booksim):
    created = import_booking(booksim, booking("BS-1008", room(oct_(10), oct_(12), external_room_id="BS-STE")))
    create_reservation(
        ReservationRequest(
            property=hotel.prop,
            booker=guest_input(),
            stays=[stay_request(hotel, oct_(12), oct_(14), room_type=hotel.ste)],
            source="phone",
        )
    )
    longer = booking("BS-1008", room(oct_(10), oct_(14), external_room_id="BS-STE"), status="modified")

    result = import_booking(booksim, longer)

    assert (result.action, result.code) == ("failed", "no_availability")
    assert created.reservation.stays.get().checkout_date == oct_(12)
    assert Alert.objects.filter(kind="channel_import_failed", resolved_at__isnull=True).exists()
    assert import_booking(booksim, longer).action == "failed"  # not remembered: the next delivery retries


def test_dorm_bookings_take_one_bed_per_guest_and_modify_them_together(hotel):
    from apps.distribution.tests.factories import connect

    connection = connect(hotel, "booksim", room_types=[hotel.dorm_type])
    dorm = room(
        oct_(10),
        oct_(12),
        external_room_id="BS-DORM",
        adults=3,
        nightly=nightly(("2026-10-10", "180000"), ("2026-10-11", "180000")),
    )

    created = import_booking(connection, booking("BS-2001", dorm))
    later = room(oct_(11), oct_(13), external_room_id="BS-DORM", adults=3)
    modified = import_booking(connection, booking("BS-2001", later, status="modified"))

    stays = list(created.reservation.stays.order_by("created_at"))
    assert len(stays) == 3
    assert modified.action == "modified"
    assert {(stay.checkin_date, stay.checkout_date) for stay in stays} == {(oct_(11), oct_(13))}


def test_a_foreign_guest_is_exempt_and_gets_english(hotel, booksim):
    guest = {"first_name": "John", "last_name": "Smith", "email": "john@example.com", "country": "US"}

    result = import_booking(booksim, booking("BS-1009", room(oct_(10), oct_(11)), guest=guest))

    booker = result.reservation.booker
    assert (booker.nationality, booker.country_of_residence, result.reservation.language) == (
        "US",
        "US",
        "en",
    )
    assert result.reservation.stays.get().nightly_rates[0]["tax"] == "0.00"


def test_a_new_booking_after_the_pms_cancelled_the_old_one_is_booked_again(hotel, booksim):
    from apps.bookings.services.reservations import cancel_reservation

    first = import_booking(booksim, booking("BS-1010", room(oct_(10), oct_(12))))
    cancel_reservation(first.reservation, reason="Error de recepción", waive_fee=True)

    again = import_booking(booksim, booking("BS-1010", room(oct_(10), oct_(13)), status="modified"))

    assert again.action == "created"
    assert again.reservation.pk != first.reservation.pk
    assert ExternalReservationMap.objects.get(external_id="BS-1010").reservation == again.reservation
