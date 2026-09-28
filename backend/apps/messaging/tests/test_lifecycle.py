"""Automatic guest-lifecycle messages: receivers (confirmation, cancellation) and the scheduled automation
`messaging.lifecycle_dispatch` (pre-arrival, arrival day, post-stay, payment reminder). Idempotent per
(reservation, event) through LifecycleDispatch."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.core import mail
from django.utils import timezone
from freezegun import freeze_time

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core import automation
from apps.core.signals import (
    reservation_cancelled,
    reservation_created,
    reservation_updated,
    seeding,
    send_on_commit,
)
from apps.guests.tests.factories import GuestFactory
from apps.messaging.lifecycle import dispatch_event
from apps.messaging.models import LifecycleDispatch, Message
from apps.messaging.tests.factories import LifecycleRuleFactory

pytestmark = pytest.mark.django_db

BOGOTA = ZoneInfo("America/Bogota")
TODAY = date(2026, 10, 6)


def _at(hour: int, minute: int = 0, day: date = TODAY):
    """Freeze the clock at a local (Bogotá) time."""
    return freeze_time(datetime.combine(day, time(hour, minute), tzinfo=BOGOTA))


@pytest.fixture
def guest(prop):
    return GuestFactory(organization=prop.organization, email="ana@example.com", phone="+573001112233")


def _reservation(prop, guest, **kwargs):
    values = {"property": prop, "booker": guest, "checkin_date": TODAY + timedelta(days=10)}
    values.update(kwargs)
    values.setdefault("checkout_date", values["checkin_date"] + timedelta(days=2))
    return ReservationFactory(**values)


def _emit(capture, signal, **kwargs):
    with capture(execute=True):
        send_on_commit(signal, **kwargs)


class TestReceivers:
    def test_a_confirmed_booking_gets_its_confirmation_once(
        self, prop, guest, django_capture_on_commit_callbacks
    ):
        LifecycleRuleFactory(property=prop, event="confirmation", channels=["email", "whatsapp"])
        reservation = _reservation(prop, guest, status="confirmed")

        _emit(django_capture_on_commit_callbacks, reservation_created, reservation=reservation)
        _emit(
            django_capture_on_commit_callbacks,
            reservation_updated,
            reservation=reservation,
            changes={"status": ("tentative", "confirmed")},
        )

        assert sorted(Message.objects.values_list("channel", "template_code")) == [
            ("email", "confirmation"),
            ("whatsapp", "confirmation"),
        ]
        dispatch = LifecycleDispatch.objects.get()
        assert (dispatch.reservation, dispatch.event, dispatch.status) == (
            reservation,
            "confirmation",
            "sent",
        )

    def test_a_tentative_booking_is_confirmed_when_it_is_paid(
        self, prop, guest, django_capture_on_commit_callbacks
    ):
        reservation = _reservation(prop, guest, status="tentative")
        _emit(django_capture_on_commit_callbacks, reservation_created, reservation=reservation)
        assert Message.objects.count() == 0

        reservation.status = "confirmed"
        reservation.save()
        _emit(
            django_capture_on_commit_callbacks,
            reservation_updated,
            reservation=reservation,
            changes={"status": ("tentative", "confirmed")},
        )
        assert set(Message.objects.values_list("template_code", flat=True)) == {"confirmation"}

    def test_other_changes_send_nothing(self, prop, guest, django_capture_on_commit_callbacks):
        reservation = _reservation(prop, guest, status="confirmed")
        _emit(
            django_capture_on_commit_callbacks,
            reservation_updated,
            reservation=reservation,
            changes={"notes": ("", "Llega tarde")},
        )
        assert Message.objects.count() == 0

    def test_cancelling_a_confirmed_booking_tells_the_guest(
        self, prop, guest, django_capture_on_commit_callbacks
    ):
        reservation = _reservation(prop, guest, status="cancelled", cancellation_fee=Decimal("320000"))
        _emit(django_capture_on_commit_callbacks, reservation_cancelled, reservation=reservation)
        (email,) = mail.outbox
        assert reservation.code in email.subject and "$ 320.000" in email.body

    def test_an_expired_hold_is_released_silently(self, prop, guest, django_capture_on_commit_callbacks):
        reservation = _reservation(prop, guest, status="cancelled", hold_expires_at=timezone.now())
        _emit(django_capture_on_commit_callbacks, reservation_cancelled, reservation=reservation)
        assert mail.outbox == [] and Message.objects.count() == 0

    def test_the_demo_seed_sends_nothing(self, prop, guest, django_capture_on_commit_callbacks):
        reservation = _reservation(prop, guest, status="confirmed")
        with seeding():
            _emit(django_capture_on_commit_callbacks, reservation_created, reservation=reservation)
            _emit(django_capture_on_commit_callbacks, reservation_cancelled, reservation=reservation)
        assert Message.objects.count() == 0 and LifecycleDispatch.objects.count() == 0

    def test_a_disabled_rule_sends_nothing(self, prop, guest, django_capture_on_commit_callbacks):
        LifecycleRuleFactory(property=prop, event="confirmation", enabled=False)
        reservation = _reservation(prop, guest, status="confirmed")
        _emit(django_capture_on_commit_callbacks, reservation_created, reservation=reservation)
        assert Message.objects.count() == 0 and LifecycleDispatch.objects.count() == 0

    def test_without_contact_data_the_dispatch_is_skipped(self, prop, django_capture_on_commit_callbacks):
        silent = GuestFactory(organization=prop.organization, email="", phone="")
        reservation = _reservation(prop, silent, status="confirmed")
        _emit(django_capture_on_commit_callbacks, reservation_created, reservation=reservation)
        assert LifecycleDispatch.objects.get().status == "skipped" and Message.objects.count() == 0


class TestDispatch:
    def test_a_delivery_failure_is_recorded_and_can_be_retried(self, prop, guest, monkeypatch):
        from apps.messaging import providers

        LifecycleRuleFactory(property=prop, event="confirmation", channels=["email"])
        reservation = _reservation(prop, guest, status="confirmed")
        monkeypatch.setattr(
            providers.SmtpEmailProvider,
            "send_email",
            lambda self, **kwargs: providers.DeliveryResult("failed", error="SMTP caído"),
        )
        dispatch = dispatch_event(reservation, "confirmation")
        assert (dispatch.status, dispatch.attempts) == ("failed", 1) and "SMTP caído" in dispatch.detail
        assert dispatch_event(reservation, "confirmation") is None  # never twice on its own

        monkeypatch.undo()
        run = automation.run("messaging.lifecycle_dispatch", prop)  # retries do not wait for the send hour
        dispatch.refresh_from_db()
        assert (dispatch.status, dispatch.attempts, run.status) == ("sent", 2, "success")


class TestAutomation:
    def test_it_is_registered_every_ten_minutes(self):
        item = automation.get("messaging.lifecycle_dispatch")
        assert (item.app, item.scope) == ("messaging", "property")
        assert str(item.schedule._orig_minute) == "*/10"

    def test_pre_arrival_goes_out_from_nine_with_the_checkin_link(self, prop, guest):
        reservation = _reservation(prop, guest, status="confirmed", checkin_date=TODAY + timedelta(days=3))
        with _at(8, 50):
            automation.run("messaging.lifecycle_dispatch", prop)
        assert Message.objects.count() == 0

        with _at(9, 10):
            run = automation.run("messaging.lifecycle_dispatch", prop)
            automation.run("messaging.lifecycle_dispatch", prop)
        messages = Message.objects.filter(template_code="pre_arrival")
        assert sorted(messages.values_list("channel", flat=True)) == ["email", "whatsapp"]
        assert all("/checkin" in m.body for m in messages)
        assert LifecycleDispatch.objects.get(reservation=reservation).event == "pre_arrival"
        assert run.details["sent"]["pre_arrival"] == 1

    def test_pre_arrival_respects_the_offset(self, prop, guest):
        _reservation(prop, guest, status="confirmed", checkin_date=TODAY + timedelta(days=4))
        _reservation(prop, guest, status="tentative", checkin_date=TODAY + timedelta(days=2))
        with _at(10):
            automation.run("messaging.lifecycle_dispatch", prop)
        assert not Message.objects.filter(template_code="pre_arrival").exists()

    def test_arrival_day(self, prop, guest):
        _reservation(prop, guest, status="confirmed", checkin_date=TODAY)
        with _at(10):
            automation.run("messaging.lifecycle_dispatch", prop)
        assert list(Message.objects.values_list("template_code", "channel")) == [("arrival_day", "whatsapp")]

    def test_post_stay_follows_the_checkout_by_the_offset(self, prop, guest):
        _reservation(
            prop,
            guest,
            status="checked_out",
            checkin_date=TODAY - timedelta(days=3),
            checkout_date=TODAY - timedelta(days=1),
        )
        _reservation(
            prop,
            guest,
            status="checked_out",
            checkin_date=TODAY - timedelta(days=30),
            checkout_date=TODAY - timedelta(days=20),
        )
        with _at(10):
            automation.run("messaging.lifecycle_dispatch", prop)
        assert list(Message.objects.values_list("template_code", flat=True)) == ["post_stay"]

    def test_payment_reminder_only_with_a_balance(self, prop, guest):
        owing = _reservation(prop, guest, status="confirmed", checkin_date=TODAY + timedelta(days=5))
        StayFactory(reservation=owing, total_amount=Decimal("500000"))
        paid = _reservation(prop, guest, status="confirmed", checkin_date=TODAY + timedelta(days=5))
        StayFactory(reservation=paid, total_amount=Decimal("0"))
        LifecycleRuleFactory(property=prop, event="payment_reminder", days_offset=5, channels=["email"])
        with _at(10):
            automation.run("messaging.lifecycle_dispatch", prop)
        (email,) = mail.outbox
        assert owing.code in email.subject and "$ 500.000" in email.body
        assert not LifecycleDispatch.objects.filter(reservation=paid).exists()
