"""B1 inventory services: block overlaps, bulk creation, safe deletion, bulk update and inheritance reset."""

from datetime import date
from decimal import Decimal

import pytest

from apps.bookings.tests.factories import StayFactory
from apps.core.errors import DomainError
from apps.core.models import AuditEvent
from apps.core.signals import inventory_changed
from apps.core.tests.factories import PropertyFactory
from apps.inventory.models import Bed, CustomFieldDefinition, Room, RoomBlock
from apps.inventory.services import (
    block_room,
    bulk_create_rooms,
    bulk_update_rooms,
    delete_room,
    effective_attributes,
    release_block,
    reset_override,
)
from apps.inventory.tests.factories import (
    AmenityFactory,
    BedFactory,
    DormRoomTypeFactory,
    RoomFactory,
    RoomTypeFactory,
)
from apps.inventory.tests.test_services_basic import listen

pytestmark = pytest.mark.django_db

OCT = lambda day: date(2026, 10, day)  # noqa: E731


def captured(signal, django_capture_on_commit_callbacks, action):
    received, stop = listen(signal)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            result = action()
    finally:
        stop()
    return result, received


class TestBlockOverlaps:
    def test_rejects_an_overlapping_active_block_of_the_same_room(self, prop):
        room = RoomFactory(room_type__property=prop)
        block_room(room, start=OCT(1), end=OCT(5), kind="maintenance", reason="")
        with pytest.raises(DomainError) as exc:
            block_room(room, start=OCT(4), end=OCT(8), kind="owner_hold", reason="")
        assert (exc.value.code, exc.value.status_code) == ("block_overlap", 409)
        assert RoomBlock.objects.count() == 1

    def test_back_to_back_and_released_blocks_do_not_overlap(self, prop):
        room = RoomFactory(room_type__property=prop)
        first = block_room(room, start=OCT(1), end=OCT(5), kind="maintenance", reason="")
        block_room(room, start=OCT(5), end=OCT(7), kind="maintenance", reason="")  # end is exclusive
        release_block(first)
        block_room(room, start=OCT(2), end=OCT(4), kind="owner_hold", reason="")
        assert RoomBlock.objects.filter(released_at__isnull=True).count() == 2

    def test_other_rooms_are_independent(self, prop):
        room_type = RoomTypeFactory(property=prop)
        block_room(RoomFactory(room_type=room_type), start=OCT(1), end=OCT(5), kind="maintenance", reason="")
        block_room(RoomFactory(room_type=room_type), start=OCT(1), end=OCT(5), kind="maintenance", reason="")

    def test_dorm_room_blocks_and_bed_blocks_exclude_each_other(self, prop):
        dorm = RoomFactory(room_type=DormRoomTypeFactory(property=prop))
        bed_a, bed_b = BedFactory(room=dorm), BedFactory(room=dorm)
        block_room(dorm, start=OCT(1), end=OCT(3), kind="maintenance", reason="", bed=bed_a)
        block_room(dorm, start=OCT(1), end=OCT(3), kind="maintenance", reason="", bed=bed_b)
        with pytest.raises(DomainError) as same_bed:
            block_room(dorm, start=OCT(2), end=OCT(4), kind="maintenance", reason="", bed=bed_a)
        with pytest.raises(DomainError) as whole_room:
            block_room(dorm, start=OCT(2), end=OCT(4), kind="maintenance", reason="")
        assert same_bed.value.code == whole_room.value.code == "block_overlap"


