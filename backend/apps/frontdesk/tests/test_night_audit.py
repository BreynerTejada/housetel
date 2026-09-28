"""Night audit (plan C1): closes the business date `D` of a property.

1. posts the room charge of every night < D+1 still unposted of the guests in house (`post_room_charges`);
2. moves the business date to D+1;
3. marks as no-show the confirmed reservations that arrive before D+1 and never checked in (when
   `property.settings.auto_no_show`, default True), charging the policy's fee;
4. raises (or resolves) the alert of the guests that should have left and did not check out;
5. writes the closing report (`NightAuditReport`, one per property and date).

A date is closed once: closing it again returns the same report and changes nothing. The scheduled automation
only closes days that already ended in the property's timezone (catching up several if it fell behind); the
manual run may close the current day early, never a day that has not started.
"""

from datetime import date
from decimal import Decimal

import pytest
from freezegun import freeze_time

from apps.bookings.models import Reservation
from apps.bookings.services.charges import post_room_charges
from apps.bookings.tests.helpers import oct_
from apps.core import automation
from apps.core.models import Alert, AuditEvent, AutomationRun
from apps.finance.models import Charge, Folio
from apps.finance.services import get_or_create_folio
from apps.frontdesk.models import NightAuditReport
from apps.frontdesk.services.night_audit import (
    NightAuditError,
    close_business_day,
    preview_night_audit,
)
from apps.frontdesk.tests.helpers import arrived, fresh, new_stay

pytestmark = pytest.mark.django_db

CODE = "frontdesk.night_audit"
# 2026-10-01 is the business date of `hotel`; the calendar is pinned right after that day ends.
AFTER_OCT_1 = "2026-10-02 02:00:00-05:00"


def room_nights(stay):
    return sorted(
        Charge.objects.filter(stay=stay, kind="room", voided_at__isnull=True).values_list(
            "night_date", flat=True
        )
    )


def reload(hotel):
    hotel.prop.refresh_from_db()
    return hotel.prop


@pytest.fixture
def guest_in_house(hotel):
    """Checked in on 2026-09-30 until 2026-10-03; the night of the 30th is already posted."""
    stay = arrived(hotel, oct_(0), oct_(3), room=hotel.rooms["101"])
    post_room_charges(stay, until_date=oct_(1))
    return fresh(stay)


