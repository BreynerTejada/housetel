"""Channex adapter (`channel_channex`, mode real) against the documented API (docs.channex.io, verified
2026-09-27): header `user-api-key`; ARI with `POST /availability` and `POST /restrictions` (`values` array,
one value per night with `date`); bookings with `GET /booking_revisions/feed` + `POST
/booking_revisions/:id/ack`; `GET /properties` to test the connection. HTTP is mocked with respx."""

import json
from datetime import time
from decimal import Decimal

import httpx
import pytest
import respx

from apps.bookings.models import Reservation
from apps.bookings.tests.helpers import oct_
from apps.core import integrations
from apps.core.models import Alert
from apps.distribution.errors import ChannelError
from apps.distribution.models import SyncLog
from apps.distribution.providers import RealChannexProvider, provider_for
from apps.distribution.services.ari import build_batch
from apps.distribution.services.pull import pull_bookings
from apps.distribution.services.queue import enqueue_ari, process_queue
from apps.distribution.tests.factories import connect

pytestmark = pytest.mark.django_db

API = "https://staging.channex.io/api/v1"
API_KEY = "test-channex-key-0123456789"
CHANNEX_PROPERTY = "716305c4-561a-4561-a187-7f5b8aeb5920"
ROOM_DBL = "994d1375-dbbd-4072-8724-b2ab32ce781b"
ROOM_STE = "b3a2a0c1-2f5e-4bd4-9a6e-0f1c2d3e4f50"
RATE_DBL = "445835fb-7956-42ac-9efc-3e6f331f0808"
RATE_STE = "7c1d9b2e-5a4f-4e3d-8c2b-1a0f9e8d7c6b"


def real_channex(prop, *, environment="staging", property_id=CHANNEX_PROPERTY, api_key=API_KEY):
    setting = integrations.get_setting(prop, "channel_channex")
    setting.mode = "real"
    setting.config = {"environment": environment, "property_id": property_id}
    setting.save(update_fields=["mode", "config"])
    if api_key:
        integrations.set_secrets(setting, {"api_key": api_key})
    return setting


@pytest.fixture
def channex(hotel):
    """A real Channex connection: DBL/STE ↔ Channex room types, BAR ↔ one Channex rate plan per room type."""
    real_channex(hotel.prop)
    connection = connect(hotel, "channex", room_types=[], plans=[])
    connection.room_mappings.create(room_type=hotel.dbl, external_room_id=ROOM_DBL)
    connection.room_mappings.create(room_type=hotel.ste, external_room_id=ROOM_STE)
    connection.rate_mappings.create(
        rate_plan=hotel.plan, room_type=hotel.dbl, external_rate_id=RATE_DBL, markup_percent=Decimal("15")
    )
    connection.rate_mappings.create(rate_plan=hotel.plan, room_type=hotel.ste, external_rate_id=RATE_STE)
    return connection


def ok(**meta):
    return httpx.Response(
        200, json={"data": [{"id": "task-1", "type": "task"}], "meta": {"message": "Success", **meta}}
    )


def sent(route) -> list[dict]:
    return json.loads(route.calls.last.request.content)["values"]


def test_the_mode_picks_the_provider(hotel, channex):
    assert isinstance(provider_for(channex), RealChannexProvider)


@respx.mock
def test_availability_and_rates_are_sent_one_value_per_night(hotel, channex):
    availability = respx.post(f"{API}/availability").mock(return_value=ok())
    restrictions = respx.post(f"{API}/restrictions").mock(return_value=ok())
    batch = build_batch(channex, hotel.dbl, oct_(5), oct_(7), ("availability", "rates", "restrictions"))

    response = provider_for(channex).push_ari(channex, [batch])

    assert availability.calls.last.request.headers["user-api-key"] == API_KEY
    assert sent(availability) == [
        {"property_id": CHANNEX_PROPERTY, "room_type_id": ROOM_DBL, "date": "2026-10-05", "availability": 3},
        {"property_id": CHANNEX_PROPERTY, "room_type_id": ROOM_DBL, "date": "2026-10-06", "availability": 3},
    ]
    night = {
        "property_id": CHANNEX_PROPERTY,
        "rate_plan_id": RATE_DBL,
        "rate": "368000.00",  # 320.000 × 1,15
        "min_stay_arrival": 1,
        "max_stay": 0,
        "closed_to_arrival": False,
        "closed_to_departure": False,
        "stop_sell": False,
    }
    assert sent(restrictions) == [{**night, "date": "2026-10-05"}, {**night, "date": "2026-10-06"}]
    assert (response["availability"], response["restrictions"], response["warnings"]) == (2, 2, [])


