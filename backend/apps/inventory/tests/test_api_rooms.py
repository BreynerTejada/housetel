"""`/api/v1/inventory/rooms/`: rooms inherit from their category; the API exposes the resolved attributes."""

import pytest

from apps.bookings.tests.factories import StayFactory
from apps.core.models import AuditEvent
from apps.core.signals import inventory_changed, room_status_changed
from apps.core.tests.factories import PropertyFactory
from apps.inventory.models import CustomFieldDefinition, Room
from apps.inventory.services import block_room
from apps.inventory.tests.conftest import BASE
from apps.inventory.tests.factories import AmenityFactory, DormRoomTypeFactory, RoomFactory, RoomTypeFactory

pytestmark = pytest.mark.django_db
URL = f"{BASE}/rooms/"


def detail(room, suffix=""):
    return f"{URL}{room.pk}/{suffix}"


@pytest.fixture
def suite(prop):
    tub, wifi = AmenityFactory(code="bathtub"), AmenityFactory(code="wifi")
    room_type = RoomTypeFactory(
        property=prop, code="STE", view="city", max_adults=2, max_children=1, max_occupancy=3,
        amenities=[wifi], custom_values={"orientation": "city"},
    )  # fmt: skip
    return room_type, tub


class TestList:
    def test_rooms_carry_their_effective_attributes(self, api, suite):
        room_type, tub = suite
        room = RoomFactory(room_type=room_type, number="306", floor="3", overrides={"view": "sea"})
        room.extra_amenities.set([tub])

        response = api.get(URL)

        assert response.status_code == 200
        [row] = response.json()
        assert (row["number"], row["room_type"], row["room_type_code"], row["kind"]) == (
            "306",
            str(room_type.pk),
            "STE",
            "private",
        )
        assert row["overridden_fields"] == ["view"]
        assert (row["effective"]["view"], row["effective"]["max_adults"]) == ("sea", 2)
        assert row["effective"]["amenities"] == ["bathtub", "wifi"]
        assert row["effective"]["custom_values"] == {"orientation": "city"}
        assert (row["extra_amenities"], row["removed_amenities"]) == (["bathtub"], [])

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("floor=2", ["201"]),
            ("housekeeping_status=dirty", ["102"]),
            ("is_active=false", ["103"]),
            ("search=20", ["201"]),
        ],
    )
    def test_filters(self, api, prop, query, expected):
        room_type = RoomTypeFactory(property=prop)
        RoomFactory(room_type=room_type, number="101", floor="1")
        RoomFactory(room_type=room_type, number="102", floor="1", housekeeping_status="dirty")
        RoomFactory(room_type=room_type, number="103", floor="1", is_active=False)
        RoomFactory(room_type=room_type, number="201", floor="2")
        numbers = [row["number"] for row in api.get(f"{URL}?{query}").json()]
        assert numbers == expected

    def test_filters_by_category(self, api, prop):
        first, second = RoomTypeFactory(property=prop), RoomTypeFactory(property=prop)
        RoomFactory(room_type=first, number="101")
        RoomFactory(room_type=second, number="201")
        assert [r["number"] for r in api.get(f"{URL}?room_type={second.pk}").json()] == ["201"]

    def test_shows_an_active_block(self, api, prop):
        room = RoomFactory(room_type__property=prop)
        block_room(
            room,
            start=prop.business_date,
            end=prop.business_date.replace(year=2099),
            kind="maintenance",
            reason="Pintura",
        )
        row = api.get(URL).json()[0]
        assert (row["active_block"]["kind"], row["active_block"]["reason"]) == ("maintenance", "Pintura")

    def test_the_list_does_not_query_per_room(self, api, prop, django_assert_max_num_queries):
        room_type = RoomTypeFactory(property=prop, amenities=[AmenityFactory()])
        for number in range(101, 121):
            RoomFactory(room_type=room_type, number=str(number))
        with django_assert_max_num_queries(20):
            assert len(api.get(URL).json()) == 20

    def test_the_number_of_queries_does_not_grow_with_the_rooms(self, api, prop):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def queries_to_list():
            with CaptureQueriesContext(connection) as context:
                assert api.get(URL).status_code == 200
            return len(context.captured_queries)

        room_type = RoomTypeFactory(property=prop, amenities=[AmenityFactory()])
        dorm_type = DormRoomTypeFactory(property=prop)

        def add_rooms(first, count):
            for number in range(first, first + count):
                room = RoomFactory(room_type=room_type if number % 2 else dorm_type, number=str(number))
                room.extra_amenities.set([AmenityFactory()])
                room.connecting_rooms.set(Room.objects.filter(property=prop)[:1])
                block_room(room, start=prop.business_date, end=prop.business_date.replace(year=2099),
                           kind="maintenance", reason="")  # fmt: skip

        add_rooms(100, 3)
        few = queries_to_list()
        add_rooms(200, 12)
        assert queries_to_list() == few