class TestBulkCreateRooms:
    def test_parses_ranges_and_creates_every_room(self, prop, owner, django_capture_on_commit_callbacks):
        room_type = RoomTypeFactory(property=prop)
        rooms, received = captured(
            inventory_changed,
            django_capture_on_commit_callbacks,
            lambda: bulk_create_rooms(
                prop, room_type=room_type, numbers="101-103,105", floor="1", actor=owner
            ),
        )
        assert [room.number for room in rooms] == ["101", "102", "103", "105"]
        assert set(Room.objects.filter(room_type=room_type).values_list("floor", flat=True)) == {"1"}
        assert received == [{"property": prop, "room_type_ids": [room_type.pk], "start": None, "end": None}]
        assert AuditEvent.objects.filter(action="inventory.rooms_bulk_created", actor=owner).exists()

    def test_lists_the_duplicates_and_creates_nothing(self, prop):
        room_type = RoomTypeFactory(property=prop)
        RoomFactory(room_type=room_type, number="102")
        with pytest.raises(DomainError) as exc:
            bulk_create_rooms(prop, room_type=room_type, numbers="101-103,101")
        assert (exc.value.code, exc.value.status_code) == ("duplicate_room_numbers", 400)
        assert exc.value.extra["duplicates"] == ["101", "102"]
        assert Room.objects.count() == 1

    def test_creates_dorm_beds_and_applies_room_custom_field_defaults(self, prop):
        CustomFieldDefinition.objects.create(
            organization=prop.organization, applies_to="room", key="minibar", field_type="boolean",
            label={"es": "Minibar"}, default_value=False,
        )  # fmt: skip
        dorm_type = DormRoomTypeFactory(property=prop)
        rooms = bulk_create_rooms(prop, room_type=dorm_type, numbers="D1-D2", beds_per_room=4)
        assert Bed.objects.filter(room__in=rooms).count() == 8
        assert {room.custom_values["minibar"] for room in Room.objects.filter(room_type=dorm_type)} == {False}

    def test_rejects_a_room_type_of_another_property(self, prop, organization):
        foreign = RoomTypeFactory(property=PropertyFactory(organization=organization))
        with pytest.raises(DomainError) as exc:
            bulk_create_rooms(prop, room_type=foreign, numbers="101")
        assert exc.value.code == "validation_error" and "room_type" in exc.value.extra["fields"]


class TestDeleteRoom:
    def test_deletes_an_unused_room_and_signals(self, prop, owner, django_capture_on_commit_callbacks):
        room = RoomFactory(room_type__property=prop)
        _, received = captured(
            inventory_changed, django_capture_on_commit_callbacks, lambda: delete_room(room, actor=owner)
        )
        assert not Room.objects.filter(pk=room.pk).exists()
        assert received == [
            {"property": prop, "room_type_ids": [room.room_type_id], "start": None, "end": None}
        ]

    @pytest.mark.parametrize("status", ["confirmed", "checked_in", "tentative"])
    def test_a_room_with_active_reservations_is_in_use(self, prop, status):
        room = RoomFactory(room_type__property=prop)
        StayFactory(reservation__property=prop, room_type=room.room_type, room=room, status=status)
        with pytest.raises(DomainError) as exc:
            delete_room(room)
        assert (exc.value.code, exc.value.status_code) == ("room_in_use", 409)
        assert exc.value.extra["active_stays"] == 1
        assert Room.objects.filter(pk=room.pk).exists()

    def test_a_room_with_past_reservations_suggests_deactivating(self, prop):
        room = RoomFactory(room_type__property=prop)
        StayFactory(reservation__property=prop, room_type=room.room_type, room=room, status="checked_out")
        with pytest.raises(DomainError) as exc:
            delete_room(room)
        assert exc.value.code == "room_in_use" and "desactívala" in exc.value.message


