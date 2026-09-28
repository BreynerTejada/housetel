"""iCal import (`distribution.pull_ical`): remote calendar events become OTA reservations with a
placeholder guest (`external_id` = UID); an event that disappears cancels its reservation. Blocks ("Not
available") and past events are ignored; an empty or unreachable calendar never cancels anything."""

from pathlib import Path

import httpx
import pytest
import respx

from apps.bookings.models import Reservation
from apps.bookings.tests.helpers import oct_
from apps.core import integrations
from apps.core.models import Alert
from apps.distribution.models import ExternalReservationMap, SyncLog
from apps.distribution.services.ical import pull_ical
from apps.distribution.tests.factories import ChannelConnectionFactory, RoomMappingFactory

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://www.airbnb.com/calendar/ical/41852.ics?s=0f3a9c"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.fixture
def airbnb(hotel):
    setting = integrations.get_setting(hotel.prop, "channel_ical")
    setting.mode = "real"
    setting.save(update_fields=["mode"])
    connection = ChannelConnectionFactory(property=hotel.prop, channel_code="ical", name="Airbnb")
    RoomMappingFactory(connection=connection, room_type=hotel.ste, external_room_id="", ical_import_url=URL)
    return connection


def ical_reservations(prop):
    return Reservation.objects.filter(property=prop, channel_code="ical").order_by("checkin_date")


@respx.mock
def test_events_become_reservations_and_blocks_are_ignored(hotel, airbnb):
    respx.get(URL).mock(return_value=httpx.Response(200, text=fixture("airbnb_two_reservations.ics")))

    summary = pull_ical(hotel.prop)

    rows = [
        (r.external_id, r.checkin_date, r.checkout_date, r.source, r.status, r.booker.full_name)
        for r in ical_reservations(hotel.prop).select_related("booker")
    ]
    assert rows == [
        ("1418fb94e984-aaa111@airbnb.com", oct_(10), oct_(12), "ota", "confirmed", "Huésped Airbnb"),
        ("1418fb94e984-bbb222@airbnb.com", oct_(15), oct_(18), "ota", "confirmed", "Huésped Airbnb"),
    ]
    stay = ical_reservations(hotel.prop).first().stays.get()
    assert (stay.room_type, stay.rate_plan, stay.adults) == (hotel.ste, hotel.plan, 2)
    assert "HMABC12345" in ical_reservations(hotel.prop).first().notes
    assert summary["created"] == 2
    mapping = airbnb.room_mappings.get()
    assert mapping.ical_last_sync_at is not None and mapping.ical_last_error == ""
    assert ExternalReservationMap.objects.filter(room_mapping=mapping).count() == 2


@respx.mock
def test_an_event_that_disappears_cancels_its_reservation(hotel, airbnb):
    route = respx.get(URL)
    route.mock(return_value=httpx.Response(200, text=fixture("airbnb_two_reservations.ics")))
    pull_ical(hotel.prop)

    route.mock(return_value=httpx.Response(200, text=fixture("airbnb_one_cancelled.ics")))
    summary = pull_ical(hotel.prop)

    statuses = {r.external_id: (r.status, r.cancellation_fee) for r in ical_reservations(hotel.prop)}
    assert statuses["1418fb94e984-aaa111@airbnb.com"][0] == "confirmed"
    assert statuses["1418fb94e984-bbb222@airbnb.com"] == ("cancelled", 0)
    assert (summary["cancelled"], summary["unchanged"]) == (1, 1)
    assert SyncLog.objects.filter(kind="booking_cancelled", status="success").count() == 1


@respx.mock
def test_an_empty_calendar_cancels_nothing(hotel, airbnb):
    route = respx.get(URL)
    route.mock(return_value=httpx.Response(200, text=fixture("airbnb_two_reservations.ics")))
    pull_ical(hotel.prop)

    route.mock(return_value=httpx.Response(200, text=fixture("airbnb_empty.ics")))
    pull_ical(hotel.prop)

    assert set(ical_reservations(hotel.prop).values_list("status", flat=True)) == {"confirmed"}
    assert SyncLog.objects.filter(kind="ical_import", status="warning").exists()


