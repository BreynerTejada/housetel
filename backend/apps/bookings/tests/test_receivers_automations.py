"""Receivers and automations of bookings (plan B2b):

- `payment_received` → an approved payment on a tentative reservation confirms it (hold cleared,
  `reservation_updated` with `{"status": ("tentative", "confirmed")}`); on a cancelled one it raises an alert.
- `bookings.release_expired_tentative` (every 15 min) cancels expired holds without fee.
- `bookings.auto_assign_rooms` (06:00) assigns today's and tomorrow's arrivals.
- `bookings.inventory_reconcile` (04:00) rebuilds InventoryDay and raises `inventory_drift` when it had to
  fix rows.
"""

from decimal import Decimal

import pytest
from celery.schedules import crontab
from django.db.models.signals import post_save
from freezegun import freeze_time

from apps.bookings.models import InventoryDay, Reservation, Stay
from apps.bookings.services.inventory import rebuild_inventory
from apps.bookings.services.reservations import cancel_reservation, confirm_reservation
from apps.bookings.tests.helpers import book, oct_
from apps.bookings.types import InvalidStateError
from apps.core import automation
from apps.core.models import Alert, AuditEvent, AutomationRun
from apps.finance.services import get_or_create_folio, record_payment
from apps.rates.tests.factories import CancellationPolicyFactory

pytestmark = pytest.mark.django_db


def pay(reservation, *, status="approved"):
    folio = get_or_create_folio(reservation)
    return record_payment(
        folio, amount=Decimal("100000"), method="bank_transfer", status=status, reference="T-1"
    )


class TestConfirmation:
    def test_confirm_reservation_clears_the_hold(
        self, hotel, owner, django_capture_on_commit_callbacks, signal_log
    ):
        reservation = book(hotel, oct_(5), oct_(7), status="tentative")

        with django_capture_on_commit_callbacks(execute=True):
            confirm_reservation(reservation, actor=owner)

        reservation.refresh_from_db()
        assert (reservation.status, reservation.hold_expires_at) == ("confirmed", None)
        assert set(Stay.objects.filter(reservation=reservation).values_list("status", flat=True)) == {
            "confirmed"
        }
        (updated,) = signal_log.of("reservation_updated")
        assert updated["changes"] == {"status": ("tentative", "confirmed")}
        assert AuditEvent.objects.get(action="bookings.reservation_confirmed").actor == owner

    def test_only_tentative_reservations_can_be_confirmed(self, hotel):
        with pytest.raises(InvalidStateError):
            confirm_reservation(book(hotel, oct_(5), oct_(7)))


class TestPaymentReceived:
    def test_an_approved_payment_confirms_a_tentative_reservation(
        self, hotel, django_capture_on_commit_callbacks
    ):
        reservation = book(hotel, oct_(5), oct_(7), status="tentative")
        with django_capture_on_commit_callbacks(execute=True):
            pay(reservation)
        reservation.refresh_from_db()
        assert (reservation.status, reservation.hold_expires_at) == ("confirmed", None)
        assert AuditEvent.objects.get(action="bookings.reservation_confirmed").source == "system"

    def test_a_pending_payment_does_not_confirm(self, hotel, django_capture_on_commit_callbacks):
        reservation = book(hotel, oct_(5), oct_(7), status="tentative")
        with django_capture_on_commit_callbacks(execute=True):
            pay(reservation, status="pending")
        assert Reservation.objects.get(pk=reservation.pk).status == "tentative"

    def test_a_confirmed_reservation_is_left_as_is(
        self, hotel, django_capture_on_commit_callbacks, signal_log
    ):
        reservation = book(hotel, oct_(5), oct_(7))
        with django_capture_on_commit_callbacks(execute=True):
            pay(reservation)
        assert signal_log.of("reservation_updated") == []

    def test_a_payment_after_the_cancellation_raises_an_alert(
        self, hotel, django_capture_on_commit_callbacks
    ):
        reservation = book(hotel, oct_(5), oct_(7), status="tentative")
        cancel_reservation(reservation, reason="Retención vencida", source="automation")
        with django_capture_on_commit_callbacks(execute=True):
            pay(reservation)
        alert = Alert.objects.get(kind="payment_after_cancellation", resolved_at__isnull=True)
        assert reservation.code in alert.title
        assert alert.data["credit"] == "100000.00"  # what the guest has in favor
        assert Reservation.objects.get(pk=reservation.pk).status == "cancelled"

    def test_paying_the_cancellation_fee_is_not_an_alert(self, hotel, django_capture_on_commit_callbacks):
        """Collecting the penalty of a cancelled reservation is the normal flow: nothing to refund."""
        hotel.plan.cancellation_policy = CancellationPolicyFactory(property=hotel.prop, non_refundable=True)
        hotel.plan.save()
        reservation = book(hotel, oct_(5), oct_(7))
        cancel_reservation(reservation, reason="No viaja")
        folio = get_or_create_folio(reservation)

        with django_capture_on_commit_callbacks(execute=True):
            record_payment(folio, amount=Decimal("761600"), method="bank_transfer", reference="FEE-1")

        assert not Alert.objects.filter(kind="payment_after_cancellation").exists()

    def test_paying_more_than_the_cancellation_fee_is_an_alert(
        self, hotel, django_capture_on_commit_callbacks
    ):
        hotel.plan.cancellation_policy = CancellationPolicyFactory(property=hotel.prop, non_refundable=True)
        hotel.plan.save()
        reservation = book(hotel, oct_(5), oct_(7))
        cancel_reservation(reservation, reason="No viaja")
        folio = get_or_create_folio(reservation)

        with django_capture_on_commit_callbacks(execute=True):
            record_payment(folio, amount=Decimal("800000"), method="bank_transfer", reference="FEE-2")

        alert = Alert.objects.get(kind="payment_after_cancellation", resolved_at__isnull=True)
        assert alert.data["credit"] == "38400.00"


