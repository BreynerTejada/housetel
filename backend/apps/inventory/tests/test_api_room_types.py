"""`/api/v1/inventory/room-types/`: CRUD with amenities by code, unit counts, duplicate, safe changes."""

import pytest

from apps.bookings.tests.factories import StayFactory
from apps.core.models import AuditEvent
from apps.core.signals import inventory_changed
from apps.inventory.models import Photo, RoomType
from apps.inventory.tests.conftest import BASE
from apps.inventory.tests.factories import (
    AmenityFactory,
    BedFactory,
    DormRoomTypeFactory,
    RoomFactory,
    RoomTypeFactory,
)

pytestmark = pytest.mark.django_db
URL = f"{BASE}/room-types/"


def detail(room_type):
    return f"{URL}{room_type.pk}/"


class TestList:
    def test_lists_the_property_categories_with_unit_counts(self, api, prop):
        wifi = AmenityFactory(code="wifi")
        double = RoomTypeFactory(property=prop, code="DBL", sort_order=10, amenities=[wifi])
        RoomFactory(room_type=double)
        RoomFactory(room_type=double)
        RoomFactory(room_type=double, is_active=False)
        dorm = DormRoomTypeFactory(property=prop, code="D6", sort_order=20)
        dorm_room = RoomFactory(room_type=dorm)
        BedFactory(room=dorm_room)
        BedFactory(room=dorm_room)
        BedFactory(room=dorm_room, is_active=False)
        RoomTypeFactory(code="OTHER")  # another property

        response = api.get(URL)

        assert response.status_code == 200
        rows = {row["code"]: row for row in response.json()}
        assert list(rows) == ["DBL", "D6"]
        assert {
            k: rows["DBL"][k] for k in ("rooms_count", "active_rooms_count", "units_count", "amenities")
        } == {
            "rooms_count": 3,
            "active_rooms_count": 2,
            "units_count": 2,
            "amenities": ["wifi"],
        }
        assert (rows["D6"]["kind"], rows["D6"]["beds_count"], rows["D6"]["units_count"]) == ("dorm", 2, 2)

    def test_the_number_of_queries_does_not_grow_with_the_categories(self, api, prop):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def queries_to_list():
            with CaptureQueriesContext(connection) as context:
                assert api.get(URL).status_code == 200
            return len(context.captured_queries)

        def add_categories(count):
            for _ in range(count):
                room_type = RoomTypeFactory(property=prop, amenities=[AmenityFactory(), AmenityFactory()])
                RoomFactory(room_type=room_type)
                Photo.objects.create(property=prop, room_type=room_type, image="photos/x.jpg")

        add_categories(2)
        few = queries_to_list()
        add_categories(8)
        assert queries_to_list() == few

    def test_the_row_carries_every_category_parameter(self, api, prop):
        RoomTypeFactory(property=prop)
        row = api.get(URL).json()[0]
        assert set(row) >= {
            "id", "code", "name", "description", "kind", "base_occupancy", "max_adults", "max_children",
            "max_occupancy", "beds", "size_m2", "view", "smoking_allowed", "accessible", "amenities", "color",
            "housekeeping_minutes", "sort_order", "is_active", "custom_values", "rooms_count",
            "active_rooms_count", "beds_count", "units_count", "photos_count", "cover_photo",
        }  # fmt: skip


class TestCreate:
    def test_creates_a_category_in_the_active_property(self, api, prop, owner):
        AmenityFactory(code="wifi")
        response = api.post(
            URL,
            {
                "code": "sup",
                "name": {"es": "Superior", "en": "Superior"},
                "max_adults": 2,
                "max_children": 1,
                "max_occupancy": 3,
                "beds": [{"type": "king", "count": 1}],
                "size_m2": "28.00",
                "view": "balcony",
                "amenities": ["wifi"],
                "color": "#5F7F66",
            },
        )
        assert response.status_code == 201, response.json()
        body = response.json()
        assert (body["code"], body["amenities"], body["units_count"], body["size_m2"]) == (
            "SUP",
            ["wifi"],
            0,
            "28.00",
        )
        room_type = RoomType.objects.get(pk=body["id"])
        assert room_type.property == prop
        assert AuditEvent.objects.filter(action="inventory.room_type_created", actor=owner).exists()

    def test_validation_errors_are_field_errors(self, api):
        response = api.post(
            URL, {"name": {"es": ""}, "max_adults": 4, "max_occupancy": 2, "amenities": ["x"]}
        )
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == "validation_error"
        assert {"name", "amenities"} <= set(body["fields"])

    @pytest.mark.parametrize("code", ["Suite Vista", "SUÍTE", "SUITE_VISTA_AL_MAR_PREMIUM"])
    def test_the_api_rejects_invalid_codes_instead_of_rewriting_them(self, api, code):
        response = api.post(URL, {"name": "Suite", "code": code})
        assert response.status_code == 400 and "code" in response.json()["fields"]

    def test_a_body_property_is_never_trusted(self, api, prop, organization):
        from apps.core.tests.factories import PropertyFactory

        other = PropertyFactory(organization=organization)
        response = api.post(URL, {"name": "Doble", "property": str(other.pk)})
        assert response.status_code == 201
        assert RoomType.objects.get(pk=response.json()["id"]).property == prop