@respx.mock
def test_only_the_changed_kinds_are_sent(hotel, channex):
    availability = respx.post(f"{API}/availability").mock(return_value=ok())
    restrictions = respx.post(f"{API}/restrictions").mock(return_value=ok())

    provider_for(channex).push_ari(
        channex, [build_batch(channex, hotel.ste, oct_(5), oct_(6), ("availability",))]
    )
    assert (availability.call_count, restrictions.call_count) == (1, 0)

    provider_for(channex).push_ari(channex, [build_batch(channex, hotel.ste, oct_(5), oct_(6), ("rates",))])
    assert (availability.call_count, restrictions.call_count) == (1, 1)
    assert sent(restrictions)[0]["rate"] == "650000.00"


@respx.mock
def test_closed_nights_go_as_stop_sell_without_rate_and_restrictions_are_translated(hotel, channex):
    from apps.rates.tests.factories import DailyRateFactory

    DailyRateFactory(
        room_type=hotel.ste,
        rate_plan=hotel.plan,
        date=oct_(5),
        price=Decimal("600000"),
        min_los=3,
        max_los=7,
        closed_to_arrival=True,
    )
    DailyRateFactory(
        room_type=hotel.ste, rate_plan=hotel.plan, date=oct_(6), price=Decimal("600000"), stop_sell=True
    )
    restrictions = respx.post(f"{API}/restrictions").mock(return_value=ok())

    provider_for(channex).push_ari(
        channex, [build_batch(channex, hotel.ste, oct_(5), oct_(7), ("restrictions",))]
    )

    first, second = sent(restrictions)
    assert (first["min_stay_arrival"], first["max_stay"], first["closed_to_arrival"], first["rate"]) == (
        3,
        7,
        True,
        "600000.00",
    )
    assert second["stop_sell"] is True


@respx.mock
def test_a_rate_the_channel_must_not_sell_goes_closed_without_a_price(hotel, channex):
    hotel.plan.is_public = False
    hotel.plan.save(update_fields=["is_public"])
    restrictions = respx.post(f"{API}/restrictions").mock(return_value=ok())

    provider_for(channex).push_ari(channex, [build_batch(channex, hotel.dbl, oct_(5), oct_(6), ("rates",))])

    (value,) = sent(restrictions)
    assert "rate" not in value  # Channex refuses a rate of 0
    assert value["stop_sell"] is True


@respx.mock
def test_warnings_of_rejected_values_are_reported(hotel, channex):
    warning = {"warning": "rate must be greater than 0", "rate_plan_id": RATE_STE, "date": "2026-10-05"}
    respx.post(f"{API}/restrictions").mock(return_value=ok(warnings=[warning]))

    response = provider_for(channex).push_ari(
        channex, [build_batch(channex, hotel.ste, oct_(5), oct_(6), ("rates",))]
    )

    assert response["warnings"] == [warning]


@pytest.mark.parametrize(
    ("status", "retryable", "code"),
    [
        (429, True, "channex_rate_limited"),
        (503, True, "channex_unavailable"),
        (401, False, "channex_unauthorized"),
        (422, False, "channex_rejected"),
    ],
)
@respx.mock
def test_http_errors_say_whether_a_retry_can_help(hotel, channex, status, retryable, code):
    respx.post(f"{API}/availability").mock(
        return_value=httpx.Response(status, json={"errors": {"code": "x", "title": "Invalid values"}})
    )

    with pytest.raises(ChannelError) as error:
        provider_for(channex).push_ari(
            channex, [build_batch(channex, hotel.dbl, oct_(5), oct_(6), ("availability",))]
        )

    assert (error.value.retryable, error.value.code) == (retryable, code)


def test_missing_credentials_fail_without_retry(hotel):
    real_channex(hotel.prop, api_key="")
    connection = connect(hotel, "channex", room_types=[hotel.dbl], plans=[hotel.plan])

    with pytest.raises(ChannelError) as error:
        provider_for(connection).push_ari(
            connection, [build_batch(connection, hotel.dbl, oct_(5), oct_(6), ("availability",))]
        )

    assert (error.value.retryable, error.value.code) == (False, "integration_misconfigured")


@respx.mock
def test_the_production_environment_uses_the_production_api(hotel):
    real_channex(hotel.prop, environment="production")
    connection = connect(hotel, "channex", room_types=[hotel.dbl], plans=[])
    route = respx.post("https://app.channex.io/api/v1/availability").mock(return_value=ok())

    provider_for(connection).push_ari(
        connection, [build_batch(connection, hotel.dbl, oct_(5), oct_(6), ("availability",))]
    )

    assert route.called