class TestCreateAndUpdate:
    def test_creates_a_room_with_overrides_and_signals(self, api, prop, suite, capture):
        room_type, _ = suite
        responses = []
        received = capture(
            inventory_changed,
            lambda: responses.append(
                api.post(
                    URL,
                    {
                        "room_type": str(room_type.pk),
                        "number": " 306 ",
                        "floor": "3",
                        "overrides": {"view": "sea", "size_m2": 48},
                    },
                )  # fmt: skip
            ),
        )
        response = responses[0]
        assert response.status_code == 201, response.json()
        body = response.json()
        assert (body["number"], body["overrides"], body["effective"]["size_m2"]) == (
            "306",
            {"view": "sea", "size_m2": "48.00"},
            "48.00",
        )
        assert received == [{"property": prop, "room_type_ids": [room_type.pk], "start": None, "end": None}]

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"number": "101"}, "number"),  # exists
            ({"overrides": {"color": "#000"}}, "overrides"),
            ({"overrides": {"max_adults": 9}}, "overrides"),  # above the category's max occupancy
            ({"overrides": {"beds": "king"}}, "overrides"),
            ({"custom_values": {"nope": 1}}, "custom_values"),
            ({"extra_amenities": ["moon"]}, "extra_amenities"),
        ],
    )
    def test_rejects_invalid_rooms(self, api, prop, suite, payload, field):
        room_type, _ = suite
        RoomFactory(room_type=room_type, number="101")
        response = api.post(URL, {"room_type": str(room_type.pk), "number": "999", **payload})
        assert response.status_code == 400 and field in response.json()["fields"], response.json()

    def test_rejects_a_category_of_another_property(self, api, organization):
        foreign = RoomTypeFactory(property=PropertyFactory(organization=organization))
        response = api.post(URL, {"room_type": str(foreign.pk), "number": "101"})
        assert response.status_code == 400 and "room_type" in response.json()["fields"]

    def test_patch_replaces_overrides_and_validates_custom_values(self, api, prop, suite):
        room_type, _ = suite
        CustomFieldDefinition.objects.create(
            organization=prop.organization, applies_to="room", key="minibar", field_type="boolean",
            label={"es": "Minibar"},
        )  # fmt: skip
        CustomFieldDefinition.objects.create(
            organization=prop.organization, applies_to="room_type", key="orientation", field_type="select",
            label={"es": "Orientación"}, options=[{"value": "sea"}, {"value": "city"}], required=True,
        )  # fmt: skip
        room = RoomFactory(room_type=room_type, overrides={"view": "sea"})
        response = api.patch(
            detail(room),
            {"overrides": {"max_adults": 3}, "custom_values": {"minibar": True, "orientation": "sea"}},
        )
        assert response.status_code == 200, response.json()
        body = response.json()
        assert (body["overrides"], body["overridden_fields"]) == ({"max_adults": 3}, ["max_adults"])
        assert body["effective"]["custom_values"] == {"orientation": "sea", "minibar": True}
        assert body["effective"]["overridden_custom_fields"] == ["minibar", "orientation"]

    def test_housekeeping_status_is_not_writable_here(self, api, prop):
        room = RoomFactory(room_type__property=prop, housekeeping_status="clean")
        api.patch(detail(room), {"housekeeping_status": "dirty"})
        assert Room.objects.get(pk=room.pk).housekeeping_status == "clean"

    def test_changing_category_signals_both_categories(self, api, prop, capture):
        room = RoomFactory(room_type__property=prop)
        target = RoomTypeFactory(property=prop)
        received = capture(inventory_changed, lambda: api.patch(detail(room), {"room_type": str(target.pk)}))
        assert len(received) == 1 and set(received[0]["room_type_ids"]) == {room.room_type_id, target.pk}

    def test_a_room_with_active_stays_cannot_change_category_or_be_deactivated(self, api, prop):
        room = RoomFactory(room_type__property=prop)
        StayFactory(reservation__property=prop, room_type=room.room_type, room=room)
        target = RoomTypeFactory(property=prop)
        for payload in ({"room_type": str(target.pk)}, {"is_active": False}):
            response = api.patch(detail(room), payload)
            assert (response.status_code, response.json()["code"]) == (409, "room_in_use")

    def test_edits_are_audited(self, api, prop, owner):
        room = RoomFactory(room_type__property=prop, floor="1")
        api.patch(detail(room), {"floor": "2"})
        event = AuditEvent.objects.get(action="inventory.room_updated")
        assert (event.actor, event.changes["floor"]) == (owner, ["1", "2"])


class TestDelete:
    def test_deletes_an_unused_room(self, api, prop):
        room = RoomFactory(room_type__property=prop)
        assert api.delete(detail(room)).status_code == 204
        assert not Room.objects.filter(pk=room.pk).exists()

    def test_a_room_with_active_reservations_answers_409_room_in_use(self, api, prop):
        room = RoomFactory(room_type__property=prop)
        StayFactory(reservation__property=prop, room_type=room.room_type, room=room)
        response = api.delete(detail(room))
        assert (response.status_code, response.json()["code"]) == (409, "room_in_use")
        assert Room.objects.filter(pk=room.pk).exists()