@freeze_time(AFTER_OCT_1)
class TestCloseBusinessDay:
    def test_posts_tonights_room_charge_of_every_guest_in_house_once(self, hotel, guest_in_house):
        report, closed = close_business_day(hotel.prop)

        assert closed is True
        assert room_nights(guest_in_house) == [oct_(0), oct_(1)]
        charge = Charge.objects.get(stay=guest_in_house, night_date=oct_(1))
        assert (charge.amount, charge.tax_amount, charge.business_date) == (
            Decimal("320000.00"),
            Decimal("60800.00"),
            oct_(1),
        )
        assert report.summary["room_charges"] == {
            "stays": 1,
            "nights": 1,
            "net": "320000.00",
            "tax": "60800.00",
            "total": "380800.00",
        }

    def test_marks_as_no_show_the_arrivals_that_never_came(self, hotel):
        missing = new_stay(hotel, oct_(1), oct_(2), room=hotel.rooms["102"])
        tomorrow = new_stay(hotel, oct_(2), oct_(3))
        tentative = new_stay(hotel, oct_(1), oct_(2), status="tentative")

        report, _ = close_business_day(hotel.prop)

        reservation = Reservation.objects.get(pk=missing.reservation_id)
        assert (reservation.status, reservation.cancellation_fee) == ("no_show", Decimal("380800.00"))
        fee = Charge.objects.get(folio__reservation=reservation, kind="cancellation_fee")
        assert (fee.amount, fee.business_date) == (Decimal("380800.00"), oct_(2))
        assert fresh(tomorrow).status == "confirmed"
        assert fresh(tentative).status == "tentative"
        assert report.summary["no_shows"] == [
            {
                "reservation_id": str(reservation.pk),
                "code": reservation.code,
                "guest_name": reservation.booker.full_name,
                "checkin": "2026-10-01",
                "fee": "380800.00",
            }
        ]
        assert report.summary["no_show_fees"] == "380800.00"
        assert [item["code"] for item in report.summary["pending_tentative"]] == [tentative.reservation.code]

    def test_the_hotel_can_turn_off_automatic_no_shows(self, hotel):
        hotel.prop.settings = {**hotel.prop.settings, "auto_no_show": False}
        hotel.prop.save(update_fields=["settings"])
        missing = new_stay(hotel, oct_(1), oct_(2))

        report, _ = close_business_day(hotel.prop)

        assert fresh(missing).status == "confirmed"
        assert (report.summary["auto_no_show"], report.summary["no_shows"]) == (False, [])

    def test_moves_the_business_date_to_the_next_day(self, hotel):
        close_business_day(hotel.prop)

        assert reload(hotel).business_date == oct_(2)

    def test_writes_the_closing_report_of_the_day(self, hotel, guest_in_house):
        report, _ = close_business_day(hotel.prop)

        report.refresh_from_db()
        assert (report.business_date, report.status) == (oct_(1), "completed")
        assert report.finished_at is not None
        summary = report.summary
        assert (summary["business_date"], summary["next_business_date"]) == ("2026-10-01", "2026-10-02")
        figures = summary["figures"]
        assert (figures["rooms_occupied"], figures["rooms_available"], figures["occupancy_pct"]) == (
            1,
            8,
            12.5,
        )
        assert (figures["room_revenue"], figures["adr"]) == ("320000.00", "320000.00")
        assert summary["activity"]["in_house"] == 1
        assert summary["errors"] == []
        event = AuditEvent.objects.get(action="frontdesk.night_audit")
        assert event.changes == {"business_date": ["2026-10-01", "2026-10-02"]}

    def test_guests_that_should_have_left_raise_an_alert(self, hotel):
        staying = arrived(hotel, date(2026, 9, 29), oct_(1), room=hotel.rooms["201"])

        report, _ = close_business_day(hotel.prop)

        assert [item["stay_id"] for item in report.summary["overdue_departures"]] == [str(staying.pk)]
        alert = Alert.objects.get(dedupe_key="frontdesk:overdue_departures", resolved_at__isnull=True)
        assert (alert.kind, alert.severity) == ("overdue_departures", "warning")
        assert alert.data["stays"] == [str(staying.pk)]

    def test_the_overdue_alert_is_resolved_when_nobody_is_late(self, hotel):
        from apps.core.alerts import raise_alert

        raise_alert(
            property=hotel.prop,
            kind="overdue_departures",
            severity="warning",
            title="1 salida sin check-out",
            message="…",
            dedupe_key="frontdesk:overdue_departures",
        )

        close_business_day(hotel.prop)

        assert not Alert.objects.filter(
            dedupe_key="frontdesk:overdue_departures", resolved_at__isnull=True
        ).exists()

    def test_a_failing_stay_does_not_stop_the_audit(self, hotel, guest_in_house):
        broken = arrived(hotel, oct_(0), oct_(2), room_type=hotel.ste, room=hotel.rooms["301"])
        Folio.objects.filter(pk=get_or_create_folio(broken.reservation).pk).update(status="closed")

        report, _ = close_business_day(hotel.prop)

        assert report.status == "partial"
        assert room_nights(guest_in_house) == [oct_(0), oct_(1)]
        assert room_nights(broken) == []
        (error,) = report.summary["errors"]
        assert (error["step"], error["code"], error["error_code"]) == (
            "room_charges",
            broken.reservation.code,
            "folio_closed",
        )
        assert reload(hotel).business_date == oct_(2)
        assert Alert.objects.filter(
            dedupe_key="frontdesk:night_audit_errors", resolved_at__isnull=True
        ).exists()


@freeze_time(AFTER_OCT_1)
class TestOnePerDate:
    def test_closing_the_same_date_again_returns_the_report_and_changes_nothing(self, hotel, guest_in_house):
        first, closed = close_business_day(hotel.prop, business_date=oct_(1))
        again, closed_again = close_business_day(hotel.prop, business_date=oct_(1))

        assert (closed, closed_again) == (True, False)
        assert again.pk == first.pk
        assert room_nights(guest_in_house) == [oct_(0), oct_(1)]
        assert reload(hotel).business_date == oct_(2)
        assert NightAuditReport.objects.filter(property=hotel.prop).count() == 1

    def test_another_date_than_the_current_one_is_refused(self, hotel):
        with pytest.raises(NightAuditError) as error:
            close_business_day(hotel.prop, business_date=oct_(5))

        assert (error.value.code, error.value.status_code) == ("business_date_changed", 409)
        assert reload(hotel).business_date == oct_(1)

    def test_a_day_that_has_not_started_cannot_be_closed(self, hotel):
        with freeze_time("2026-09-30 22:00:00-05:00"), pytest.raises(NightAuditError) as error:
            close_business_day(hotel.prop)

        assert error.value.code == "audit_ahead"
        assert reload(hotel).business_date == oct_(1)

    def test_the_current_day_can_be_closed_early(self, hotel):
        with freeze_time("2026-10-01 23:30:00-05:00"):
            report, closed = close_business_day(hotel.prop)

        assert (closed, report.business_date, reload(hotel).business_date) == (True, oct_(1), oct_(2))