class TestUpdate:
    def test_updates_attributes_and_amenities(self, api, prop):
        AmenityFactory(code="wifi")
        AmenityFactory(code="tv")
        room_type = RoomTypeFactory(property=prop, amenities=[])
        response = api.patch(detail(room_type), {"view": "sea", "amenities": ["tv", "wifi"]})
        assert response.status_code == 200
        room_type.refresh_from_db()
        assert (room_type.view, sorted(room_type.amenities.values_list("code", flat=True))) == (
            "sea",
            ["tv", "wifi"],
        )

    def test_kind_cannot_change_once_it_has_rooms(self, api, prop):
        room_type = RoomTypeFactory(property=prop)
        RoomFactory(room_type=room_type)
        response = api.patch(detail(room_type), {"kind": "dorm"})
        assert response.status_code == 400 and "kind" in response.json()["fields"]

    def test_deactivating_signals_inventory(self, api, prop, capture):
        room_type = RoomTypeFactory(property=prop)
        received = capture(inventory_changed, lambda: api.patch(detail(room_type), {"is_active": False}))
        assert received == [{"property": prop, "room_type_ids": [room_type.pk], "start": None, "end": None}]

    def test_a_category_with_active_reservations_cannot_be_deactivated(self, api, prop):
        room_type = RoomTypeFactory(property=prop)
        StayFactory(reservation__property=prop, room_type=room_type)
        response = api.patch(detail(room_type), {"is_active": False})
        assert (response.status_code, response.json()["code"]) == (409, "room_type_in_use")
        assert RoomType.objects.get(pk=room_type.pk).is_active

    def test_an_occupancy_change_that_breaks_a_room_override_is_rejected(self, api, prop):
        room_type = RoomTypeFactory(
            property=prop, base_occupancy=2, max_adults=2, max_children=1, max_occupancy=4
        )
        RoomFactory(room_type=room_type, number="306", overrides={"max_adults": 4})
        RoomFactory(room_type=room_type, number="301")

        response = api.patch(detail(room_type), {"max_occupancy": 3})

        assert response.status_code == 400
        assert "306" in str(response.json()["fields"]["max_occupancy"]), response.json()
        assert RoomType.objects.get(pk=room_type.pk).max_occupancy == 4

    def test_an_occupancy_change_the_room_overrides_still_fit_is_saved(self, api, prop):
        room_type = RoomTypeFactory(
            property=prop, base_occupancy=2, max_adults=2, max_children=1, max_occupancy=4
        )
        RoomFactory(room_type=room_type, number="306", overrides={"max_adults": 3})

        response = api.patch(detail(room_type), {"max_occupancy": 3})

        assert response.status_code == 200, response.json()
        assert RoomType.objects.get(pk=room_type.pk).max_occupancy == 3

    def test_other_attributes_do_not_signal(self, api, prop, capture):
        room_type = RoomTypeFactory(property=prop)
        assert capture(inventory_changed, lambda: api.patch(detail(room_type), {"color": "#000000"})) == []


class TestDelete:
    def test_deletes_a_category_without_rooms(self, api, prop):
        room_type = RoomTypeFactory(property=prop)
        assert api.delete(detail(room_type)).status_code == 204
        assert not RoomType.objects.filter(pk=room_type.pk).exists()

    def test_a_category_with_rooms_is_in_use(self, api, prop):
        room_type = RoomTypeFactory(property=prop)
        RoomFactory(room_type=room_type)
        response = api.delete(detail(room_type))
        assert (response.status_code, response.json()["code"]) == (409, "room_type_in_use")

    def test_a_category_with_reservation_history_is_in_use(self, api, prop):
        room_type = RoomTypeFactory(property=prop)
        StayFactory(reservation__property=prop, room_type=room_type, status="checked_out")
        response = api.delete(detail(room_type))
        assert (response.status_code, response.json()["code"]) == (409, "room_type_in_use")


class TestDuplicate:
    def test_copies_the_parameters_and_amenities_with_a_new_code(self, api, prop):
        wifi = AmenityFactory(code="wifi")
        source = RoomTypeFactory(
            property=prop, code="STE", name={"es": "Suite", "en": "Suite"}, view="sea", amenities=[wifi],
            custom_values={}, color="#B4583B",
        )  # fmt: skip
        RoomFactory(room_type=source)
        response = api.post(f"{detail(source)}duplicate/", {})
        assert response.status_code == 201
        body = response.json()
        assert body["id"] != str(source.pk)
        assert (body["code"], body["name"], body["view"], body["amenities"], body["color"]) == (
            "STE2",
            {"es": "Suite (copia)", "en": "Suite (copy)"},
            "sea",
            ["wifi"],
            "#B4583B",
        )
        assert body["rooms_count"] == 0

    def test_accepts_a_code_and_name(self, api, prop):
        source = RoomTypeFactory(property=prop, code="STE")
        response = api.post(f"{detail(source)}duplicate/", {"code": "STX", "name": {"es": "Suite XL"}})
        assert (response.json()["code"], response.json()["name"]) == ("STX", {"es": "Suite XL"})


class TestPhotosInList:
    def test_cover_photo_is_the_first_photo(self, api, prop):
        room_type = RoomTypeFactory(property=prop)
        Photo.objects.create(property=prop, room_type=room_type, image="photos/b.jpg", sort_order=2)
        Photo.objects.create(property=prop, room_type=room_type, image="photos/a.jpg", sort_order=1)
        row = api.get(URL).json()[0]
        assert (row["photos_count"], row["cover_photo"]) == (2, "/media/photos/a.jpg")
