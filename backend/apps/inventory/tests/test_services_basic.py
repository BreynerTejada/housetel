"""Phase A inventory services (plan Step 5): inheritance, blocks and housekeeping status (with signals)."""

from datetime import date
from decimal import Decimal

import pytest

from apps.core.errors import DomainError
from apps.core.models import AuditEvent
from apps.core.signals import inventory_changed, room_status_changed
from apps.inventory.models import CustomFieldDefinition, Room, RoomBlock
from apps.inventory.services import (
    block_room,
    effective_attributes,
    release_block,
    set_housekeeping_status,
    validate_custom_values,
)
from apps.inventory.tests.factories import (
    AmenityFactory,
    BedFactory,
    DormRoomTypeFactory,
    RoomFactory,
    RoomTypeFactory,
)

pytestmark = pytest.mark.django_db

OCT = lambda day: date(2026, 10, day)  # noqa: E731


def listen(signal):
    """Collect what `signal` receivers get; returns (received, stop)."""
    received = []

    def receiver(sender, **kwargs):
        kwargs.pop("signal")
        received.append(kwargs)

    signal.connect(receiver, weak=False)
    return received, lambda: signal.disconnect(receiver)


class TestEffectiveAttributes:
    def test_inherits_the_room_type_and_flags_overrides(self, prop):
        wifi, tv, tub, safe = (AmenityFactory(code=c) for c in ("wifi", "tv", "tub", "safe"))
        room_type = RoomTypeFactory(
            property=prop,
            code="STE",
            name={"es": "Suite", "en": "Suite"},
            view="city",
            max_adults=2,
            size_m2=Decimal("42.00"),
            amenities=[wifi, tv],
            custom_values={"orientation": "city", "minibar": False},
        )
        room = RoomFactory(
            room_type=room_type,
            number="306",
            floor="3",
            name="Suite Panorámica",
            overrides={"view": "sea", "max_adults": 3, "unknown": "ignored"},
            custom_values={"minibar": True},
        )
        room.extra_amenities.set([tub, safe])
        room.removed_amenities.set([tv])

        attrs = effective_attributes(room)

        assert (attrs["view"], attrs["max_adults"], attrs["size_m2"]) == ("sea", 3, Decimal("42.00"))
        assert attrs["name"] == {"es": "Suite", "en": "Suite"}
        assert attrs["overridden_fields"] == ["max_adults", "view"]
        assert attrs["amenities"] == ["safe", "tub", "wifi"]
        assert (attrs["amenities_added"], attrs["amenities_removed"]) == (["safe", "tub"], ["tv"])
        assert attrs["custom_values"] == {"orientation": "city", "minibar": True}
        assert attrs["overridden_custom_fields"] == ["minibar"]
        assert (
            attrs["room_id"],
            attrs["room_type_id"],
            attrs["number"],
            attrs["room_name"],
            attrs["floor"],
        ) == (
            room.pk,
            room_type.pk,
            "306",
            "Suite Panorámica",
            "3",
        )
        assert attrs["kind"] == "private" and "unknown" not in attrs

    def test_room_without_overrides_is_the_room_type(self, prop):
        room = RoomFactory(room_type=RoomTypeFactory(property=prop, max_occupancy=4))
        attrs = effective_attributes(room)
        assert (attrs["max_occupancy"], attrs["overridden_fields"], attrs["amenities"]) == (4, [], [])