@respx.mock
def test_the_queue_pushes_to_channex_and_logs_warnings(hotel, channex):
    respx.post(f"{API}/availability").mock(return_value=ok())
    respx.post(f"{API}/restrictions").mock(
        return_value=ok(warnings=[{"warning": "rate must be greater than 0"}])
    )
    enqueue_ari(hotel.prop, room_type_ids=[hotel.ste.pk], start=oct_(5), end=oct_(6))

    summary = process_queue(hotel.prop)

    assert summary["sent"] == 1
    log = SyncLog.objects.get(connection=channex)
    assert (log.direction, log.kind, log.status) == ("out", "ari", "warning")
    assert "rate must be greater than 0" in log.message


REVISION = {
    "type": "booking_revision",
    "id": "03dd7198-c5b7-493c-a889-74d0c2211de7",
    "attributes": {
        "id": "03dd7198-c5b7-493c-a889-74d0c2211de7",
        "property_id": CHANNEX_PROPERTY,
        "booking_id": "cfa33f3b-bd32-4b90-8ef9-bde2bfe986cd",
        "unique_id": "BDC-9996013801",
        "revision_id": "03dd7198-c5b7-493c-a889-74d0c2211de7",
        "ota_reservation_code": "9996013801",
        "ota_name": "Booking.com",
        "status": "new",
        "arrival_date": "2026-10-10",
        "departure_date": "2026-10-12",
        "arrival_hour": "18:00",
        "currency": "COP",
        "amount": "736000.00",
        "notes": "Would like a quiet room",
        "customer": {
            "name": "Emma",
            "surname": "de Vries",
            "mail": "emma@example.com",
            "phone": "31612345678",
            "country": "NL",
            "language": "en",
        },
        "rooms": [
            {
                "room_type_id": ROOM_DBL,
                "rate_plan_id": RATE_DBL,
                "checkin_date": "2026-10-10",
                "checkout_date": "2026-10-12",
                "amount": "736000.00",
                "days": {"2026-10-10": "368000.00", "2026-10-11": "368000.00"},
                "occupancy": {"adults": 2, "children": 0, "infants": 0},
            }
        ],
        "inserted_at": "2026-10-01T10:03:29.335485",
    },
}


def feed(*revisions):
    return httpx.Response(
        200, json={"data": list(revisions), "meta": {"total": len(revisions), "page": 1, "limit": 100}}
    )


def revision(status="new", **changes):
    data = json.loads(json.dumps(REVISION))
    data["attributes"].update(status=status, **changes)
    data["id"] = data["attributes"]["revision_id"] = changes.get("revision_id", f"rev-{status}")
    return data


@respx.mock
def test_booking_revisions_are_mapped_to_channel_bookings(hotel, channex):
    route = respx.get(f"{API}/booking_revisions/feed").mock(return_value=feed(REVISION))

    (booking,) = provider_for(channex).fetch_bookings(channex)

    assert route.calls.last.request.url.params["filter[property_id]"] == CHANNEX_PROPERTY
    assert (booking.external_id, booking.status, booking.revision_id) == (
        "cfa33f3b-bd32-4b90-8ef9-bde2bfe986cd",
        "new",
        "03dd7198-c5b7-493c-a889-74d0c2211de7",
    )
    assert booking.guest == {
        "first_name": "Emma",
        "last_name": "de Vries",
        "email": "emma@example.com",
        "phone": "31612345678",
        "country": "NL",
        "language": "en",
    }
    (room,) = booking.rooms
    assert (room.external_room_id, room.external_rate_id, room.checkin, room.checkout, room.adults) == (
        ROOM_DBL,
        RATE_DBL,
        oct_(10),
        oct_(12),
        2,
    )
    assert room.nightly_rates == [
        {"date": oct_(10), "amount": Decimal("368000.00")},
        {"date": oct_(11), "amount": Decimal("368000.00")},
    ]
    assert booking.eta == time(18, 0)
    assert "Booking.com" in booking.notes and "9996013801" in booking.notes


@respx.mock
def test_pulled_bookings_enter_the_pms_and_are_acknowledged(hotel, channex):
    respx.get(f"{API}/booking_revisions/feed").mock(return_value=feed(REVISION))
    ack = respx.post(f"{API}/booking_revisions/{REVISION['id']}/ack").mock(
        return_value=httpx.Response(200, json={"meta": {"message": "Success"}})
    )

    summary = pull_bookings(hotel.prop)

    reservation = Reservation.objects.get(external_id="cfa33f3b-bd32-4b90-8ef9-bde2bfe986cd")
    assert (reservation.source, reservation.channel_code, reservation.eta) == ("ota", "channex", time(18, 0))
    assert reservation.booker.nationality == "NL"
    assert [night["net"] for night in reservation.stays.get().nightly_rates] == ["368000.00", "368000.00"]
    assert ack.called
    assert (summary["created"], summary["acknowledged"]) == (1, 1)


