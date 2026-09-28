"""Changing or cancelling the booking from the portal, always within the policy."""

from datetime import date
from decimal import Decimal

import pytest
from freezegun import freeze_time

from apps.bookings.models import Reservation
from apps.bookings.tests.helpers import book, oct_
from apps.core.models import Alert, AuditEvent
from apps.core.tokens import make_reservation_token
from apps.finance.models import Charge
from apps.finance.services import get_or_create_folio, record_payment
from apps.guestportal.models import GuestPortalSettings
from apps.rates.services.quote import set_daily_rates
from apps.rates.tests.factories import CancellationPolicyFactory

pytestmark = pytest.mark.django_db

INSIDE_FREE_WINDOW = "2026-10-01 10:00:00-05:00"  # free until Oct 3, 15:00 (48 h before the 15:00 arrival)
AFTER_FREE_WINDOW = "2026-10-04 10:00:00-05:00"


@pytest.fixture
def flexible(hotel):
    policy = CancellationPolicyFactory(property=hotel.prop)  # free until 48 h before, then the first night
    hotel.plan.cancellation_policy = policy
    hotel.plan.save(update_fields=["cancellation_policy"])
    return policy


@pytest.fixture
def booking(hotel, flexible):
    return book(hotel, oct_(5), oct_(7))


@pytest.fixture
def url(booking):
    token = make_reservation_token(booking)

    def _url(path=""):
        return f"/api/v1/public/guestportal/{token}/{path}"

    return _url


class TestCancellation:
    @freeze_time(INSIDE_FREE_WINDOW)
    def test_the_summary_previews_what_cancelling_would_cost(self, public_api, url):
        cancellation = public_api.get(url()).json()["cancellation"]

        assert (cancellation["can_cancel"], cancellation["fee"], cancellation["fee_reason"]) == (
            True,
            "0.00",
            "free_window",
        )
        assert cancellation["free_until"] == "2026-10-03T15:00:00-05:00"

    @freeze_time(INSIDE_FREE_WINDOW)
    def test_cancelling_inside_the_free_window_costs_nothing(self, public_api, url, booking):
        response = public_api.post(url("cancel/"), {"confirm": True}, format="json")

        assert response.status_code == 200, response.json()
        booking.refresh_from_db()
        assert (booking.status, booking.cancellation_fee) == ("cancelled", Decimal("0"))
        assert response.json()["reservation"]["status"] == "cancelled"
        event = AuditEvent.objects.get(action="bookings.reservation_cancelled", target_id=str(booking.pk))
        assert event.source == "guest"

    @freeze_time(AFTER_FREE_WINDOW)
    def test_after_the_free_window_the_policy_charges_the_first_night(self, public_api, url, booking):
        preview = public_api.get(url()).json()["cancellation"]
        assert (preview["fee"], preview["fee_reason"]) == ("380800.00", "first_night")

        response = public_api.post(url("cancel/"), {"confirm": True}, format="json")

        assert response.status_code == 200
        fee = Charge.objects.get(folio__reservation=booking, kind="cancellation_fee")
        assert fee.amount == Decimal("380800")
        assert Reservation.objects.get(pk=booking.pk).cancellation_fee == Decimal("380800")

    def test_cancelling_needs_an_explicit_confirmation(self, public_api, url, booking):
        response = public_api.post(url("cancel/"), {}, format="json")

        assert response.status_code == 400
        assert response.json()["code"] == "confirmation_required"
        assert Reservation.objects.get(pk=booking.pk).status == "confirmed"

    def test_channel_bookings_are_cancelled_on_the_channel(self, public_api, hotel):
        ota = book(hotel, oct_(5), oct_(7), source="ota", channel_code="booksim", external_id="BK-1",
                   enforce_restrictions=False)  # fmt: skip
        ota_url = f"/api/v1/public/guestportal/{make_reservation_token(ota)}/"

        assert public_api.get(ota_url).json()["cancellation"]["reason"] == "channel"
        response = public_api.post(ota_url + "cancel/", {"confirm": True}, format="json")

        assert response.status_code == 409
        assert response.json()["code"] == "managed_by_channel"
        assert Reservation.objects.get(pk=ota.pk).status == "confirmed"

    def test_the_hotel_may_turn_off_self_service_cancellations(self, public_api, url, booking):
        GuestPortalSettings.objects.create(property=booking.property, allow_guest_cancellation=False)

        response = public_api.post(url("cancel/"), {"confirm": True}, format="json")

        assert response.status_code == 409
        assert response.json()["code"] == "cancellation_disabled"

    @freeze_time(INSIDE_FREE_WINDOW)
    def test_a_guest_who_had_paid_leaves_a_credit_the_hotel_is_told_about(self, public_api, url, booking):
        record_payment(get_or_create_folio(booking), amount=Decimal("761600"), method="bank_transfer")

        public_api.post(url("cancel/"), {"confirm": True}, format="json")

        alert = Alert.objects.get(property=booking.property, kind="guestportal_cancelled")
        assert alert.severity == "warning"
        assert alert.data["credit"] == "761600.00"
        assert alert.link == f"/app/reservations/{booking.pk}"


