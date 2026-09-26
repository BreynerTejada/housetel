from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.core.tests.factories import PropertyFactory
from apps.inventory.models import Amenity, CustomFieldDefinition, RoomBlock
from apps.inventory.tests.factories import (
    AmenityFactory,
    BedFactory,
    DormRoomTypeFactory,
    RoomFactory,
    RoomTypeFactory,
)

pytestmark = pytest.mark.django_db


def test_room_numbers_are_unique_per_property(prop, organization):
    RoomFactory(room_type__property=prop, number="101")
    RoomFactory(room_type__property=PropertyFactory(organization=organization), number="101")
    with pytest.raises(IntegrityError), transaction.atomic():
        RoomFactory(room_type__property=prop, number="101")


def test_room_type_codes_are_unique_per_property(prop):
    RoomTypeFactory(property=prop, code="DBL")
    RoomTypeFactory(code="DBL")
    with pytest.raises(IntegrityError), transaction.atomic():
        RoomTypeFactory(property=prop, code="DBL")


class TestRoomOverrides:
    def test_only_overridable_fields_are_accepted(self, prop):
        room = RoomFactory(room_type__property=prop, overrides={"view": "sea", "color": "#000"})
        with pytest.raises(ValidationError) as exc:
            room.clean()
        assert "overrides" in exc.value.message_dict
        assert "color" in str(exc.value.message_dict["overrides"])

    def test_valid_overrides_pass(self, prop):
        room = RoomFactory(room_type__property=prop, overrides={"view": "sea", "max_adults": 3})
        room.clean()

    def test_overrides_must_be_a_dict(self, prop):
        room = RoomFactory(room_type__property=prop, overrides=["view"])
        with pytest.raises(ValidationError):
            room.clean()

    def test_room_must_belong_to_the_room_type_property(self, prop, organization):
        room = RoomFactory(room_type__property=prop)
        room.property = PropertyFactory(organization=organization)
        with pytest.raises(ValidationError) as exc:
            room.clean()
        assert "room_type" in exc.value.message_dict


def test_bed_labels_are_unique_per_room(prop):
    dorm = RoomFactory(room_type=DormRoomTypeFactory(property=prop))
    BedFactory(room=dorm, label="A")
    BedFactory(label="A")
    with pytest.raises(IntegrityError), transaction.atomic():
        BedFactory(room=dorm, label="A")


def test_block_end_date_is_exclusive_and_after_start(prop):
    room = RoomFactory(room_type__property=prop)
    RoomBlock.objects.create(
        room=room, start_date=date(2026, 10, 1), end_date=date(2026, 10, 2), kind="maintenance"
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        RoomBlock.objects.create(
            room=room, start_date=date(2026, 10, 2), end_date=date(2026, 10, 2), kind="maintenance"
        )


class TestAmenities:
    def test_global_catalog_codes_are_unique(self):
        AmenityFactory(code="wifi")
        with pytest.raises(IntegrityError), transaction.atomic():
            AmenityFactory(code="wifi")

    def test_an_organization_can_define_its_own_code(self, organization):
        AmenityFactory(code="wifi")
        AmenityFactory(code="wifi", organization=organization)
        assert Amenity.objects.filter(code="wifi").count() == 2


def test_custom_field_keys_are_unique_per_scope(organization, prop):
    values = {
        "organization": organization,
        "applies_to": "room",
        "key": "minibar",
        "field_type": "boolean",
        "label": {"es": "Minibar", "en": "Minibar"},
    }
    CustomFieldDefinition.objects.create(**values)
    CustomFieldDefinition.objects.create(**{**values, "property": prop})
    CustomFieldDefinition.objects.create(**{**values, "applies_to": "room_type"})
    with pytest.raises(IntegrityError), transaction.atomic():
        CustomFieldDefinition.objects.create(**values)