@respx.mock
def test_an_unreachable_calendar_is_logged_alerted_and_cancels_nothing(hotel, airbnb):
    route = respx.get(URL)
    route.mock(return_value=httpx.Response(200, text=fixture("airbnb_two_reservations.ics")))
    pull_ical(hotel.prop)

    route.mock(return_value=httpx.Response(503, text="Service Unavailable"))
    summary = pull_ical(hotel.prop)

    mapping = airbnb.room_mappings.get()
    assert "503" in mapping.ical_last_error
    assert summary["failed"] == 1
    assert set(ical_reservations(hotel.prop).values_list("status", flat=True)) == {"confirmed"}
    alert = Alert.objects.get(kind="ical_import_failed", resolved_at__isnull=True)
    assert alert.dedupe_key == f"distribution:ical:{mapping.pk}"

    route.mock(return_value=httpx.Response(200, text=fixture("airbnb_two_reservations.ics")))
    pull_ical(hotel.prop)
    assert not Alert.objects.filter(kind="ical_import_failed", resolved_at__isnull=True).exists()


@respx.mock
def test_a_room_calendar_books_that_room(hotel):
    setting = integrations.get_setting(hotel.prop, "channel_ical")
    setting.mode = "real"
    setting.save(update_fields=["mode"])
    connection = ChannelConnectionFactory(property=hotel.prop, channel_code="ical", name="VRBO")
    RoomMappingFactory(
        connection=connection,
        room_type=hotel.dbl,
        room=hotel.rooms["201"],
        external_room_id="",
        ical_import_url=URL,
    )
    respx.get(URL).mock(return_value=httpx.Response(200, text=fixture("airbnb_one_cancelled.ics")))

    pull_ical(hotel.prop)

    stay = Reservation.objects.get(external_id="1418fb94e984-aaa111@airbnb.com").stays.get()
    assert (stay.room_type, stay.room) == (hotel.dbl, hotel.rooms["201"])


def _book(hotel, room_type, checkin, checkout):
    from apps.bookings.services.reservations import create_reservation
    from apps.bookings.tests.helpers import guest_input, stay_request
    from apps.bookings.types import ReservationRequest

    return create_reservation(
        ReservationRequest(
            property=hotel.prop,
            booker=guest_input(),
            stays=[stay_request(hotel, checkin, checkout, room_type=room_type)],
            source="phone",
        )
    )


def export_url(mapping) -> str:
    return f"http://localhost:5173/api/v1/public/distribution/ical/{mapping.ical_export_token}.ics"


def test_the_simulated_mode_reads_housetel_exports_locally_and_never_goes_to_internet(hotel, organization):
    """Default (simulated) mode: another Housetel property's export is read locally; other URLs are not
    fetched."""
    from apps.bookings.tests.helpers import build_hotel
    from apps.core.tests.factories import PropertyFactory

    partner = build_hotel(PropertyFactory(organization=organization))
    exporter = ChannelConnectionFactory(property=partner.prop, channel_code="ical", name="Export")
    exported = RoomMappingFactory(connection=exporter, room_type=partner.ste, external_room_id="")
    _book(partner, partner.ste, oct_(10), oct_(12))
    importer = ChannelConnectionFactory(property=hotel.prop, channel_code="ical", name="Casa aliada")
    RoomMappingFactory(
        connection=importer, room_type=hotel.dbl, external_room_id="", ical_import_url=export_url(exported)
    )
    RoomMappingFactory(connection=importer, room_type=hotel.ste, external_room_id="", ical_import_url=URL)

    with respx.mock(assert_all_called=False) as mock:
        internet = mock.route(host__regex=".*")
        summary = pull_ical(hotel.prop)

    assert not internet.called
    assert summary["created"] == 1
    imported = Reservation.objects.get(property=hotel.prop, channel_code="ical")
    assert (imported.checkin_date, imported.checkout_date) == (oct_(10), oct_(12))


