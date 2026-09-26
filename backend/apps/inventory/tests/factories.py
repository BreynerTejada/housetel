"""Inventory factories. A room's property always follows its room type:
`RoomFactory(room_type__property=prop)`."""

from datetime import timedelta

import factory
from django.utils.timezone import localdate

from apps.core.tests.factories import PropertyFactory
from apps.inventory.models import Amenity, Bed, Room, RoomBlock, RoomType


class AmenityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Amenity

    organization = None  # global catalog
    code = factory.Sequence(lambda n: f"amenity_{n}")
    name = factory.LazyAttribute(lambda o: {"es": f"Amenidad {o.code}", "en": f"Amenity {o.code}"})
    icon = "sparkles"
    category = Amenity.Category.ROOM


class RoomTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RoomType
        skip_postgeneration_save = True

    property = factory.SubFactory(PropertyFactory)
    code = factory.Sequence(lambda n: f"RT{n}")
    name = factory.LazyAttribute(lambda o: {"es": f"Categoría {o.code}", "en": f"Room type {o.code}"})
    description = factory.LazyFunction(lambda: {"es": "Habitación de prueba", "en": "Test room"})
    kind = RoomType.Kind.PRIVATE
    base_occupancy = 2
    max_adults = 2
    max_children = 1
    max_occupancy = 3
    beds = factory.LazyFunction(lambda: [{"type": "queen", "count": 1}])
    housekeeping_minutes = 30

    @factory.post_generation
    def amenities(self, create, extracted, **kwargs):
        if create and extracted:
            self.amenities.set(extracted)


class DormRoomTypeFactory(RoomTypeFactory):
    """Dorm category: units are beds, one person per bed."""

    kind = RoomType.Kind.DORM
    base_occupancy = 1
    max_adults = 1
    max_children = 0
    max_occupancy = 1
    beds = factory.LazyFunction(lambda: [{"type": "bunk", "count": 3}])


class RoomFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Room

    room_type = factory.SubFactory(RoomTypeFactory)
    property = factory.SelfAttribute("room_type.property")
    number = factory.Sequence(lambda n: f"{101 + n}")
    floor = "1"
    housekeeping_status = Room.HousekeepingStatus.CLEAN


class BedFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Bed

    room = factory.SubFactory(RoomFactory, room_type=factory.SubFactory(DormRoomTypeFactory))
    label = factory.Sequence(lambda n: f"C{n + 1}")
    bed_type = Bed.BedType.SINGLE


class RoomBlockFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RoomBlock

    room = factory.SubFactory(RoomFactory)
    start_date = factory.LazyFunction(lambda: localdate() + timedelta(days=3))
    end_date = factory.LazyAttribute(lambda o: o.start_date + timedelta(days=2))  # exclusive
    kind = RoomBlock.Kind.OUT_OF_ORDER
    reason = "Mantenimiento"