class TestBulkCreate:
    def test_creates_the_rooms_of_a_range(self, api, prop):
        room_type = RoomTypeFactory(property=prop)
        response = api.post(
            f"{URL}bulk-create/", {"room_type": str(room_type.pk), "numbers": "101-103,105", "floor": "1"}
        )
        assert response.status_code == 201, response.json()
        assert response.json()["count"] == 4
        assert [row["number"] for row in response.json()["rooms"]] == ["101", "102", "103", "105"]
        assert Room.objects.filter(room_type=room_type, floor="1").count() == 4

    def test_duplicates_answer_400_listing_them(self, api, prop):
        room_type = RoomTypeFactory(property=prop)
        RoomFactory(room_type=room_type, number="102")
        response = api.post(f"{URL}bulk-create/", {"room_type": str(room_type.pk), "numbers": "101-103"})
        assert response.status_code == 400
        assert (response.json()["code"], response.json()["duplicates"]) == ("duplicate_room_numbers", ["102"])
        assert Room.objects.count() == 1

    def test_invalid_ranges_answer_400(self, api, prop):
        room_type = RoomTypeFactory(property=prop)
        response = api.post(f"{URL}bulk-create/", {"room_type": str(room_type.pk), "numbers": "110-101"})
        assert (response.status_code, response.json()["code"]) == (400, "invalid_room_numbers")
        assert "numbers" in response.json()["fields"]

    def test_dorms_get_their_beds(self, api, prop):
        dorm = DormRoomTypeFactory(property=prop)
        response = api.post(
            f"{URL}bulk-create/", {"room_type": str(dorm.pk), "numbers": "D1", "beds_per_room": 6}
        )
        assert response.status_code == 201
        assert response.json()["rooms"][0]["active_beds_count"] == 6


class TestBulkUpdate:
    def test_only_the_selected_rooms_change(self, api, prop):
        room_type = RoomTypeFactory(property=prop, view="city")
        rooms = [RoomFactory(room_type=room_type, number=str(n), floor="1") for n in (101, 102, 103)]
        response = api.post(
            f"{URL}bulk-update/",
            {"ids": [str(rooms[0].pk), str(rooms[2].pk)], "set": {"floor": "5", "view": "sea"}, "reset": []},
        )
        assert response.status_code == 200, response.json()
        assert response.json()["updated"] == 2
        state = {room.number: (room.floor, room.overrides) for room in Room.objects.all()}
        assert state == {"101": ("5", {"view": "sea"}), "102": ("1", {}), "103": ("5", {"view": "sea"})}

    def test_invalid_payloads_answer_400(self, api, prop):
        room = RoomFactory(room_type__property=prop)
        response = api.post(f"{URL}bulk-update/", {"ids": [str(room.pk)], "set": {"color": "#fff"}})
        assert response.status_code == 400 and "color" in response.json()["fields"]


class TestInheritanceEndpoints:
    def test_effective_includes_the_inherited_values(self, api, suite):
        room_type, _ = suite
        room = RoomFactory(room_type=room_type, overrides={"view": "sea"})
        body = api.get(detail(room, "effective/")).json()
        assert (body["view"], body["overridden_fields"]) == ("sea", ["view"])
        assert body["inherited"]["view"] == "city"
        assert (body["inherited"]["amenities"], body["inherited"]["custom_values"]) == (
            ["wifi"],
            {"orientation": "city"},
        )

    def test_reset_override_restores_the_category_value(self, api, suite):
        room_type, _ = suite
        room = RoomFactory(room_type=room_type, overrides={"view": "sea", "max_adults": 1})
        response = api.post(detail(room, "reset-override/"), {"field": "view"})
        assert response.status_code == 200
        assert (response.json()["overrides"], response.json()["effective"]["view"]) == (
            {"max_adults": 1},
            "city",
        )

    def test_reset_override_rejects_unknown_fields(self, api, prop):
        room = RoomFactory(room_type__property=prop)
        assert api.post(detail(room, "reset-override/"), {"field": "color"}).status_code == 400


class TestStatus:
    def test_changes_the_housekeeping_status_through_the_service(self, api, prop, owner, capture):
        room = RoomFactory(room_type__property=prop, housekeeping_status="dirty")
        responses = []
        received = capture(
            room_status_changed,
            lambda: responses.append(api.post(detail(room, "status/"), {"housekeeping_status": "clean"})),
        )
        assert responses[0].status_code == 200
        assert responses[0].json()["housekeeping_status"] == "clean"
        assert [(r["old"], r["new"]) for r in received] == [("dirty", "clean")]
        assert AuditEvent.objects.get(action="inventory.room_status_changed").actor == owner

    def test_rejects_unknown_statuses(self, api, prop):
        room = RoomFactory(room_type__property=prop)
        response = api.post(detail(room, "status/"), {"housekeeping_status": "sparkling"})
        assert response.status_code == 400