def test_a_property_never_imports_its_own_calendar_back(hotel):
    exporter = ChannelConnectionFactory(property=hotel.prop, channel_code="ical", name="Export")
    exported = RoomMappingFactory(connection=exporter, room_type=hotel.ste, external_room_id="")
    _book(hotel, hotel.ste, oct_(10), oct_(12))
    RoomMappingFactory(
        connection=ChannelConnectionFactory(property=hotel.prop, channel_code="ical", name="Espejo"),
        room_type=hotel.ste,
        external_room_id="",
        ical_import_url=export_url(exported),
    )

    summary = pull_ical(hotel.prop)

    assert summary["created"] == 0
    assert not Reservation.objects.filter(channel_code="ical").exists()


BOOKING_STYLE = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Booking.com//Calendar//EN
BEGIN:VEVENT
UID:booking-12345@booking.com
DTSTART;VALUE=DATE:20261020
DTEND;VALUE=DATE:20261023
SUMMARY:CLOSED - Not available
END:VEVENT
END:VCALENDAR
"""


def _real_mode(hotel):
    setting = integrations.get_setting(hotel.prop, "channel_ical")
    setting.mode = "real"
    setting.save(update_fields=["mode"])


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/cal.ics",
        "http://db:5432/cal.ics",
        "http://10.0.0.7/cal.ics",
        "ftp://example.com/x.ics",
    ],
)
def test_calendars_on_internal_networks_are_never_fetched(hotel, url):
    _real_mode(hotel)
    connection = ChannelConnectionFactory(property=hotel.prop, channel_code="ical", name="Airbnb")
    mapping = RoomMappingFactory(
        connection=connection, room_type=hotel.ste, external_room_id="", ical_import_url=url
    )

    with respx.mock(assert_all_called=False) as mock:
        anything = mock.route()
        summary = pull_ical(hotel.prop)

    assert not anything.called
    assert summary["failed"] == 1
    mapping.refresh_from_db()
    assert "red interna" in mapping.ical_last_error or "https://" in mapping.ical_last_error


@respx.mock
def test_webcal_urls_are_downloaded_over_https(hotel):
    _real_mode(hotel)
    connection = ChannelConnectionFactory(property=hotel.prop, channel_code="ical", name="VRBO")
    RoomMappingFactory(
        connection=connection,
        room_type=hotel.ste,
        external_room_id="",
        ical_import_url="webcal://www.vrbo.com/icalendar/abc.ics",
    )
    route = respx.get("https://www.vrbo.com/icalendar/abc.ics").mock(
        return_value=httpx.Response(200, text=fixture("airbnb_one_cancelled.ics"))
    )

    summary = pull_ical(hotel.prop)

    assert route.called and summary["created"] == 1


@respx.mock
def test_closed_events_are_reservations_when_the_connection_imports_every_event(hotel):
    """Booking.com calendars mark every booking as "CLOSED - Not available"."""
    _real_mode(hotel)
    connection = ChannelConnectionFactory(
        property=hotel.prop, channel_code="ical", name="Booking.com", settings={"import_all_events": True}
    )
    RoomMappingFactory(connection=connection, room_type=hotel.ste, external_room_id="", ical_import_url=URL)
    respx.get(URL).mock(return_value=httpx.Response(200, text=BOOKING_STYLE))

    summary = pull_ical(hotel.prop)

    assert summary["created"] == 1
    reservation = Reservation.objects.get(external_id="booking-12345@booking.com")
    assert (reservation.checkin_date, reservation.checkout_date) == (oct_(20), oct_(23))
    assert reservation.booker.full_name == "Huésped Booking.Com" or reservation.booker.last_name.startswith(
        "Booking"
    )


def test_the_simulated_mode_skips_external_calendars_once_and_says_why(hotel):
    connection = ChannelConnectionFactory(property=hotel.prop, channel_code="ical", name="Airbnb")
    mapping = RoomMappingFactory(
        connection=connection, room_type=hotel.ste, external_room_id="", ical_import_url=URL
    )

    with respx.mock(assert_all_called=False) as mock:
        internet = mock.route()
        first = pull_ical(hotel.prop)
        pull_ical(hotel.prop)

    assert not internet.called
    assert first["skipped"] == 1
    mapping.refresh_from_db()
    assert mapping.ical_last_error.startswith("Modo simulado")
    assert SyncLog.objects.filter(kind="ical_import", status="skipped").count() == 1  # not one per pull
