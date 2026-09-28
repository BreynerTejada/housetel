"""Pushing the ARI queue: providers receive the batches, failures back off and finally alert."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from freezegun import freeze_time

from apps.bookings.tests.helpers import oct_
from apps.core.models import Alert, AuditEvent
from apps.distribution.errors import ChannelError
from apps.distribution.models import AriUpdate, ChannelConnection, SimOtaInventory, SyncLog
from apps.distribution.providers import SimulatedOtaProvider
from apps.distribution.services.queue import enqueue_ari, full_sync, process_queue

pytestmark = pytest.mark.django_db

T0 = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)


def cells(connection) -> list[tuple]:
    return list(
        SimOtaInventory.objects.filter(connection=connection)
        .order_by("external_room_id", "external_rate_id", "date")
        .values_list("external_room_id", "external_rate_id", "date", "available", "price", "stop_sell")
    )


def test_pending_updates_reach_the_simulated_ota(hotel, booksim):
    enqueue_ari(hotel.prop, room_type_ids=[hotel.dbl.pk], start=oct_(5), end=oct_(7))

    summary = process_queue(hotel.prop)

    assert cells(booksim) == [
        ("BS-DBL", "BS-BAR", oct_(5), 3, Decimal("320000.00"), False),
        ("BS-DBL", "BS-BAR", oct_(6), 3, Decimal("320000.00"), False),
    ]
    update = AriUpdate.objects.get()
    assert (update.status, update.attempts, update.last_error) == (AriUpdate.Status.SENT, 1, "")
    assert update.sent_at is not None
    booksim.refresh_from_db()
    assert booksim.last_sync_at is not None
    log = SyncLog.objects.get(connection=booksim)
    assert (log.direction, log.kind, log.status) == ("out", "ari", "success")
    assert summary["sent"] == 1


def test_a_new_push_overwrites_what_the_ota_had(hotel, booksim):
    from apps.rates.models import RoomTypeRateDefaults

    enqueue_ari(hotel.prop, room_type_ids=[hotel.dbl.pk], start=oct_(5), end=oct_(6))
    process_queue(hotel.prop)
    RoomTypeRateDefaults.objects.filter(room_type=hotel.dbl).update(price=Decimal("300000"))
    enqueue_ari(hotel.prop, room_type_ids=[hotel.dbl.pk], start=oct_(5), end=oct_(6))
    process_queue(hotel.prop)

    assert cells(booksim) == [("BS-DBL", "BS-BAR", oct_(5), 3, Decimal("300000.00"), False)]


def test_a_failed_push_backs_off_then_fails_alerts_and_recovers(hotel, booksim, monkeypatch):
    def unavailable(self, connection, batches):
        raise ChannelError("La OTA no responde")

    enqueue_ari(hotel.prop, room_type_ids=[hotel.dbl.pk], start=oct_(5), end=oct_(6))
    update = AriUpdate.objects.get()
    with monkeypatch.context() as ota_down:
        ota_down.setattr(SimulatedOtaProvider, "push_ari", unavailable)

        with freeze_time(T0):
            process_queue(hotel.prop)
        update.refresh_from_db()
        assert (update.status, update.attempts, update.last_error) == ("pending", 1, "La OTA no responde")
        assert update.next_attempt_at == T0 + timedelta(seconds=30)

        with freeze_time(T0 + timedelta(seconds=10)):  # not due yet
            process_queue(hotel.prop)
        update.refresh_from_db()
        assert update.attempts == 1

        moments = [T0 + timedelta(seconds=30), T0 + timedelta(seconds=150), T0 + timedelta(seconds=630)]
        for moment, wait in zip(moments, (120, 480, 1800), strict=True):
            with freeze_time(moment):
                process_queue(hotel.prop)
            update.refresh_from_db()
            assert update.next_attempt_at == moment + timedelta(seconds=wait)
        assert update.attempts == 4 and not Alert.objects.exists()

        with freeze_time(update.next_attempt_at):
            process_queue(hotel.prop)
    update.refresh_from_db()
    booksim.refresh_from_db()
    assert (update.status, update.attempts) == ("failed", 5)
    assert (booksim.status, booksim.last_error) == ("error", "La OTA no responde")
    alert = Alert.objects.get(resolved_at__isnull=True)
    assert (alert.kind, alert.severity, alert.dedupe_key) == (
        "channel_sync_failed",
        "critical",
        f"distribution:ari:{booksim.pk}",
    )
    assert SyncLog.objects.filter(connection=booksim, status="error").count() == 5

    # the OTA is back: the next push succeeds and clears the error
    enqueue_ari(hotel.prop, room_type_ids=[hotel.dbl.pk], start=oct_(5), end=oct_(6))
    process_queue(hotel.prop)
    booksim.refresh_from_db()
    assert (booksim.status, booksim.last_error) == ("active", "")
    assert not Alert.objects.filter(resolved_at__isnull=True).exists()


def test_paused_connections_keep_their_queue(hotel, booksim):
    enqueue_ari(hotel.prop, room_type_ids=[hotel.dbl.pk], start=oct_(5), end=oct_(6))
    ChannelConnection.objects.filter(pk=booksim.pk).update(status=ChannelConnection.Status.PAUSED)

    process_queue(hotel.prop)

    assert AriUpdate.objects.get().status == "pending"
    assert not SimOtaInventory.objects.exists()


def test_updates_left_sending_by_a_crashed_push_are_sent_again(hotel, booksim):
    enqueue_ari(hotel.prop, room_type_ids=[hotel.dbl.pk], start=oct_(5), end=oct_(6))
    AriUpdate.objects.update(status="sending", updated_at=T0 - timedelta(minutes=30))

    with freeze_time(T0):
        process_queue(hotel.prop)

    assert AriUpdate.objects.get().status == "sent"
    assert len(cells(booksim)) == 1


def test_full_sync_sends_the_whole_horizon_now(hotel, booksim, owner):
    summary = full_sync(booksim, actor=owner)

    assert summary["sent"] == 2  # DBL and STE
    assert SimOtaInventory.objects.filter(connection=booksim).count() == 2 * 365
    last = SimOtaInventory.objects.filter(connection=booksim).latest("date")
    assert last.date == oct_(1) + timedelta(days=364)
    event = AuditEvent.objects.get(action="distribution.full_sync")
    assert (event.actor, event.target_id) == (owner, str(booksim.pk))


def test_full_sync_of_a_paused_connection_is_refused(hotel, booksim):
    from apps.core.errors import ConflictError

    booksim.status = ChannelConnection.Status.PAUSED
    booksim.save(update_fields=["status"])

    with pytest.raises(ConflictError) as error:
        full_sync(booksim)
    assert error.value.code == "connection_paused"


def test_a_deleted_plan_is_closed_on_the_channel_even_without_rates_changed(
    hotel, booksim, django_capture_on_commit_callbacks
):
    """Deleting a rate plan emits no `rates_changed` (B2a): the channel must still stop selling it."""
    from apps.rates.tests.factories import DerivedRatePlanFactory

    derived = DerivedRatePlanFactory(
        property=hotel.prop, parent=hotel.plan, code="NR", room_types=[hotel.dbl]
    )
    booksim.rate_mappings.create(rate_plan=derived, external_rate_id="BS-NR")
    full_sync(booksim)
    cell = {"external_room_id": "BS-DBL", "external_rate_id": "BS-NR", "date": oct_(5)}
    assert SimOtaInventory.objects.get(**cell).stop_sell is False

    with django_capture_on_commit_callbacks(execute=True):
        derived.delete()
    process_queue(hotel.prop)

    closed = SimOtaInventory.objects.get(**cell)
    assert (closed.stop_sell, closed.price) == (True, None)
    assert booksim.rate_mappings.get(external_rate_id="BS-NR").rate_plan is None