class TestBlocks:
    def test_block_room_creates_the_block_audits_and_signals(
        self, prop, owner, django_capture_on_commit_callbacks
    ):
        room = RoomFactory(room_type=RoomTypeFactory(property=prop))
        received, stop = listen(inventory_changed)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                block = block_room(
                    room, start=OCT(1), end=OCT(3), kind="maintenance", reason="Pintura", actor=owner
                )
        finally:
            stop()
        block.refresh_from_db()
        assert (block.room, block.bed, block.start_date, block.end_date, block.kind, block.reason) == (
            room,
            None,
            OCT(1),
            OCT(3),
            "maintenance",
            "Pintura",
        )
        assert block.created_by == owner and block.released_at is None
        assert received == [
            {"property": prop, "room_type_ids": [room.room_type_id], "start": OCT(1), "end": OCT(3)}
        ]
        assert AuditEvent.objects.filter(action="inventory.room_blocked", target_id=str(block.pk)).exists()

    def test_can_block_a_single_dorm_bed(self, prop):
        dorm = RoomFactory(room_type=DormRoomTypeFactory(property=prop))
        bed = BedFactory(room=dorm)
        assert block_room(dorm, start=OCT(1), end=OCT(2), kind="out_of_order", reason="", bed=bed).bed == bed

    def test_rejects_a_bed_of_another_room(self, prop):
        room = RoomFactory(room_type=RoomTypeFactory(property=prop))
        with pytest.raises(DomainError) as exc:
            block_room(room, start=OCT(1), end=OCT(2), kind="out_of_order", reason="", bed=BedFactory())
        assert exc.value.code == "invalid_bed"

    @pytest.mark.parametrize("end", [OCT(1), date(2026, 9, 30)])
    def test_rejects_empty_ranges(self, prop, end):
        room = RoomFactory(room_type=RoomTypeFactory(property=prop))
        with pytest.raises(DomainError) as exc:
            block_room(room, start=OCT(1), end=end, kind="maintenance", reason="")
        assert exc.value.code == "invalid_dates"
        assert not RoomBlock.objects.exists()

    def test_release_block_signals_once(self, prop, owner, django_capture_on_commit_callbacks):
        room = RoomFactory(room_type=RoomTypeFactory(property=prop))
        block = block_room(room, start=OCT(1), end=OCT(3), kind="maintenance", reason="")
        received, stop = listen(inventory_changed)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                released = release_block(block, actor=owner)
                again = release_block(block, actor=owner)
        finally:
            stop()
        assert released.released_at is not None and again.released_at == released.released_at
        assert received == [
            {"property": prop, "room_type_ids": [room.room_type_id], "start": OCT(1), "end": OCT(3)}
        ]
        assert AuditEvent.objects.filter(action="inventory.block_released").count() == 1


class TestHousekeepingStatus:
    def test_changes_status_audits_and_signals(self, prop, owner, django_capture_on_commit_callbacks):
        room = RoomFactory(room_type=RoomTypeFactory(property=prop), housekeeping_status="clean")
        received, stop = listen(room_status_changed)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                result = set_housekeeping_status(room, "dirty", actor=owner, source="automation")
        finally:
            stop()
        assert Room.objects.get(pk=room.pk).housekeeping_status == "dirty" == result.housekeeping_status
        assert received == [{"room": result, "old": "clean", "new": "dirty"}]
        event = AuditEvent.objects.get(action="inventory.room_status_changed")
        assert (event.source, event.changes) == ("automation", {"housekeeping_status": ["clean", "dirty"]})

    def test_same_status_is_a_no_op(self, prop, django_capture_on_commit_callbacks):
        room = RoomFactory(room_type=RoomTypeFactory(property=prop), housekeeping_status="clean")
        received, stop = listen(room_status_changed)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                set_housekeeping_status(room, "clean")
        finally:
            stop()
        assert received == [] and not AuditEvent.objects.exists()

    def test_rejects_unknown_statuses(self, prop):
        room = RoomFactory(room_type=RoomTypeFactory(property=prop))
        with pytest.raises(DomainError) as exc:
            set_housekeeping_status(room, "sparkling")
        assert exc.value.code == "invalid_status"


class TestValidateCustomValues:
    @pytest.fixture
    def defs(self, organization):
        def make(key, field_type, **extra):
            return CustomFieldDefinition(
                organization=organization,
                applies_to="room",
                key=key,
                field_type=field_type,
                label={"es": key},
                **extra,
            )

        return [
            make("notes", "text"),
            make("beds_extra", "number"),
            make("minibar", "boolean", required=True),
            make(
                "orientation", "select", options=[{"value": "sea"}, {"value": "city"}], default_value="city"
            ),
            make("views", "multiselect", options=[{"value": "sea"}, {"value": "garden"}]),
            make("renovated", "date"),
        ]

    def test_cleans_valid_values_and_applies_defaults(self, defs):
        cleaned = validate_custom_values(
            defs,
            {"notes": "Vista", "beds_extra": 2, "minibar": True, "views": ["sea"], "renovated": "2026-01-15"},
        )
        assert cleaned == {
            "notes": "Vista",
            "beds_extra": 2,
            "minibar": True,
            "orientation": "city",
            "views": ["sea"],
            "renovated": "2026-01-15",
        }

    @pytest.mark.parametrize(
        ("values", "key"),
        [
            ({"minibar": True, "beds_extra": "dos"}, "beds_extra"),
            ({"minibar": "yes"}, "minibar"),
            ({"minibar": True, "orientation": "moon"}, "orientation"),
            ({"minibar": True, "views": ["sea", "moon"]}, "views"),
            ({"minibar": True, "renovated": "15/01/2026"}, "renovated"),
            ({"minibar": True, "notes": 5}, "notes"),
            ({}, "minibar"),
            ({"minibar": True, "color": "red"}, "color"),
        ],
    )
    def test_reports_the_invalid_key(self, defs, values, key):
        with pytest.raises(DomainError) as exc:
            validate_custom_values(defs, values)
        assert exc.value.code == "invalid_custom_values"
        assert key in exc.value.extra["fields"]
