"""Paying the balance, buying extras and asking the hotel for services from the portal."""

from decimal import Decimal

import pytest
from django.conf import settings

from apps.core.models import Alert
from apps.finance.models import Charge, PaymentIntent
from apps.finance.services import get_or_create_folio, record_payment
from apps.guestportal.models import GuestPortalSettings, ServiceRequest
from apps.rates.tests.factories import ExtraFactory, TaxFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def extras_tax(hotel):
    return TaxFactory(
        property=hotel.prop, code="IVA-EXT", applies_to="extras", exempt_foreign_non_residents=False
    )


@pytest.fixture
def breakfast(hotel, extras_tax):
    return ExtraFactory(
        property=hotel.prop,
        code="BRK",
        name={"es": "Desayuno", "en": "Breakfast"},
        price=Decimal("35000"),
        charge_type="per_person_night",
        tax=extras_tax,
    )


class TestPayingTheBalance:
    def test_paying_creates_a_payment_link_for_the_balance(self, public_api, portal_url, reservation):
        response = public_api.post(portal_url("pay/"), {}, format="json")

        assert response.status_code == 201, response.json()
        intent = PaymentIntent.objects.get(reference=response.json()["reference"])
        assert intent.folio.reservation_id == reservation.pk
        assert intent.amount == Decimal("761600")
        assert response.json()["amount"] == "761600.00"
        assert response.json()["checkout_url"] == intent.checkout_url
        assert intent.return_url.startswith(f"{settings.FRONTEND_URL}/g/")
        assert intent.return_url.endswith("?paid=1")

    def test_the_guest_may_pay_part_of_it(self, public_api, portal_url):
        response = public_api.post(portal_url("pay/"), {"amount": "200000"}, format="json")

        assert response.status_code == 201
        assert response.json()["amount"] == "200000.00"

    def test_more_than_what_is_owed_is_rejected(self, public_api, portal_url):
        response = public_api.post(portal_url("pay/"), {"amount": "900000"}, format="json")

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_amount"

    def test_a_settled_booking_has_nothing_to_pay(self, public_api, portal_url, reservation):
        record_payment(get_or_create_folio(reservation), amount=Decimal("761600"), method="bank_transfer")

        response = public_api.post(portal_url("pay/"), {}, format="json")

        assert response.status_code == 409
        assert response.json()["code"] == "nothing_to_pay"

    def test_an_open_link_for_the_same_amount_is_reused(self, public_api, portal_url):
        first = public_api.post(portal_url("pay/"), {}, format="json").json()
        second = public_api.post(portal_url("pay/"), {}, format="json").json()

        assert second["reference"] == first["reference"]
        assert PaymentIntent.objects.count() == 1

    def test_the_simulated_gateway_settles_the_balance(self, public_api, portal_url):
        reference = public_api.post(portal_url("pay/"), {}, format="json").json()["reference"]

        decided = public_api.post(
            f"/api/v1/public/finance/sim/intents/{reference}/decide/",
            {"outcome": "approved", "method": "card"},
            format="json",
        )

        assert decided.status_code == 200
        balance = public_api.get(portal_url()).json()["balance"]
        assert (balance["paid"], balance["due"], balance["can_pay"]) == ("761600.00", "0.00", False)


class TestExtras:
    def test_the_guest_sees_what_can_be_bought_online_with_its_final_price(
        self, public_api, portal_url, hotel, breakfast
    ):
        ExtraFactory(property=hotel.prop, code="SPA", sellable_online=False)
        ExtraFactory(property=hotel.prop, code="OLD", is_active=False)

        extras = public_api.get(portal_url("extras/")).json()

        assert [extra["code"] for extra in extras] == ["BRK"]
        # 2 adults × 2 nights; 35.000 + 19 % IVA = 41.650 each
        assert extras[0]["unit_price"] == "41650.00"
        assert extras[0]["default_quantity"] == 4
        assert extras[0]["default_total"] == "166600.00"
        assert extras[0]["charge_type"] == "per_person_night"

    def test_buying_an_extra_posts_the_charge_when_the_hotel_auto_approves(
        self, public_api, portal_url, reservation, breakfast
    ):
        response = public_api.post(
            portal_url("requests/"),
            {"kind": "extra", "extra_id": str(breakfast.pk), "quantity": 2},
            format="json",
        )

        assert response.status_code == 201, response.json()
        request = ServiceRequest.objects.get()
        charge = Charge.objects.get(folio__reservation=reservation, kind="extra")
        assert (charge.extra_id, charge.quantity, charge.amount, charge.tax_amount, charge.source) == (
            breakfast.pk,
            2,
            Decimal("70000"),
            Decimal("13300"),
            "guest",
        )
        assert (request.status, request.charge_id, request.price) == ("approved", charge.pk, Decimal("83300"))
        assert response.json()["request"]["status"] == "approved"
        assert public_api.get(portal_url()).json()["balance"]["due"] == "844900.00"  # 761.600 + 83.300

    def test_extras_wait_for_the_hotel_when_it_approves_them_by_hand(
        self, public_api, portal_url, reservation, breakfast
    ):
        GuestPortalSettings.objects.create(property=reservation.property, auto_approve_extras=False)

        response = public_api.post(
            portal_url("requests/"),
            {"kind": "extra", "extra_id": str(breakfast.pk), "quantity": 2},
            format="json",
        )

        assert response.status_code == 201
        request = ServiceRequest.objects.get()
        assert (request.status, request.charge_id, request.price) == ("requested", None, Decimal("83300"))
        assert not Charge.objects.filter(folio__reservation=reservation, kind="extra").exists()
        assert Alert.objects.filter(kind="guestportal_request", resolved_at__isnull=True).count() == 1

    def test_an_extra_that_is_not_sold_online_cannot_be_bought(self, public_api, portal_url, hotel):
        hidden = ExtraFactory(property=hotel.prop, sellable_online=False)

        response = public_api.post(
            portal_url("requests/"), {"kind": "extra", "extra_id": str(hidden.pk)}, format="json"
        )

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_extra"


class TestServiceRequests:
    def test_a_late_checkout_is_a_request_the_staff_is_alerted_about(
        self, public_api, portal_url, reservation
    ):
        response = public_api.post(
            portal_url("requests/"),
            {"kind": "late_checkout", "requested_time": "14:00", "notes": "Vuelo a las 6 pm"},
            format="json",
        )

        assert response.status_code == 201, response.json()
        request = ServiceRequest.objects.get(reservation=reservation)
        assert (request.kind, request.status, request.requested_time.isoformat(), request.charge_id) == (
            "late_checkout",
            "requested",
            "14:00:00",
            None,
        )
        alert = Alert.objects.get(property=reservation.property, kind="guestportal_request")
        assert reservation.code in alert.title
        assert alert.link == f"/app/reservations/{reservation.pk}"
        assert alert.data["request_id"] == str(request.pk)
        assert [item["kind"] for item in public_api.get(portal_url()).json()["requests"]] == ["late_checkout"]

    def test_other_requests_need_a_description(self, public_api, portal_url):
        response = public_api.post(portal_url("requests/"), {"kind": "other", "notes": " "}, format="json")

        assert response.status_code == 400
        assert "notes" in response.json()["fields"]

    def test_a_cancelled_booking_takes_no_requests(self, public_api, portal_url, reservation):
        from apps.bookings.services.reservations import cancel_reservation

        cancel_reservation(reservation, reason="test")

        response = public_api.post(portal_url("requests/"), {"kind": "late_checkout"}, format="json")

        assert response.status_code == 409
        assert response.json()["code"] == "invalid_state"