class TestAutomations:
    def test_are_registered_with_their_schedules(self):
        assert automation.get("bookings.auto_assign_rooms").schedule == crontab(hour=6, minute=0)
        assert automation.get("bookings.release_expired_tentative").schedule == crontab(minute="*/15")
        assert automation.get("bookings.inventory_reconcile").schedule == crontab(hour=4, minute=0)

    def test_expired_holds_are_released_without_fee(self, hotel):
        with freeze_time("2026-10-01 12:00:00+00:00"):
            expired = book(hotel, oct_(5), oct_(7), status="tentative", hold_minutes=20)
            holding = book(hotel, oct_(5), oct_(7), status="tentative", hold_minutes=120)
        with freeze_time("2026-10-01 12:30:00+00:00"):
            run = automation.run("bookings.release_expired_tentative", hotel.prop)

        assert run.status == "success"
        assert run.details == {"released": [expired.code]}
        expired.refresh_from_db()
        assert (expired.status, expired.cancellation_fee) == ("cancelled", Decimal("0"))
        assert Reservation.objects.get(pk=holding.pk).status == "tentative"
        assert AuditEvent.objects.get(action="bookings.reservation_cancelled").source == "automation"
        assert InventoryDay.objects.get(room_type=hotel.dbl, date=oct_(5)).sold_units == 1

    def test_a_hold_paid_while_the_run_is_going_is_not_released(self, hotel):
        """The run lists the expired holds, then cancels them one by one; a payment can confirm one of them in
        between. Each one is checked again under lock, so a confirmed (paid) reservation is never
        cancelled."""
        with freeze_time("2026-10-01 12:00:00+00:00"):
            first = book(hotel, oct_(5), oct_(7), status="tentative", hold_minutes=10)
            paid = book(hotel, oct_(5), oct_(7), status="tentative", hold_minutes=20)

        def payment_lands(sender, instance, **kwargs):
            """While the run cancels `first`, the payment of `paid` confirms it."""
            if instance.pk == first.pk and instance.status == "cancelled":
                confirm_reservation(Reservation.objects.get(pk=paid.pk), source="system")

        post_save.connect(payment_lands, sender=Reservation, dispatch_uid="test-payment-lands")
        try:
            with freeze_time("2026-10-01 12:30:00+00:00"):
                run = automation.run("bookings.release_expired_tentative", hotel.prop)
        finally:
            post_save.disconnect(sender=Reservation, dispatch_uid="test-payment-lands")

        paid.refresh_from_db()
        assert (paid.status, paid.cancellation_fee) == ("confirmed", Decimal("0"))
        assert Reservation.objects.get(pk=first.pk).status == "cancelled"
        assert (run.status, run.details["released"]) == ("success", [first.code])
        assert InventoryDay.objects.get(room_type=hotel.dbl, date=oct_(5)).sold_units == 1

    def test_auto_assign_covers_today_and_tomorrow(self, hotel):
        today = book(hotel, oct_(1), oct_(2)).stays.get()
        tomorrow = book(hotel, oct_(2), oct_(3)).stays.get()
        later = book(hotel, oct_(3), oct_(4)).stays.get()

        run = automation.run("bookings.auto_assign_rooms", hotel.prop)

        assigned = {stay.pk for stay in Stay.objects.filter(room__isnull=False)}
        assert assigned == {today.pk, tomorrow.pk} and later.pk not in assigned
        assert (run.status, run.details["assigned"]) == ("success", 2)

    def test_inventory_reconcile_repairs_drift_and_alerts_once(self, hotel):
        book(hotel, oct_(3), oct_(5))
        rebuild_inventory(hotel.prop)
        InventoryDay.objects.filter(room_type=hotel.dbl, date=oct_(3)).update(sold_units=3)

        run = automation.run("bookings.inventory_reconcile", hotel.prop)

        assert (run.status, run.details["updated"]) == ("success", 1)
        assert InventoryDay.objects.get(room_type=hotel.dbl, date=oct_(3)).sold_units == 1
        alert = Alert.objects.get(kind="inventory_drift", resolved_at__isnull=True)
        assert alert.data["drift"][0]["sold_units"] == [3, 1]

        automation.run("bookings.inventory_reconcile", hotel.prop)
        assert not Alert.objects.filter(kind="inventory_drift", resolved_at__isnull=True).exists()
        assert AutomationRun.objects.filter(code="bookings.inventory_reconcile").count() == 2