class TestBulkUpdateRooms:
    @pytest.fixture
    def rooms(self, prop):
        room_type = RoomTypeFactory(property=prop, max_adults=2, max_occupancy=3, view="city")
        return [
            RoomFactory(room_type=room_type, number=number, floor="1") for number in ("101", "102", "103")
        ]

    def test_only_the_selected_rooms_change(self, prop, rooms):
        bulk_update_rooms(prop, room_ids=[rooms[0].pk, rooms[1].pk], values={"floor": "2", "view": "sea"})
        state = {room.number: (room.floor, room.overrides) for room in Room.objects.all()}
        assert state == {"101": ("2", {"view": "sea"}), "102": ("2", {"view": "sea"}), "103": ("1", {})}

    def test_accepts_prefixed_overrides_and_custom_values(self, prop, rooms):
        CustomFieldDefinition.objects.create(
            organization=prop.organization, applies_to="room", key="minibar", field_type="boolean",
            label={"es": "Minibar"},
        )  # fmt: skip
        bulk_update_rooms(
            prop,
            room_ids=[rooms[0].pk],
            values={
                "overrides.name": {"es": "Doble con balcón"},
                "custom_values.minibar": True,
                "name": "Balcón",
            },
        )
        room = Room.objects.get(pk=rooms[0].pk)
        assert room.overrides == {"name": {"es": "Doble con balcón"}}
        assert (room.custom_values, room.name) == ({"minibar": True}, "Balcón")

    def test_reset_restores_inheritance(self, prop, rooms):
        Room.objects.filter(pk__in=[r.pk for r in rooms]).update(overrides={"view": "sea", "max_adults": 3})
        bulk_update_rooms(prop, room_ids=[rooms[0].pk, rooms[1].pk], reset=["view"])
        assert {room.number: room.overrides for room in Room.objects.all()} == {
            "101": {"max_adults": 3},
            "102": {"max_adults": 3},
            "103": {"view": "sea", "max_adults": 3},
        }

    @pytest.mark.parametrize(
        ("values", "field"),
        [
            ({"color": "#000000"}, "color"),
            ({"max_adults": "many"}, "max_adults"),
            ({"max_adults": 4}, "max_adults"),  # effective max_occupancy is 3
            ({"custom_values.unknown": 1}, "custom_values.unknown"),
            ({"housekeeping_status": "sparkling"}, "housekeeping_status"),
        ],
    )
    def test_invalid_values_change_nothing(self, prop, rooms, values, field):
        with pytest.raises(DomainError) as exc:
            bulk_update_rooms(prop, room_ids=[r.pk for r in rooms], values={"floor": "9", **values})
        assert exc.value.code == "validation_error" and field in exc.value.extra["fields"]
        assert set(Room.objects.values_list("floor", flat=True)) == {"1"}

    def test_rejects_rooms_of_another_property(self, prop, organization, rooms):
        foreign = RoomFactory(room_type__property=PropertyFactory(organization=organization))
        with pytest.raises(DomainError) as exc:
            bulk_update_rooms(prop, room_ids=[rooms[0].pk, foreign.pk], values={"floor": "2"})
        assert "ids" in exc.value.extra["fields"]
        assert Room.objects.get(pk=foreign.pk).floor == "1"

    def test_moving_rooms_to_another_category_signals_both(
        self, prop, rooms, django_capture_on_commit_callbacks
    ):
        target = RoomTypeFactory(property=prop)
        _, received = captured(
            inventory_changed,
            django_capture_on_commit_callbacks,
            lambda: bulk_update_rooms(prop, room_ids=[rooms[0].pk], values={"room_type": str(target.pk)}),
        )
        assert Room.objects.get(pk=rooms[0].pk).room_type == target
        assert len(received) == 1
        assert set(received[0]["room_type_ids"]) == {rooms[0].room_type_id, target.pk}

    def test_a_room_with_active_stays_cannot_change_category_or_be_deactivated(self, prop, rooms):
        StayFactory(
            reservation__property=prop, room_type=rooms[0].room_type, room=rooms[0], status="confirmed"
        )
        target = RoomTypeFactory(property=prop)
        for values in ({"room_type": str(target.pk)}, {"is_active": False}):
            with pytest.raises(DomainError) as exc:
                bulk_update_rooms(prop, room_ids=[rooms[0].pk, rooms[1].pk], values=values)
            assert exc.value.code == "room_in_use" and exc.value.extra["rooms"] == ["101"]
        assert Room.objects.filter(room_type=target).count() == 0

    def test_housekeeping_status_goes_through_the_service(self, prop, rooms):
        bulk_update_rooms(prop, room_ids=[rooms[0].pk], values={"housekeeping_status": "dirty"})
        assert Room.objects.get(pk=rooms[0].pk).housekeeping_status == "dirty"
        assert AuditEvent.objects.filter(action="inventory.room_status_changed").count() == 1


