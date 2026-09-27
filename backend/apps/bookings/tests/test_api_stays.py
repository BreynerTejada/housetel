"""Stay actions API (`/api/v1/bookings/stays/{id}/…`, plan B2b › API): modify, assign, unassign, check-in,
check-out, occupants. Each action answers with the updated reservation detail."""

from uuid import uuid4

import pytest

from apps.bookings.models import Stay
from apps.bookings.services.reservations import assign_room
from apps.bookings.tests.helpers import book, oct_
from apps.core.tests.factories import PropertyFactory
from apps.guests.tests.factories import GuestFactory
from apps.inventory.models import Room
from apps.inventory.tests.factories import RoomFactory, RoomTypeFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/bookings/stays/"


def new_stay(hotel, checkin=None, checkout=None, room=None, **kwargs):
    stay = book(hotel, checkin or oct_(1), checkout or oct_(3), **kwargs).stays.get()
    if room is not None:
        assign_room(stay, room)
    return Stay.objects.get(pk=stay.pk)


def stay_of(response, stay):
    return next(item for item in response.json()["stays"] if item["id"] == str(stay.pk))


class TestRetrieve:
    def test_shows_the_stay(self, hotel, api):
        stay = new_stay(hotel)
        body = api.get(f"{URL}{stay.pk}/").json()
        assert (body["id"], body["reservation_id"], body["code"]) == (
            str(stay.pk),
            str(stay.reservation_id),
            stay.reservation.code,
        )

    def test_stays_of_other_properties_are_404(self, hotel, api, organization):
        stay = new_stay(hotel)
        other = PropertyFactory(organization=organization)
        client = api
        client.credentials(HTTP_X_PROPERTY_ID=str(other.pk))
        assert client.get(f"{URL}{stay.pk}/").status_code == 404
        assert client.post(f"{URL}{stay.pk}/check-in/").status_code == 404


class TestModify:
    def test_extends_and_reprices(self, hotel, api):
        stay = new_stay(hotel)
        response = api.post(f"{URL}{stay.pk}/modify/", {"checkout": "2026-10-04"}, format="json")
        assert response.status_code == 200, response.json()
        assert (response.json()["checkout_date"], response.json()["total_amount"]) == (
            "2026-10-04",
            "1142400.00",
        )

    def test_changes_category_and_plan_by_id(self, hotel, api):
        stay = new_stay(hotel)
        response = api.post(
            f"{URL}{stay.pk}/modify/",
            {"room_type_id": str(hotel.ste.pk), "rate_plan_id": str(hotel.plan.pk), "reprice": True},
            format="json",
        )
        assert stay_of(response, stay)["room_type"]["code"] == "STE"

    def test_no_availability_is_a_409(self, hotel, api):
        for _ in range(3):
            book(hotel, oct_(3), oct_(4))
        stay = new_stay(hotel)
        response = api.post(f"{URL}{stay.pk}/modify/", {"checkout": "2026-10-04"}, format="json")
        assert (response.status_code, response.json()["code"]) == (409, "no_availability")

    def test_unknown_category_is_a_400(self, hotel, api):
        stay = new_stay(hotel)
        response = api.post(
            f"{URL}{stay.pk}/modify/", {"room_type_id": str(PropertyFactory().pk)}, format="json"
        )
        assert (response.status_code, response.json()["code"]) == (400, "invalid_room_type")


class TestModifyPreview:
    def test_shows_the_new_price_and_changes_nothing(self, hotel, api):
        stay = new_stay(hotel, room=hotel.rooms["101"])
        response = api.post(
            f"{URL}{stay.pk}/modify-preview/", {"checkout": "2026-10-04", "reprice": True}, format="json"
        )
        assert response.status_code == 200, response.json()
        body = response.json()
        assert set(body) == {
            "stay",
            "room_kept",
            "current_total",
            "difference",
            "reservation_total",
            "balance",
        }
        assert set(body["stay"]) == {
            "id",
            "checkin_date",
            "checkout_date",
            "nights",
            "room_type_id",
            "rate_plan_id",
            "room_id",
            "bed_id",
            "adults",
            "children",
            "nightly_rates",
            "total_amount",
        }
        assert (body["stay"]["total_amount"], body["difference"], body["room_kept"]) == (
            "1142400.00",
            "380800.00",
            True,
        )
        assert Stay.objects.get(pk=stay.pk).checkout_date == oct_(3)

    def test_a_category_change_by_id(self, hotel, api):
        stay = new_stay(hotel)
        response = api.post(
            f"{URL}{stay.pk}/modify-preview/", {"room_type_id": str(hotel.ste.pk)}, format="json"
        )
        assert response.json()["stay"]["room_type_id"] == str(hotel.ste.pk)

    def test_no_availability_is_a_409(self, hotel, api):
        for _ in range(3):
            book(hotel, oct_(3), oct_(4))
        stay = new_stay(hotel)
        response = api.post(f"{URL}{stay.pk}/modify-preview/", {"checkout": "2026-10-04"}, format="json")
        assert (response.status_code, response.json()["code"]) == (409, "no_availability")

    def test_needs_manage(self, hotel, api_for, make_member):
        stay = new_stay(hotel)
        response = api_for(make_member("accountant"), hotel.prop).post(
            f"{URL}{stay.pk}/modify-preview/", {"checkout": "2026-10-04"}, format="json"
        )
        assert (response.status_code, response.json()["permission"]) == (403, "bookings.manage")


