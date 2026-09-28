"""Checkout quote and online booking (plan C4 › POST bookings/)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.utils import timezone

from apps.bookings.models import Reservation
from apps.core.models import IntegrationSetting
from apps.finance.models import Charge, PaymentIntent
from apps.marketplace.models import BookingEngineSettings
from apps.marketplace.tests.conftest import PUBLIC
from apps.marketplace.tests.helpers import booking_payload, day, guest_payload

pytestmark = pytest.mark.django_db

# DBL + FLEX, 2 adults, 2 nights: 320.000 × 2 = 640.000 + IVA 19 % (60.800 per night) = 761.600
DBL_FLEX_TOTAL = Decimal("761600")


def _book(public_api, payload, expected=201):
    response = public_api.post(f"{PUBLIC}/bookings/", payload, format="json")
    assert response.status_code == expected, response.json()
    return response.json()


def _quote(public_api, payload, expected=200):
    response = public_api.post(f"{PUBLIC}/checkout/quote/", payload, format="json")
    assert response.status_code == expected, response.json()
    return response.json()


class TestPayAtHotel:
    def test_confirms_the_booking_without_a_payment_link(self, public_api, hotel):
        data = _book(public_api, booking_payload(hotel))

        reservation = Reservation.objects.get(code=data["reservation_code"])
        assert data["status"] == "confirmed"
        assert data["payment"] is None
        assert reservation.status == "confirmed"
        assert reservation.source == "marketplace"
        assert reservation.guarantee == "none"
        assert reservation.hold_expires_at is None
        assert reservation.total_amount == DBL_FLEX_TOTAL
        assert not PaymentIntent.objects.filter(folio__reservation=reservation).exists()
        assert data["portal_url"].startswith(f"{settings.FRONTEND_URL}/g/")
        assert data["confirmation_path"] == f"/booking/{reservation.code}/confirmed"

    def test_stores_the_guest_with_consent_and_the_requests(self, public_api, hotel):
        payload = booking_payload(
            hotel,
            guest=guest_payload(email="Laura.Gomez@Example.com", marketing_consent=True),
            special_requests="Cama extra para bebé",
            eta="18:30",
            language="en",
        )

        data = _book(public_api, payload)

        reservation = Reservation.objects.select_related("booker").get(code=data["reservation_code"])
        assert reservation.booker.email == "laura.gomez@example.com"
        assert reservation.booker.data_processing_consent_at is not None
        assert reservation.booker.marketing_consent is True
        assert reservation.special_requests == "Cama extra para bebé"
        assert reservation.eta.strftime("%H:%M") == "18:30"
        assert reservation.language == "en"


class TestPayNow:
    def test_creates_a_tentative_booking_and_a_payment_link_for_the_total(self, public_api, hotel):
        data = _book(public_api, booking_payload(hotel, payment_option="pay_now"))

        reservation = Reservation.objects.get(code=data["reservation_code"])
        intent = PaymentIntent.objects.get(reference=data["payment"]["reference"])
        assert data["status"] == "tentative"
        assert reservation.status == "tentative"
        assert reservation.guarantee == "deposit"
        # PSE needs time: the hold (and so the link) lasts 45 minutes
        assert reservation.hold_expires_at == timezone.now() + timedelta(minutes=45)
        assert intent.amount == DBL_FLEX_TOTAL
        assert intent.expires_at == reservation.hold_expires_at
        assert intent.return_url == f"{settings.FRONTEND_URL}/booking/{reservation.code}/confirmed"
        assert data["payment"]["checkout_url"] == f"{settings.FRONTEND_URL}/sim/pay/{intent.reference}"
        assert data["payment"]["amount"] == "761600.00"
        assert data["amount_due_now"] == "761600.00"

    def test_the_approved_simulated_payment_confirms_the_booking(
        self, public_api, hotel, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            data = _book(public_api, booking_payload(hotel, payment_option="pay_now"))
        reference = data["payment"]["reference"]

        with django_capture_on_commit_callbacks(execute=True):
            response = public_api.post(
                f"/api/v1/public/finance/sim/intents/{reference}/decide/",
                {"outcome": "approved", "method": "pse"},
                format="json",
            )
        assert response.status_code == 200, response.json()

        reservation = Reservation.objects.get(code=data["reservation_code"])
        assert reservation.status == "confirmed"
        assert reservation.hold_expires_at is None

    def test_a_deposit_plan_paid_at_the_hotel_charges_only_the_deposit_now(self, public_api, hotel):
        hotel.flex.deposit_percent = Decimal("30")
        hotel.flex.save(update_fields=["deposit_percent"])

        data = _book(public_api, booking_payload(hotel, payment_option="pay_at_hotel"))

        reservation = Reservation.objects.get(code=data["reservation_code"])
        assert reservation.status == "tentative"
        # 30 % of each stay: 761.600 × 0,3 = 228.480
        assert PaymentIntent.objects.get(reference=data["payment"]["reference"]).amount == Decimal("228480")

    def test_nothing_is_created_when_online_payments_are_off(self, public_api, hotel):
        IntegrationSetting.objects.create(property=hotel.prop, kind="payments", enabled=False)

        data = _book(public_api, booking_payload(hotel, payment_option="pay_now"), expected=409)

        assert data["code"] == "online_payments_disabled"
        assert not Reservation.objects.filter(property=hotel.prop).exists()


class TestTaxExemption:
    def test_foreign_non_residents_do_not_pay_iva_on_lodging(self, public_api, hotel):
        payload = booking_payload(
            hotel, payment_option="pay_now", guest=guest_payload(nationality="US", country_of_residence="US")
        )

        quote = _quote(public_api, payload)
        data = _book(public_api, payload)

        assert quote["tax_exempt"] is True
        assert quote["lodging_total"] == "640000.00"
        assert quote["tax_total"] == "0.00"
        reservation = Reservation.objects.get(code=data["reservation_code"])
        assert reservation.total_amount == Decimal("640000")
        assert PaymentIntent.objects.get(reference=data["payment"]["reference"]).amount == Decimal("640000")

    def test_a_foreigner_living_in_colombia_pays_iva(self, public_api, hotel):
        payload = booking_payload(hotel, guest=guest_payload(nationality="US", country_of_residence="CO"))

        quote = _quote(public_api, payload)

        assert quote["tax_exempt"] is False
        assert quote["total"] == "761600.00"


class TestExtrasAndTotals:
    def test_extras_are_posted_as_charges_and_the_quote_matches_the_booking(self, public_api, hotel):
        payload = booking_payload(
            hotel, payment_option="pay_now", extras=[{"extra_id": str(hotel.breakfast.pk), "quantity": None}]
        )

        quote = _quote(public_api, payload)
        data = _book(public_api, payload)

        # breakfast per person-night: 2 persons × 2 nights × 35.000 = 140.000 + IVA 26.600
        assert quote["extras"][0]["quantity"] == 4
        assert quote["extras"][0]["total"] == "166600.00"
        assert quote["total"] == "928200.00"
        reservation = Reservation.objects.get(code=data["reservation_code"])
        charge = Charge.objects.get(folio__reservation=reservation, kind="extra")
        assert (charge.quantity, charge.amount, charge.tax_amount) == (4, Decimal("140000"), Decimal("26600"))
        assert charge.source == "guest"
        assert PaymentIntent.objects.get(reference=data["payment"]["reference"]).amount == Decimal("928200")
        assert data["total"] == quote["total"]

    def test_extras_not_sold_online_are_rejected(self, public_api, hotel):
        payload = booking_payload(hotel, extras=[{"extra_id": str(hotel.minibar.pk), "quantity": 1}])

        assert _book(public_api, payload, expected=400)["code"] == "invalid_extra"

    def test_quantity_books_several_rooms(self, public_api, hotel):
        data = _book(public_api, booking_payload(hotel, quantity=2))

        reservation = Reservation.objects.get(code=data["reservation_code"])
        assert reservation.stays.count() == 2
        assert reservation.total_amount == DBL_FLEX_TOTAL * 2


class TestRejections:
    def test_no_availability_answers_409(self, public_api, hotel):
        data = _book(public_api, booking_payload(hotel, quantity=3), expected=409)

        assert data["code"] == "no_availability"
        assert not Reservation.objects.filter(property=hotel.prop).exists()

    def test_the_last_room_goes_to_the_first_guest(self, public_api, hotel):
        _book(public_api, booking_payload(hotel, room_type=hotel.ste))

        data = _book(public_api, booking_payload(hotel, room_type=hotel.ste), expected=409)

        assert data["code"] == "no_availability"

    def test_plans_that_are_not_public_cannot_be_booked_online(self, public_api, hotel):
        data = _book(public_api, booking_payload(hotel, plan=hotel.corp), expected=400)

        assert data["code"] == "invalid_rate_plan"

    def test_consent_is_mandatory(self, public_api, hotel):
        data = _book(
            public_api, booking_payload(hotel, guest=guest_payload(data_processing_consent=False)), 400
        )

        assert data["code"] == "validation_error"
        assert data["fields"]["guest"]["data_processing_consent"]
        assert not Reservation.objects.filter(property=hotel.prop).exists()

    def test_restrictions_apply(self, public_api, hotel):
        from apps.rates.services.quote import set_daily_rates

        set_daily_rates(
            property=hotel.prop,
            room_type=hotel.dbl,
            rate_plan=hotel.flex,
            start=day(8),
            end=day(9),
            restrictions={"min_los": 3},
        )

        data = _book(public_api, booking_payload(hotel), expected=400)

        assert data["code"] == "restriction_violation"

    def test_an_invalid_promo_code_is_rejected_before_booking(self, public_api, hotel):
        payload = booking_payload(hotel, promo_code="NOEXISTE")

        assert _quote(public_api, payload, expected=400)["code"] == "promo_invalid"
        assert _book(public_api, payload, expected=400)["code"] == "promo_invalid"

    def test_unlisted_hotels_cannot_be_booked_through_the_marketplace(self, public_api, hotel):
        hotel.prop.marketplace_listed = False
        hotel.prop.save(update_fields=["marketplace_listed"])

        assert _book(public_api, booking_payload(hotel), expected=404)["code"] == "not_found"

    def test_arrivals_before_the_booking_window_are_rejected(self, public_api, hotel):
        BookingEngineSettings.objects.create(property=hotel.prop, min_advance_hours=48)

        data = _book(public_api, booking_payload(hotel, checkin=day(1), checkout=day(3)), expected=400)

        assert data["code"] == "too_soon"


class TestBookingEngine:
    def test_books_through_the_engine_and_comes_back_to_the_hotel_page(self, public_api, hotel):
        hotel.prop.marketplace_listed = False
        hotel.prop.save(update_fields=["marketplace_listed"])

        data = _book(public_api, booking_payload(hotel, via="booking_engine", payment_option="pay_now"))

        reservation = Reservation.objects.get(code=data["reservation_code"])
        assert reservation.source == "booking_engine"
        intent = PaymentIntent.objects.get(reference=data["payment"]["reference"])
        assert intent.return_url == f"{settings.FRONTEND_URL}/h/{hotel.prop.slug}/booking/{reservation.code}"
        assert data["confirmation_path"] == f"/h/{hotel.prop.slug}/booking/{reservation.code}"

    def test_the_engine_rejects_plans_it_does_not_sell(self, public_api, hotel):
        engine = BookingEngineSettings.objects.create(property=hotel.prop)
        engine.allowed_rate_plans.set([hotel.nr])

        data = _book(public_api, booking_payload(hotel, via="booking_engine"), expected=400)

        assert data["code"] == "invalid_rate_plan"


class TestQuote:
    def test_quote_breaks_down_the_selection_and_the_amount_due_now(self, public_api, hotel):
        hotel.flex.deposit_percent = Decimal("30")
        hotel.flex.save(update_fields=["deposit_percent"])

        quote = _quote(public_api, booking_payload(hotel, payment_option="pay_at_hotel"))

        item = quote["items"][0]
        assert item["units"] == 1
        assert item["total"] == "761600.00"
        assert item["tax"] == "121600.00"
        assert item["deposit"] == "228480.00"
        assert quote["requires_payment"] is True
        assert quote["deposit_total"] == "228480.00"
        assert quote["amount_due_now"] == "228480.00"
        assert quote["due_now"] == {"pay_now": "761600.00", "pay_at_hotel": "228480.00"}
        assert quote["nights"] == 2

    def test_quote_detects_a_selection_that_is_no_longer_available(self, public_api, hotel):
        data = _quote(public_api, booking_payload(hotel, quantity=3), expected=409)

        assert data["code"] == "no_availability"
