"""ARI queue: inventory/rates signals enqueue one pending update per (connection, category), coalesced."""

from datetime import timedelta

import pytest

from apps.bookings.tests.helpers import oct_
from apps.core import signals
from apps.distribution.models import AriUpdate, ChannelConnection
from apps.distribution.tests.factories import connect

pytestmark = pytest.mark.django_db


def emit(capture, signal, **kwargs):
    with capture(execute=True):
        signals.send_on_commit(signal, **kwargs)


def inventory_changed(capture, hotel, room_types, start, end):
    emit(
        capture,
        signals.inventory_changed,
        property=hotel.prop,
        room_type_ids=[room_type.pk for room_type in room_types],
        start=start,
        end=end,
    )


def rates_changed(capture, hotel, room_types, plans, start, end):
    emit(
        capture,
        signals.rates_changed,
        property=hotel.prop,
        room_type_ids=[room_type.pk for room_type in room_types],
        rate_plan_ids=[plan.pk for plan in plans],
        start=start,
        end=end,
    )


def test_changes_to_a_category_coalesce_into_one_pending_update(
    hotel, booksim, django_capture_on_commit_callbacks
):
    capture = django_capture_on_commit_callbacks
    inventory_changed(capture, hotel, [hotel.dbl], oct_(5), oct_(8))
    inventory_changed(capture, hotel, [hotel.dbl], oct_(7), oct_(12))
    rates_changed(capture, hotel, [hotel.dbl], [hotel.plan], oct_(20), oct_(22))

    update = AriUpdate.objects.get(connection=booksim)
    assert (update.room_type_id, update.start, update.end, update.status) == (
        hotel.dbl.pk,
        oct_(5),
        oct_(22),
        AriUpdate.Status.PENDING,
    )
    assert sorted(update.kinds) == ["availability", "rates", "restrictions"]
    assert update.property_id == hotel.prop.pk


def test_each_connection_and_category_gets_its_own_update(hotel, booksim, django_capture_on_commit_callbacks):
    airsim = connect(hotel, "airsim", room_types=[hotel.dbl])
    inventory_changed(django_capture_on_commit_callbacks, hotel, [hotel.dbl, hotel.ste], oct_(3), oct_(4))

    rows = sorted(
        (update.connection.channel_code, update.room_type.code)
        for update in AriUpdate.objects.select_related("connection", "room_type")
    )
    assert rows == [("airsim", "DBL"), ("booksim", "DBL"), ("booksim", "STE")]
    assert airsim.ari_updates.count() == 1


def test_unmapped_categories_paused_and_ical_connections_enqueue_nothing(
    hotel, booksim, django_capture_on_commit_callbacks
):
    connect(hotel, "airsim", status=ChannelConnection.Status.PAUSED)
    connect(hotel, "ical")
    inventory_changed(django_capture_on_commit_callbacks, hotel, [hotel.dorm_type], oct_(3), oct_(4))
    assert not AriUpdate.objects.exists()

    inventory_changed(django_capture_on_commit_callbacks, hotel, [hotel.ste], oct_(3), oct_(4))
    assert list(AriUpdate.objects.values_list("connection__channel_code", flat=True)) == ["booksim"]


def test_open_ranges_become_the_sync_horizon_and_the_past_is_ignored(
    hotel, booksim, django_capture_on_commit_callbacks
):
    capture = django_capture_on_commit_callbacks
    inventory_changed(capture, hotel, [hotel.dbl], oct_(1) - timedelta(days=30), oct_(1))
    assert not AriUpdate.objects.exists()

    inventory_changed(capture, hotel, [hotel.dbl], None, None)
    update = AriUpdate.objects.get()
    assert (update.start, update.end) == (oct_(1), oct_(1) + timedelta(days=365))


def test_an_update_already_being_sent_is_not_extended(hotel, booksim, django_capture_on_commit_callbacks):
    capture = django_capture_on_commit_callbacks
    inventory_changed(capture, hotel, [hotel.dbl], oct_(5), oct_(6))
    AriUpdate.objects.update(status=AriUpdate.Status.SENDING)

    inventory_changed(capture, hotel, [hotel.dbl], oct_(9), oct_(10))

    assert sorted(AriUpdate.objects.values_list("status", "start")) == [
        (AriUpdate.Status.PENDING, oct_(9)),
        (AriUpdate.Status.SENDING, oct_(5)),
    ]


def test_rate_changes_of_unmapped_plans_are_ignored(hotel, booksim, django_capture_on_commit_callbacks):
    from apps.rates.tests.factories import RatePlanFactory

    other_plan = RatePlanFactory(property=hotel.prop, code="CORP", room_types=[hotel.dbl])
    rates_changed(django_capture_on_commit_callbacks, hotel, [hotel.dbl], [other_plan], oct_(3), oct_(4))
    assert not AriUpdate.objects.exists()


def test_nothing_is_enqueued_while_seeding(hotel, booksim, django_capture_on_commit_callbacks):
    with signals.seeding():
        inventory_changed(django_capture_on_commit_callbacks, hotel, [hotel.dbl], oct_(3), oct_(4))
    assert not AriUpdate.objects.exists()


def test_a_debounced_push_is_scheduled_once(
    hotel, booksim, django_capture_on_commit_callbacks, scheduled_pushes
):
    capture = django_capture_on_commit_callbacks
    inventory_changed(capture, hotel, [hotel.dbl], oct_(3), oct_(4))
    inventory_changed(capture, hotel, [hotel.ste], oct_(3), oct_(4))

    assert scheduled_pushes == [((), {"args": [str(hotel.prop.pk)], "countdown": 5})]