class TestAssign:
    def test_assigns_and_unassigns(self, hotel, api):
        stay = new_stay(hotel)
        response = api.post(f"{URL}{stay.pk}/assign/", {"room_id": str(hotel.rooms["102"].pk)}, format="json")
        assert response.status_code == 200
        assert stay_of(response, stay)["room"]["number"] == "102"
        response = api.post(f"{URL}{stay.pk}/unassign/")
        assert (response.status_code, stay_of(response, stay)["room"]) == (200, None)

    def test_an_occupied_room_is_a_409_and_another_category_needs_force(self, hotel, api):
        new_stay(hotel, room=hotel.rooms["101"])
        stay = new_stay(hotel)
        response = api.post(f"{URL}{stay.pk}/assign/", {"room_id": str(hotel.rooms["101"].pk)}, format="json")
        assert (response.status_code, response.json()["code"]) == (409, "no_availability")
        response = api.post(f"{URL}{stay.pk}/assign/", {"room_id": str(hotel.rooms["301"].pk)}, format="json")
        assert (response.status_code, response.json()["code"]) == (400, "category_mismatch")
        response = api.post(
            f"{URL}{stay.pk}/assign/", {"room_id": str(hotel.rooms["301"].pk), "force": True}, format="json"
        )
        assert stay_of(response, stay)["room"]["number"] == "301"

    def test_a_dorm_bed(self, hotel, api):
        stay = new_stay(hotel, room_type=hotel.dorm_type, adults=1)
        response = api.post(
            f"{URL}{stay.pk}/assign/",
            {"room_id": str(hotel.dorm.pk), "bed_id": str(hotel.beds["C"].pk)},
            format="json",
        )
        assert stay_of(response, stay)["bed"] == {"id": str(hotel.beds["C"].pk), "label": "C"}

    def test_rooms_of_other_properties_are_rejected(self, hotel, api):
        foreign_room = RoomFactory(room_type=RoomTypeFactory(property=PropertyFactory()), number="999")
        stay = new_stay(hotel)
        response = api.post(f"{URL}{stay.pk}/assign/", {"room_id": str(foreign_room.pk)}, format="json")
        assert (response.status_code, response.json()["code"]) == (400, "invalid_room")

    def test_the_room_id_is_required(self, hotel, api):
        response = api.post(f"{URL}{new_stay(hotel).pk}/assign/", {}, format="json")
        assert (response.status_code, response.json()["code"]) == (400, "validation_error")


class TestRoomOptions:
    def test_lists_where_the_stay_can_go(self, hotel, api):
        stay = new_stay(hotel)
        response = api.get(f"{URL}{stay.pk}/room-options/")
        assert response.status_code == 200
        body = response.json()
        assert [item["room_number"] for item in body] == ["101", "102", "201", "301"]
        assert set(body[0]) == {
            "room_id",
            "room_number",
            "floor",
            "room_type_id",
            "room_type_code",
            "bed_id",
            "bed_label",
            "housekeeping_status",
            "ready",
            "same_category",
        }
        assert (body[0]["same_category"], body[-1]["same_category"]) == (True, False)

    def test_needs_view_and_the_stay_of_the_active_property(self, hotel, api_for, make_member, organization):
        stay = new_stay(hotel)
        response = api_for(make_member("housekeeping"), hotel.prop).get(f"{URL}{stay.pk}/room-options/")
        assert (response.status_code, response.json()["permission"]) == (403, "bookings.view")
        other = api_for(make_member("owner"), PropertyFactory(organization=organization))
        assert other.get(f"{URL}{stay.pk}/room-options/").status_code == 404