class TestAutomation:
    def test_it_is_registered_at_two_in_the_morning(self):
        item = automation.get(CODE)

        assert (item.app, item.scope, item.default_enabled) == ("frontdesk", "property", True)
        assert (item.schedule.hour, item.schedule.minute) == ({2}, {0})

    def test_the_scheduled_run_catches_up_every_day_that_already_ended(self, hotel):
        with freeze_time("2026-10-04 02:00:00-05:00"):
            run = automation.run(CODE, hotel.prop)

        assert run.status == "success"
        assert reload(hotel).business_date == oct_(4)
        reports = NightAuditReport.objects.filter(property=hotel.prop).order_by("business_date")
        assert [report.business_date for report in reports] == [oct_(1), oct_(2), oct_(3)]
        assert all(report.run_id == run.pk for report in reports)
        assert run.details["closed"] == ["2026-10-01", "2026-10-02", "2026-10-03"]

    def test_the_scheduled_run_skips_a_day_that_has_not_ended(self, hotel):
        with freeze_time("2026-10-01 23:00:00-05:00"):
            run = automation.run(CODE, hotel.prop)

        assert run.status == "skipped"
        assert reload(hotel).business_date == oct_(1)
        assert not NightAuditReport.objects.exists()

    def test_it_closes_at_most_a_week_per_run(self, hotel):
        hotel.prop.business_date = date(2026, 9, 1)
        hotel.prop.save(update_fields=["business_date"])

        with freeze_time(AFTER_OCT_1):
            run = automation.run(CODE, hotel.prop)

        assert (run.status, len(run.details["closed"])) == ("partial", 7)
        assert reload(hotel).business_date == date(2026, 9, 8)

    def test_a_manual_run_closes_the_requested_date_and_records_who(self, hotel, owner):
        with freeze_time("2026-10-01 23:30:00-05:00"):
            run = automation.run(
                CODE, hotel.prop, params={"mode": "manual", "business_date": "2026-10-01"}, triggered_by=owner
            )

        report = NightAuditReport.objects.get(property=hotel.prop)
        assert (run.status, report.business_date, report.triggered_by, report.run) == (
            "success",
            oct_(1),
            owner,
            run,
        )
        assert AutomationRun.objects.get(pk=run.pk).triggered_by == owner


@freeze_time(AFTER_OCT_1)
class TestPreview:
    def test_the_preview_tells_what_would_happen_without_changing_anything(self, hotel, guest_in_house):
        missing = new_stay(hotel, oct_(1), oct_(2), room=hotel.rooms["102"])
        charges_before = Charge.objects.count()

        preview = preview_night_audit(hotel.prop)

        assert (preview["business_date"], preview["next_business_date"]) == ("2026-10-01", "2026-10-02")
        assert (preview["can_run"], preview["reason"], preview["due"]) == (True, None, True)
        summary = preview["summary"]
        assert [item["code"] for item in summary["no_shows"]] == [missing.reservation.code]
        assert summary["room_charges"]["nights"] == 1
        assert fresh(missing).status == "confirmed"
        assert Charge.objects.count() == charges_before
        assert reload(hotel).business_date == oct_(1)
        assert not NightAuditReport.objects.exists()
        assert not AuditEvent.objects.filter(action="frontdesk.night_audit").exists()

    def test_the_preview_of_a_day_that_has_not_started_explains_why(self, hotel):
        with freeze_time("2026-09-30 10:00:00-05:00"):
            preview = preview_night_audit(hotel.prop)

        assert (preview["can_run"], preview["reason"], preview["summary"]) == (False, "audit_ahead", None)
