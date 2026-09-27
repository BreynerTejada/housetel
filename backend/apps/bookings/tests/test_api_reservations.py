"""Reservations API (`/api/v1/bookings/reservations/`, plan B2b › API): list + filters, create, detail, PATCH,
cancel (+ preview), confirm, no-show; errors with `code`; permissions; tenant isolation."""

from decimal import Decimal
from uuid import uuid4

import pytest
from django.conf import settings
from freezegun import freeze_time

from apps.bookings.models import Reservation
from apps.bookings.services.reservations import assign_room, check_in
from apps.bookings.tests.factories import ReservationGroupFactory
from apps.bookings.tests.helpers import book, guest_input, oct_
from apps.core.models import AuditEvent
from apps.core.tests.factories import OrganizationFactory, PropertyFactory
from apps.finance.services import get_or_create_folio, record_payment
from apps.guests.tests.factories import GuestFactory
from apps.inventory.models import Room
from apps.rates.models import DailyRate
from apps.rates.tests.factories import CancellationPolicyFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/bookings/reservations/"

LIST_KEYS = {
    "id",
    "code",
    "status",
    "source",
    "channel_code",
    "external_id",
    "checkin_date",
    "checkout_date",
    "nights",
    "adults",
    "children",
    "currency",
    "total_amount",
    "balance",
    "guarantee",
    "hold_expires_at",
    "created_at",
    "booker",
    "group",
    "stays",
}
DETAIL_KEYS = LIST_KEYS | {
    "language",
    "eta",
    "special_requests",
    "notes",
    "promo_code",
    "cancellation_policy_snapshot",
    "cancelled_at",
    "cancellation_reason",
    "cancellation_fee",
    "custom_values",
    "tags",
    "external_payload",
    "created_by",
    "updated_at",
    "folio_id",
    "portal_url",
    "flags",
}
STAY_KEYS = {
    "id",
    "status",
    "checkin_date",
    "checkout_date",
    "nights",
    "adults",
    "children",
    "children_ages",
    "room_type",
    "rate_plan",
    "room",
    "bed",
    "locked_room",
    "nightly_rates",
    "total_amount",
    "checked_in_at",
    "checked_out_at",
    "occupants",
}
GUEST_KEYS = {
    "id",
    "first_name",
    "last_name",
    "full_name",
    "email",
    "phone",
    "document_type",
    "document_number",
    "nationality",
    "country_of_residence",
    "language",
    "is_vip",
    "is_foreign_non_resident",
}
FLAG_KEYS = {"ready_for_checkin", "arrives_today", "departs_today", "in_house", "unassigned", "balance_due"}


def payload(hotel, **overrides):
    body = {
        "booker": {
            "first_name": "Laura",
            "last_name": "Gómez",
            "email": "laura@example.com",
            "document_type": "CC",
            "document_number": "52123456",
            "nationality": "CO",
            "country_of_residence": "CO",
            "data_processing_consent": True,
        },
        "stays": [
            {
                "room_type_id": str(hotel.dbl.pk),
                "rate_plan_id": str(hotel.plan.pk),
                "checkin": "2026-10-01",
                "checkout": "2026-10-03",
                "adults": 2,
            }
        ],
        "notes": "Llega tarde",
    }
    body.update(overrides)
    return body


def ids(response):
    return {item["id"] for item in response.json()["results"]}