class TestModification:
    @freeze_time(INSIDE_FREE_WINDOW)
    def test_the_preview_reprices_without_saving(self, public_api, url, booking):
        response = public_api.post(
            url("modify-preview/"), {"checkin": "2026-10-05", "checkout": "2026-10-08"}, format="json"
        )

        assert response.status_code == 200, response.json()
        assert response.json() == {
            "checkin": "2026-10-05",
            "checkout": "2026-10-08",
            "nights": 3,
            "current_total": "761600.00",
            "total": "1142400.00",
            "difference": "380800.00",
            "balance": "1142400.00",
            "currency": "COP",
        }
        assert booking.stays.get().checkout_date == oct_(7)

    @freeze_time(INSIDE_FREE_WINDOW)
    def test_changing_the_dates_reprices_the_stay(self, public_api, url, booking):
        response = public_api.post(
            url("modify/"), {"checkin": "2026-10-05", "checkout": "2026-10-08"}, format="json"
        )

        assert response.status_code == 200, response.json()
        stay = booking.stays.get()
        assert (stay.checkout_date, stay.total_amount) == (oct_(8), Decimal("1142400"))
        assert (response.json()["total"], response.json()["balance"]) == ("1142400.00", "1142400.00")
        assert response.json()["summary"]["reservation"]["checkout_date"] == "2026-10-08"
        assert Alert.objects.filter(property=booking.property, kind="guestportal_modified").exists()

    @freeze_time(INSIDE_FREE_WINDOW)
    def test_dates_without_availability_are_refused(self, public_api, url, hotel, booking):
        for _ in range(3):  # every DBL room taken on Oct 7
            book(hotel, oct_(7), oct_(8))

        response = public_api.post(
            url("modify/"), {"checkin": "2026-10-05", "checkout": "2026-10-08"}, format="json"
        )

        assert response.status_code == 409
        assert response.json()["code"] == "no_availability"
        assert booking.stays.get().checkout_date == oct_(7)

    @freeze_time(INSIDE_FREE_WINDOW)
    def test_rate_restrictions_apply_to_guest_changes(self, public_api, url, hotel):
        set_daily_rates(property=hotel.prop, room_type=hotel.dbl, rate_plan=hotel.plan, start=oct_(9),
                        end=oct_(10), restrictions={"min_los": 3})  # fmt: skip

        response = public_api.post(
            url("modify/"), {"checkin": "2026-10-09", "checkout": "2026-10-11"}, format="json"
        )

        assert response.status_code == 400
        assert response.json()["code"] == "restriction_violation"
        assert response.json()["violations"] == ["min_los"]

    @freeze_time(AFTER_FREE_WINDOW)
    def test_dates_only_change_while_the_booking_can_be_cancelled_for_free(self, public_api, url):
        assert public_api.get(url()).json()["modification"]["can_modify"] is False

        response = public_api.post(
            url("modify/"), {"checkin": "2026-10-05", "checkout": "2026-10-08"}, format="json"
        )

        assert response.status_code == 409
        assert response.json()["code"] == "modification_not_allowed"
        assert response.json()["reason"] == "outside_free_window"

    @freeze_time(INSIDE_FREE_WINDOW)
    def test_arrival_cannot_move_to_the_past(self, public_api, url):
        response = public_api.post(
            url("modify/"), {"checkin": "2026-09-29", "checkout": "2026-10-02"}, format="json"
        )

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_dates"


def test_nobody_changes_a_booking_with_a_token_for_another_one(public_api, hotel, flexible):
    mine, theirs = book(hotel, oct_(5), oct_(7)), book(hotel, oct_(12), oct_(14))

    public_api.post(f"/api/v1/public/guestportal/{make_reservation_token(mine)}/cancel/", {"confirm": True},
                    format="json")  # fmt: skip

    assert Reservation.objects.get(pk=theirs.pk).status == "confirmed"
    assert Reservation.objects.get(pk=mine.pk).checkin_date == date(2026, 10, 5)