class TestHousekeepingStatusIsNeverOverwritten:
    """Housekeeping changes a room's status all day (check-out → dirty, cleaned → clean). Editing the room's
    settings at the same moment must not write back the status it read before."""

    def test_saving_a_room_keeps_a_status_changed_meanwhile(self, prop):
        from apps.inventory.services import save_room

        room = RoomFactory(room_type__property=prop, housekeeping_status="clean", floor="1")
        loaded_by_the_edit = Room.objects.get(pk=room.pk)
        Room.objects.filter(pk=room.pk).update(housekeeping_status="dirty")  # a check-out meanwhile

        save_room(prop, data={"floor": "2"}, room=loaded_by_the_edit)

        fresh = Room.objects.get(pk=room.pk)
        assert (fresh.floor, fresh.housekeeping_status) == ("2", "dirty")

    def test_bulk_update_keeps_a_status_changed_meanwhile(self, prop, monkeypatch):
        from apps.inventory import services

        room = RoomFactory(room_type__property=prop, housekeeping_status="clean", floor="1")
        real_plan = services._bulk_plan

        def plan_while_a_guest_checks_out(*args, **kwargs):  # the rooms are already loaded here
            Room.objects.filter(pk=room.pk).update(housekeeping_status="dirty")
            return real_plan(*args, **kwargs)

        monkeypatch.setattr(services, "_bulk_plan", plan_while_a_guest_checks_out)
        bulk_update_rooms(prop, room_ids=[room.pk], values={"floor": "2"})

        fresh = Room.objects.get(pk=room.pk)
        assert (fresh.floor, fresh.housekeeping_status) == ("2", "dirty")


class TestResetOverride:
    def test_removes_an_override_amenity_changes_or_a_custom_value(self, prop, owner):
        tub = AmenityFactory(code="bathtub")
        room = RoomFactory(
            room_type=RoomTypeFactory(property=prop, view="city", custom_values={"orientation": "city"}),
            overrides={"view": "sea", "size_m2": "30.00"},
            custom_values={"orientation": "sea"},
        )
        room.extra_amenities.set([tub])

        reset_override(room, "view", actor=owner)
        reset_override(room, "custom_values.orientation", actor=owner)
        reset_override(room, "amenities", actor=owner)

        room.refresh_from_db()
        attrs = effective_attributes(room)
        assert (room.overrides, room.custom_values, list(room.extra_amenities.all())) == (
            {"size_m2": "30.00"}, {}, []
        )  # fmt: skip
        assert (attrs["view"], attrs["custom_values"], attrs["size_m2"]) == (
            "city",
            {"orientation": "city"},
            Decimal("30.00"),
        )
        assert AuditEvent.objects.filter(action="inventory.room_override_reset").count() == 3

    def test_rejects_unknown_fields(self, prop):
        room = RoomFactory(room_type__property=prop)
        with pytest.raises(DomainError) as exc:
            reset_override(room, "color")
        assert exc.value.code == "validation_error"


@pytest.mark.django_db(transaction=True)
def test_simultaneous_bulk_creations_with_overlapping_numbers_report_duplicates(prop, monkeypatch):
    """Two staff members (or a double submit) create overlapping ranges at once: one wins, the other gets
    `duplicate_room_numbers` (400) instead of a raw IntegrityError, and no room exists twice."""
    import threading
    import time

    from django.db import connection

    from apps.inventory import services

    room_type = RoomTypeFactory(property=prop)
    real_create_rooms = services._create_rooms

    def slow_create_rooms(*args, **kwargs):
        time.sleep(0.4)  # keeps the first transaction open while the second one checks the numbers
        return real_create_rooms(*args, **kwargs)

    monkeypatch.setattr(services, "_create_rooms", slow_create_rooms)
    barrier = threading.Barrier(2)
    outcomes = []

    def worker(numbers):
        try:
            barrier.wait(timeout=10)
            outcomes.append(("created", len(bulk_create_rooms(prop, room_type=room_type, numbers=numbers))))
        except DomainError as exc:
            outcomes.append(("rejected", exc.code))
        except Exception as exc:  # noqa: BLE001 - reported by the assertion
            outcomes.append(("error", repr(exc)))
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(numbers,)) for numbers in ("101-103", "103-105")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(outcomes) == [("created", 3), ("rejected", "duplicate_room_numbers")], outcomes
    assert Room.objects.filter(property=prop, number="103").count() == 1
