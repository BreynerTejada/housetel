"""Automations of distribution (spec §6): `distribution.push_ari` (every minute, sends the ARI queue),
`distribution.pull_ical` (every 15 minutes, imports remote calendars) and `distribution.pull_bookings`
(every 5 minutes, downloads the bookings of pull channels such as Channex)."""

import pytest
from celery.schedules import crontab

from apps.bookings.models import Reservation
from apps.bookings.tests.helpers import oct_
from apps.core import automation
from apps.distribution.models import AriUpdate, SimOtaInventory
from apps.distribution.services import simulator
from apps.distribution.services.queue import enqueue_ari, full_sync
from apps.distribution.tests.factories import ChannelConnectionFactory, RoomMappingFactory, connect

pytestmark = pytest.mark.django_db


def test_the_automations_are_registered_with_their_schedules():
    push, ical, bookings = (
        automation.get(code)
        for code in ("distribution.push_ari", "distribution.pull_ical", "distribution.pull_bookings")
    )

    assert push.schedule == crontab(minute="*")
    assert ical.schedule == crontab(minute="*/15")
    assert bookings.schedule == crontab(minute="*/5")
    assert all(item.app == "distribution" and item.default_enabled for item in (push, ical, bookings))
    assert all(
        item.name_en and item.description_es and item.description_en for item in (push, ical, bookings)
    )


def test_push_ari_sends_what_is_queued(hotel):
    connection = connect(hotel, "booksim")
    enqueue_ari(hotel.prop, room_type_ids=[hotel.dbl.pk], start=oct_(5), end=oct_(7))

    run = automation.run("distribution.push_ari", hotel.prop)

    assert (run.status, run.details["sent"]) == ("success", 1)
    assert SimOtaInventory.objects.filter(connection=connection).count() == 2
    assert AriUpdate.objects.get().status == "sent"


def test_push_ari_with_nothing_queued_is_skipped(hotel):
    connect(hotel, "booksim")

    run = automation.run("distribution.push_ari", hotel.prop)

    assert run.status == "skipped"


def test_push_ari_reports_failures_as_partial(hotel, monkeypatch):
    from apps.distribution.errors import ChannelError
    from apps.distribution.providers import SimulatedOtaProvider

    connect(hotel, "booksim")
    enqueue_ari(hotel.prop, room_type_ids=[hotel.dbl.pk], start=oct_(5), end=oct_(7))
    monkeypatch.setattr(
        SimulatedOtaProvider, "push_ari", lambda *args: (_ for _ in ()).throw(ChannelError("caído"))
    )

    run = automation.run("distribution.push_ari", hotel.prop)

    assert (run.status, run.details["retrying"]) == ("partial", 1)


def test_pull_ical_imports_the_calendars(hotel, organization):
    from apps.bookings.services.reservations import create_reservation
    from apps.bookings.tests.helpers import build_hotel, guest_input, stay_request
    from apps.bookings.types import ReservationRequest
    from apps.core.tests.factories import PropertyFactory

    partner = build_hotel(PropertyFactory(organization=organization))
    exported = RoomMappingFactory(
        connection=ChannelConnectionFactory(property=partner.prop, channel_code="ical", name="Export"),
        room_type=partner.ste,
        external_room_id="",
    )
    create_reservation(
        ReservationRequest(
            property=partner.prop,
            booker=guest_input(),
            stays=[stay_request(partner, oct_(10), oct_(12), room_type=partner.ste)],
            source="phone",
        )
    )
    RoomMappingFactory(
        connection=ChannelConnectionFactory(property=hotel.prop, channel_code="ical", name="Aliado"),
        room_type=hotel.dbl,
        external_room_id="",
        ical_import_url=f"https://housetel.example/api/v1/public/distribution/ical/{exported.ical_export_token}.ics",
    )

    run = automation.run("distribution.pull_ical", hotel.prop)

    assert (run.status, run.details["created"], run.details["calendars"]) == ("success", 1, 1)
    assert Reservation.objects.filter(property=hotel.prop, channel_code="ical").count() == 1


def test_pull_ical_without_calendars_is_skipped(hotel):
    run = automation.run("distribution.pull_ical", hotel.prop)

    assert run.status == "skipped"


def test_pull_bookings_downloads_the_simulated_channex_feed(hotel):
    channex = connect(hotel, "channex")
    full_sync(channex)
    simulator.create_booking(
        channex,
        external_room_id="CH-DBL",
        external_rate_id="CH-BAR",
        checkin=oct_(10),
        checkout=oct_(12),
        adults=2,
    )

    run = automation.run("distribution.pull_bookings", hotel.prop)

    assert (run.status, run.details["created"], run.details["acknowledged"]) == ("success", 1, 1)
    assert Reservation.objects.filter(property=hotel.prop, channel_code="channex").count() == 1


def test_pull_bookings_without_pull_channels_is_skipped(hotel):
    connect(hotel, "booksim")

    run = automation.run("distribution.pull_bookings", hotel.prop)

    assert run.status == "skipped"