class TestList:
    def test_lists_the_reservations_of_the_active_property(self, hotel, api, organization):
        mine = book(hotel, oct_(1), oct_(3))
        sister = PropertyFactory(organization=organization)
        book_elsewhere = Reservation.objects.create(
            property=sister,
            booker=GuestFactory(organization=organization),
            checkin_date=oct_(1),
            checkout_date=oct_(2),
        )

        response = api.get(URL)

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1 and ids(response) == {str(mine.pk)}
        assert str(book_elsewhere.pk) not in ids(response)
        item = body["results"][0]
        assert set(item) == LIST_KEYS
        assert (item["total_amount"], item["balance"], item["nights"]) == ("761600.00", "761600.00", 2)
        assert set(item["booker"]) == {"id", "full_name", "email", "phone", "is_vip", "nationality"}
        assert set(item["stays"][0]) == {"id", "status", "room_type", "room", "bed"}

    def test_filters(self, hotel, api):
        arriving = book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["101"].pk})
        later = book(
            hotel,
            oct_(5),
            oct_(8),
            source="ota",
            channel_code="booksim",
            external_id="BK-778",
            enforce_restrictions=False,
        )
        tentative = book(
            hotel,
            oct_(2),
            oct_(4),
            status="tentative",
            room_type=hotel.ste,
            booker=guest_input(first_name="Mariana", last_name="Quintero", email="mq@example.com"),
        )
        record_payment(get_or_create_folio(later), amount=later.total_amount, method="bank_transfer")

        def query(**params):
            return ids(api.get(URL, params))

        assert query(status="tentative") == {str(tentative.pk)}
        assert query(status=["tentative", "confirmed"]) == {
            str(arriving.pk),
            str(later.pk),
            str(tentative.pk),
        }
        assert query(source="ota") == query(channel_code="booksim") == {str(later.pk)}
        assert query(arrival_from="2026-10-02", arrival_to="2026-10-05") == {str(tentative.pk), str(later.pk)}
        assert query(departure_from="2026-10-03", departure_to="2026-10-03") == {str(arriving.pk)}
        assert query(in_house_on="2026-10-02") == {str(arriving.pk)}  # tentative holds are not in house
        assert query(room_type=str(hotel.ste.pk)) == {str(tentative.pk)}
        assert query(unassigned=1) == {str(later.pk), str(tentative.pk)}
        assert query(balance_due=1) == {str(arriving.pk), str(tentative.pk)}
        assert (
            query(q="quinter")
            == query(q="MQ@EXAMPLE")
            == query(q=tentative.code.lower())
            == {str(tentative.pk)}
        )
        assert query(q="BK-778") == {str(later.pk)}

    def test_ordering(self, hotel, api):
        first = book(hotel, oct_(3), oct_(4))
        second = book(hotel, oct_(1), oct_(2))
        response = api.get(URL, {"ordering": "checkin_date"})
        assert [item["id"] for item in response.json()["results"]] == [str(second.pk), str(first.pk)]
        response = api.get(URL, {"ordering": "-balance"})
        assert response.status_code == 200

    def test_housekeeping_cannot_see_reservations(self, hotel, api_for, make_member):
        response = api_for(make_member("housekeeping"), hotel.prop).get(URL)
        assert response.status_code == 403
        assert response.json()["permission"] == "bookings.view"


class TestCreate:
    def test_returns_201_with_the_detail(self, hotel, api):
        response = api.post(URL, payload(hotel), format="json")

        assert response.status_code == 201, response.json()
        body = response.json()
        assert set(body) == DETAIL_KEYS
        assert (body["status"], body["total_amount"], body["notes"]) == (
            "confirmed",
            "761600.00",
            "Llega tarde",
        )
        assert set(body["booker"]) == GUEST_KEYS and body["booker"]["document_number"] == "52123456"
        (stay,) = body["stays"]
        assert set(stay) == STAY_KEYS
        assert stay["room_type"] == {
            "id": str(hotel.dbl.pk),
            "code": "DBL",
            "name": hotel.dbl.name,
            "kind": "private",
            "color": hotel.dbl.color,
        }
        assert set(stay["rate_plan"]) == {"id", "code", "name", "meal_plan"}
        assert stay["nightly_rates"][0] == {
            "date": "2026-10-01",
            "amount": "380800.00",
            "net": "320000.00",
            "tax": "60800.00",
        }
        assert set(body["flags"]) == FLAG_KEYS
        assert body["portal_url"].startswith(f"{settings.FRONTEND_URL}/g/")
        assert body["folio_id"]

    def test_an_existing_guest_can_be_referenced(self, hotel, api, organization):
        guest = GuestFactory(organization=organization)
        body = payload(hotel, booker_id=str(guest.pk))
        del body["booker"]
        response = api.post(URL, body, format="json")
        assert response.status_code == 201 and response.json()["booker"]["id"] == str(guest.pk)

    def test_the_booker_is_required_and_must_belong_to_the_organization(self, hotel, api):
        body = payload(hotel)
        del body["booker"]
        response = api.post(URL, body, format="json")
        assert (response.status_code, response.json()["code"]) == (400, "validation_error")
        stranger = GuestFactory(organization=OrganizationFactory())
        response = api.post(URL, {**body, "booker_id": str(stranger.pk)}, format="json")
        assert (response.status_code, response.json()["code"]) == (400, "invalid_guest")

    def test_payload_validation(self, hotel, api):
        response = api.post(URL, payload(hotel, stays=[]), format="json")
        assert (response.status_code, response.json()["code"]) == (400, "validation_error")
        assert "stays" in response.json()["fields"]

    def test_no_availability_is_a_409_with_the_shortfalls(self, hotel, api):
        for _ in range(3):
            book(hotel, oct_(1), oct_(3))
        response = api.post(URL, payload(hotel), format="json")
        assert (response.status_code, response.json()["code"]) == (409, "no_availability")
        assert response.json()["shortfalls"][0]["date"] == "2026-10-01"

    def test_a_restriction_is_a_400_with_the_violations(self, hotel, api):
        DailyRate.objects.create(
            room_type=hotel.dbl, rate_plan=hotel.plan, date=oct_(1), price=Decimal("320000"), stop_sell=True
        )
        response = api.post(URL, payload(hotel), format="json")
        assert (response.status_code, response.json()["code"]) == (400, "restriction_violation")
        assert response.json()["violations"] == ["stop_sell"]

    def test_capacity_is_a_400(self, hotel, api):
        body = payload(hotel)
        body["stays"][0]["adults"] = 3
        response = api.post(URL, body, format="json")
        assert (response.status_code, response.json()["code"]) == (400, "capacity_exceeded")

    def test_overbooking_needs_its_permission(self, hotel, api, api_for, make_member):
        for _ in range(3):
            book(hotel, oct_(1), oct_(3))
        front_desk = api_for(make_member("front_desk"), hotel.prop)
        response = front_desk.post(URL, payload(hotel, allow_overbooking=True), format="json")
        assert (response.status_code, response.json()["permission"]) == (403, "bookings.overbook")
        assert api.post(URL, payload(hotel, allow_overbooking=True), format="json").status_code == 201

    def test_staff_bookings_are_audited_as_the_user_whatever_the_source(self, hotel, api, owner):
        response = api.post(URL, payload(hotel, source="booking_engine"), format="json")
        assert (response.status_code, response.json()["source"]) == (201, "booking_engine")
        event = AuditEvent.objects.get(action="bookings.reservation_created")
        assert (event.source, event.actor) == ("user", owner)

    def test_front_desk_can_create_and_the_accountant_cannot(self, hotel, api_for, make_member):
        assert (
            api_for(make_member("front_desk"), hotel.prop)
            .post(URL, payload(hotel), format="json")
            .status_code
            == 201
        )
        response = api_for(make_member("accountant"), hotel.prop).post(URL, payload(hotel), format="json")
        assert (response.status_code, response.json()["permission"]) == (403, "bookings.manage")