class TestCheckInOut:
    def test_check_in_and_out(self, hotel, api):
        stay = new_stay(hotel, oct_(1), oct_(2), room=hotel.rooms["101"])
        response = api.post(f"{URL}{stay.pk}/check-in/")
        assert (response.status_code, response.json()["status"]) == (200, "checked_in")

        hotel.prop.business_date = oct_(2)
        hotel.prop.save()
        response = api.post(f"{URL}{stay.pk}/check-out/")
        assert (response.status_code, response.json()["code"], response.json()["amount"]) == (
            409,
            "balance_due",
            "380800.00",
        )
        response = api.post(f"{URL}{stay.pk}/check-out/", {"force": True}, format="json")
        assert (response.status_code, response.json()["status"]) == (200, "checked_out")

    def test_a_dirty_room_is_a_409_room_not_ready(self, hotel, api):
        Room.objects.filter(pk=hotel.rooms["101"].pk).update(housekeeping_status="dirty")
        stay = new_stay(hotel, room=hotel.rooms["101"])
        response = api.post(f"{URL}{stay.pk}/check-in/")
        assert (response.status_code, response.json()["code"]) == (409, "room_not_ready")
        assert api.post(f"{URL}{stay.pk}/check-in/", {"force": True}, format="json").status_code == 200

    def test_front_desk_checks_in_but_cannot_force_a_checkout_with_balance(self, hotel, api_for, make_member):
        front_desk = api_for(make_member("front_desk"), hotel.prop)
        stay = new_stay(hotel, oct_(1), oct_(2), room=hotel.rooms["101"])
        assert front_desk.post(f"{URL}{stay.pk}/check-in/").status_code == 200
        response = front_desk.post(f"{URL}{stay.pk}/check-out/", {"force": True}, format="json")
        assert (response.status_code, response.json()["permission"]) == (
            403,
            "bookings.checkout_with_balance",
        )

    def test_housekeeping_cannot_check_in(self, hotel, api_for, make_member):
        stay = new_stay(hotel, room=hotel.rooms["101"])
        response = api_for(make_member("housekeeping"), hotel.prop).post(f"{URL}{stay.pk}/check-in/")
        assert (response.status_code, response.json()["permission"]) == (403, "bookings.checkin")


class TestOccupants:
    def test_add_by_id_or_data_and_remove(self, hotel, api, organization):
        stay = new_stay(hotel)
        guest = GuestFactory(organization=organization)

        response = api.post(f"{URL}{stay.pk}/occupants/", {"guest_id": str(guest.pk)}, format="json")
        assert response.status_code == 200
        response = api.post(
            f"{URL}{stay.pk}/occupants/",
            {
                "guest": {
                    "first_name": "Mateo",
                    "last_name": "Gómez",
                    "document_type": "TI",
                    "document_number": "1099",
                }
            },
            format="json",
        )
        occupants = stay_of(response, stay)["occupants"]
        assert {item["first_name"] for item in occupants} == {guest.first_name, "Mateo"}

        response = api.delete(f"{URL}{stay.pk}/occupants/?guest_id={guest.pk}")
        assert [item["first_name"] for item in stay_of(response, stay)["occupants"]] == ["Mateo"]

    def test_a_guest_of_another_organization_is_rejected(self, hotel, api):
        stay = new_stay(hotel)
        stranger = GuestFactory()
        response = api.post(f"{URL}{stay.pk}/occupants/", {"guest_id": str(stranger.pk)}, format="json")
        assert (response.status_code, response.json()["code"]) == (400, "invalid_guest")
        assert not Stay.objects.get(pk=stay.pk).occupants.exists()

    @pytest.mark.parametrize("method", ["post", "delete"])
    def test_another_organizations_guest_is_answered_like_a_missing_one(self, hotel, api, method):
        """Another tenant's guest ids cannot be probed: the answer is the one of an id that does not exist."""
        stay = new_stay(hotel)

        def call(guest_id):
            if method == "delete":
                return api.delete(f"{URL}{stay.pk}/occupants/?guest_id={guest_id}")
            return api.post(f"{URL}{stay.pk}/occupants/", {"guest_id": str(guest_id)}, format="json")

        foreign, missing = call(GuestFactory().pk), call(uuid4())

        assert (foreign.status_code, foreign.json()["code"]) == (400, "invalid_guest")
        assert foreign.json() == missing.json()