@respx.mock
def test_a_revision_that_fails_is_not_acknowledged_so_it_comes_back(hotel, channex):
    unmapped = revision(revision_id="rev-unmapped")
    unmapped["attributes"]["rooms"][0]["room_type_id"] = "unknown-room"
    respx.get(f"{API}/booking_revisions/feed").mock(return_value=feed(unmapped))
    ack = respx.post(url__regex=rf"{API}/booking_revisions/.+/ack")

    summary = pull_bookings(hotel.prop)

    assert not ack.called
    assert (summary["failed"], summary["acknowledged"]) == (1, 0)
    assert Alert.objects.filter(kind="channel_import_failed", resolved_at__isnull=True).exists()


@respx.mock
def test_modification_and_cancellation_revisions_follow_the_booking(hotel, channex):
    route = respx.get(f"{API}/booking_revisions/feed")
    respx.post(url__regex=rf"{API}/booking_revisions/.+/ack").mock(return_value=httpx.Response(200, json={}))
    route.mock(return_value=feed(REVISION))
    pull_bookings(hotel.prop)

    longer = revision("modified", departure_date="2026-10-13")
    longer["attributes"]["rooms"][0].update(checkout_date="2026-10-13")
    route.mock(return_value=feed(longer))
    pull_bookings(hotel.prop)
    reservation = Reservation.objects.get(external_id=REVISION["attributes"]["booking_id"])
    assert reservation.stays.get().checkout_date == oct_(13)

    route.mock(return_value=feed(revision("cancelled")))
    summary = pull_bookings(hotel.prop)
    reservation.refresh_from_db()
    assert (reservation.status, summary["cancelled"]) == ("cancelled", 1)


@respx.mock
def test_an_unreachable_feed_is_logged_and_alerted(hotel, channex):
    respx.get(f"{API}/booking_revisions/feed").mock(return_value=httpx.Response(502))

    summary = pull_bookings(hotel.prop)

    assert summary["errors"] == 1
    assert SyncLog.objects.filter(connection=channex, direction="in", status="error").exists()
    alert = Alert.objects.get(kind="channel_pull_failed", resolved_at__isnull=True)
    assert alert.dedupe_key == f"distribution:pull:{channex.pk}"


@respx.mock
def test_test_connection_lists_the_properties_of_the_key(hotel, channex):
    respx.get(f"{API}/properties").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "type": "property",
                        "id": CHANNEX_PROPERTY,
                        "attributes": {"title": "Casa Aurora", "currency": "COP"},
                    }
                ],
                "meta": {"page": 1, "limit": 100, "total": 1},
            },
        )
    )

    good, message = provider_for(channex).test_connection(channex)

    assert good and "Casa Aurora" in message


@respx.mock
def test_test_connection_fails_when_the_property_is_not_visible(hotel, channex):
    respx.get(f"{API}/properties").mock(
        return_value=httpx.Response(200, json={"data": [], "meta": {"total": 0}})
    )

    good, message = provider_for(channex).test_connection(channex)

    assert not good and CHANNEX_PROPERTY in message


@respx.mock
def test_the_remote_catalog_lists_channex_room_types_and_rate_plans(hotel, channex):
    respx.get(f"{API}/room_types/options").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "type": "room_type",
                        "id": ROOM_DBL,
                        "attributes": {"id": ROOM_DBL, "title": "Double", "default_occupancy": 2},
                    }
                ]
            },
        )
    )
    respx.get(f"{API}/rate_plans/options").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "type": "rate_plan",
                        "id": RATE_DBL,
                        "attributes": {
                            "id": RATE_DBL,
                            "title": "BAR",
                            "room_type_id": ROOM_DBL,
                            "currency": "COP",
                            "sell_mode": "per_room",
                            "occupancy": 2,
                        },
                    }
                ]
            },
        )
    )

    catalog = provider_for(channex).remote_catalog(channex)

    assert catalog == {
        "rooms": [{"id": ROOM_DBL, "title": "Double"}],
        "rates": [{"id": RATE_DBL, "title": "BAR", "room_id": ROOM_DBL, "currency": "COP"}],
    }