class TestDetail:
    def test_shows_the_reservation_with_flags(self, hotel, api):
        reservation = book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["101"].pk})
        body = api.get(f"{URL}{reservation.pk}/").json()
        assert body["flags"] == {
            "ready_for_checkin": True,
            "arrives_today": True,
            "departs_today": False,
            "in_house": False,
            "unassigned": False,
            "balance_due": True,
        }
        assert body["stays"][0]["room"] == {
            "id": str(hotel.rooms["101"].pk),
            "number": "101",
            "floor": "1",
            "housekeeping_status": "clean",
        }
        Room.objects.filter(pk=hotel.rooms["101"].pk).update(housekeeping_status="dirty")
        assert api.get(f"{URL}{reservation.pk}/").json()["flags"]["ready_for_checkin"] is False

    def test_in_house_flags(self, hotel, api):
        reservation = book(hotel, oct_(1), oct_(2), stay_kwargs={"room_id": hotel.rooms["101"].pk})
        check_in(reservation.stays.get())
        hotel.prop.business_date = oct_(2)
        hotel.prop.save()
        flags = api.get(f"{URL}{reservation.pk}/").json()["flags"]
        assert (flags["in_house"], flags["departs_today"], flags["arrives_today"]) == (True, True, False)

    def test_reservations_of_other_tenants_are_404(self, hotel, api, organization):
        stranger = PropertyFactory()
        other = Reservation.objects.create(
            property=stranger,
            booker=GuestFactory(organization=stranger.organization),
            checkin_date=oct_(1),
            checkout_date=oct_(2),
        )
        assert api.get(f"{URL}{other.pk}/").status_code == 404


class TestUpdate:
    def test_patch_edits_the_free_fields(self, hotel, api, django_capture_on_commit_callbacks, signal_log):
        reservation = book(hotel, oct_(1), oct_(3))
        group = ReservationGroupFactory(property=hotel.prop)
        with django_capture_on_commit_callbacks(execute=True):
            response = api.patch(
                f"{URL}{reservation.pk}/",
                {
                    "notes": "Cuna",
                    "eta": "18:30",
                    "guarantee": "card",
                    "group_id": str(group.pk),
                    "status": "x",
                },
                format="json",
            )
        assert response.status_code == 200, response.json()
        body = response.json()
        assert (body["notes"], body["eta"], body["guarantee"], body["status"]) == (
            "Cuna",
            "18:30:00",
            "card",
            "confirmed",
        )
        assert body["group"] == {"id": str(group.pk), "name": group.name}
        (updated,) = signal_log.of("reservation_updated")
        assert updated["changes"]["notes"] == ("", "Cuna")

    def test_patch_validates(self, hotel, api):
        reservation = book(hotel, oct_(1), oct_(3))
        response = api.patch(f"{URL}{reservation.pk}/", {"guarantee": "gold"}, format="json")
        assert (response.status_code, response.json()["code"]) == (400, "validation_error")

    def test_the_booker_can_change_to_another_guest_of_the_organization(self, hotel, api, organization):
        reservation = book(hotel, oct_(1), oct_(3))
        guest = GuestFactory(organization=organization)
        response = api.patch(f"{URL}{reservation.pk}/", {"booker_id": str(guest.pk)}, format="json")
        assert (response.status_code, response.json()["booker"]["id"]) == (200, str(guest.pk))

    def test_another_organizations_guest_as_booker_is_answered_like_a_missing_one(self, hotel, api):
        """Another tenant's guest ids cannot be probed: the answer is the one of an id that does not exist."""
        reservation = book(hotel, oct_(1), oct_(3))
        url = f"{URL}{reservation.pk}/"

        foreign = api.patch(url, {"booker_id": str(GuestFactory().pk)}, format="json")
        missing = api.patch(url, {"booker_id": str(uuid4())}, format="json")

        assert (foreign.status_code, foreign.json()["code"]) == (400, "invalid_guest")
        assert foreign.json() == missing.json()
        assert Reservation.objects.get(pk=reservation.pk).booker_id == reservation.booker_id


class TestActions:
    def test_cancel_requires_confirm(self, hotel, api):
        reservation = book(hotel, oct_(1), oct_(3))
        response = api.post(f"{URL}{reservation.pk}/cancel/", {"reason": "Cambio"}, format="json")
        assert (response.status_code, response.json()["code"]) == (400, "confirmation_required")
        response = api.post(
            f"{URL}{reservation.pk}/cancel/", {"reason": "Cambio", "confirm": True}, format="json"
        )
        assert (response.status_code, response.json()["status"]) == (200, "cancelled")

    @freeze_time("2026-10-08 20:01:00+00:00")
    def test_waiving_the_fee_needs_its_permission(self, hotel, api, api_for, make_member):
        policy = CancellationPolicyFactory(property=hotel.prop, non_refundable=True)
        hotel.plan.cancellation_policy = policy
        hotel.plan.save()
        reservation = book(hotel, oct_(10), oct_(12))
        body = {"reason": "Cortesía", "waive_fee": True, "confirm": True}
        front_desk = api_for(make_member("front_desk"), hotel.prop)
        response = front_desk.post(f"{URL}{reservation.pk}/cancel/", body, format="json")
        assert (response.status_code, response.json()["permission"]) == (403, "bookings.waive_fee")
        response = api.post(f"{URL}{reservation.pk}/cancel/", body, format="json")
        assert (response.status_code, response.json()["cancellation_fee"]) == (200, "0.00")

    @freeze_time("2026-10-08 20:01:00+00:00")
    def test_cancel_preview(self, hotel, api):
        policy = CancellationPolicyFactory(
            property=hotel.prop, free_until_hours_before=48, penalty_type="first_night"
        )
        hotel.plan.cancellation_policy = policy
        hotel.plan.save()
        reservation = book(hotel, oct_(10), oct_(12))
        response = api.get(f"{URL}{reservation.pk}/cancel-preview/")
        assert response.status_code == 200
        assert response.json() == {
            "fee": "380800.00",
            "currency": "COP",
            "reason": "first_night",
            "free_until": "2026-10-08T15:00:00-05:00",
            "non_refundable": False,
            "policy": reservation.cancellation_policy_snapshot,
        }

    def test_cancelling_an_in_house_reservation_is_a_409(self, hotel, api):
        reservation = book(hotel, oct_(1), oct_(3))
        assign_room(reservation.stays.get(), hotel.rooms["101"])
        check_in(reservation.stays.get())
        response = api.post(f"{URL}{reservation.pk}/cancel/", {"reason": "-", "confirm": True}, format="json")
        assert (response.status_code, response.json()["code"]) == (409, "invalid_state")

    def test_the_accountant_cannot_cancel(self, hotel, api_for, make_member):
        reservation = book(hotel, oct_(1), oct_(3))
        response = api_for(make_member("accountant"), hotel.prop).post(
            f"{URL}{reservation.pk}/cancel/", {"reason": "-", "confirm": True}, format="json"
        )
        assert (response.status_code, response.json()["permission"]) == (403, "bookings.cancel")

    def test_confirm(self, hotel, api):
        reservation = book(hotel, oct_(3), oct_(5), status="tentative")
        response = api.post(f"{URL}{reservation.pk}/confirm/")
        assert (response.status_code, response.json()["status"], response.json()["hold_expires_at"]) == (
            200,
            "confirmed",
            None,
        )
        assert api.post(f"{URL}{reservation.pk}/confirm/").json()["code"] == "invalid_state"

    def test_no_show(self, hotel, api):
        reservation = book(hotel, oct_(1), oct_(3))
        hotel.prop.business_date = oct_(2)
        hotel.prop.save()
        response = api.post(f"{URL}{reservation.pk}/no-show/")
        assert (response.status_code, response.json()["status"], response.json()["cancellation_fee"]) == (
            200,
            "no_show",
            "380800.00",
        )
