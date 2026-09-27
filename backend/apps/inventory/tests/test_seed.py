"""Inventory demo seed (plan B1): amenity catalog, categories/rooms of spec §10, dorm beds, custom fields,
overrides and photos (picsum when reachable, generated warm gradients otherwise)."""

import io
import random
from collections import Counter

import pytest
from django.utils import timezone
from PIL import Image

from apps.core.seed import SeedContext, seed_base
from apps.inventory import seed as inventory_seed
from apps.inventory.models import Amenity, Bed, CustomFieldDefinition, Photo, Room, RoomType
from apps.inventory.serializers import clean_overrides, room_occupancy_errors
from apps.inventory.services import effective_attributes, inventory_summary

pytestmark = pytest.mark.django_db


@pytest.fixture
def offline(monkeypatch):
    """No network in tests: every download fails, so photos are generated with Pillow."""
    calls = []

    def fail(urls):
        calls.extend(urls)
        return {}

    monkeypatch.setattr(inventory_seed, "download_photos", fail)
    return calls


@pytest.fixture
def ctx(offline):
    context = SeedContext(today=timezone.localdate(), rng=random.Random(20260925))
    seed_base(context)
    return context


def units(prop):
    return {row["code"]: row["units"] for row in inventory_summary(prop)["room_types"]}


def test_global_amenity_catalog(ctx):
    inventory_seed.seed(ctx)
    catalog = Amenity.objects.filter(organization__isnull=True)
    assert catalog.count() >= 30
    for amenity in catalog:
        assert amenity.name.get("es") and amenity.name.get("en") and amenity.icon, amenity.code
    assert set(catalog.values_list("category", flat=True)) == {
        "room",
        "bathroom",
        "property",
        "accessibility",
        "view",
    }


def test_casa_aurora_has_the_24_rooms_of_the_spec(ctx):
    inventory_seed.seed(ctx)
    aurora = ctx.properties["aurora"]
    assert units(aurora) == {"DBL": 10, "SUP": 8, "STE": 6}
    rooms = Room.objects.filter(property=aurora)
    numbers = {
        code: sorted(rooms.filter(room_type__code=code).values_list("number", flat=True))
        for code in ("DBL", "SUP", "STE")
    }
    assert numbers["DBL"] == [str(n) for n in range(101, 111)]
    assert numbers["SUP"] == [str(n) for n in range(201, 209)]
    assert numbers["STE"] == [str(n) for n in range(301, 307)]
    standard = RoomType.objects.get(property=aurora, code="DBL")
    assert (standard.beds, standard.size_m2) == ([{"type": "queen", "count": 1}], 22)
    suite = RoomType.objects.get(property=aurora, code="STE")
    assert "bathtub" in suite.amenities.values_list("code", flat=True)
    assert Room.objects.get(property=aurora, number="301").floor == "3"


def test_andino_medellin_and_the_bogota_hostel(ctx):
    inventory_seed.seed(ctx)
    assert sum(units(ctx.properties["andino_mde"]).values()) == 40
    assert list(units(ctx.properties["andino_mde"]).values()) == [20, 14, 6]
    hostel = ctx.properties["andino_bog"]
    dorm_rooms = Counter(
        Room.objects.filter(property=hostel, room_type__kind="dorm").values_list("room_type__code", flat=True)
    )
    assert sorted(dorm_rooms.values()) == [1, 2, 2]
    beds_per_room = {
        room.number: room.beds.filter(is_active=True).count()
        for room in Room.objects.filter(property=hostel, room_type__kind="dorm")
    }
    assert sorted(beds_per_room.values()) == [6, 6, 6, 8, 8]
    assert Room.objects.filter(property=hostel, room_type__kind="private").count() == 8
    assert inventory_summary(hostel)["warnings"] == []


def test_example_custom_fields_and_overrides(ctx):
    inventory_seed.seed(ctx)
    aurora = ctx.properties["aurora"]
    minibar = CustomFieldDefinition.objects.get(organization=aurora.organization, key="minibar")
    orientation = CustomFieldDefinition.objects.get(organization=aurora.organization, key="orientation")
    assert (minibar.applies_to, minibar.field_type) == ("room", "boolean")
    assert (orientation.applies_to, orientation.field_type) == ("room_type", "select")
    assert [option["value"] for option in orientation.options] == ["sea", "city", "garden"]

    panoramic = effective_attributes(Room.objects.get(property=aurora, number="306"))
    assert (
        "view" in panoramic["overridden_fields"]
        and panoramic["view"] != RoomType.objects.get(property=aurora, code="STE").view
    )
    assert (
        panoramic["custom_values"]["orientation"] == "sea" and panoramic["custom_values"]["minibar"] is True
    )

    # every seeded override is valid for the API
    for room in Room.objects.exclude(overrides={}):
        context = {"property": room.property}
        assert clean_overrides(room.overrides, context=context) is not None
        assert room_occupancy_errors(room.room_type, room.overrides) == {}


def test_generates_photos_for_every_category_and_property_when_offline(ctx, offline):
    inventory_seed.seed(ctx)
    for room_type in RoomType.objects.all():
        assert room_type.photos.count() == inventory_seed.PHOTOS_PER_ROOM_TYPE, room_type.code
    for prop in ctx.properties.values():
        assert (
            Photo.objects.filter(property=prop, room_type__isnull=True).count()
            == inventory_seed.PHOTOS_PER_PROPERTY
        )
    photo = Photo.objects.filter(room_type__isnull=False).first()
    with photo.image.open("rb") as handle:
        image = Image.open(io.BytesIO(handle.read()))
        assert image.size == (1200, 800)
    for name in Photo.objects.values_list("image", flat=True):
        assert name.startswith("photos/seed/") and name.count("photos/") == 1, name
    assert photo.caption.get("es") and photo.caption.get("en")
    assert offline and all(url.startswith("https://picsum.photos/seed/") for url in offline)


def test_uses_downloaded_photos_when_available(ctx, monkeypatch):
    buffer = io.BytesIO()
    Image.new("RGB", (1200, 800), (10, 20, 30)).save(buffer, format="JPEG")
    monkeypatch.setattr(
        inventory_seed, "download_photos", lambda urls: dict.fromkeys(urls, buffer.getvalue())
    )
    inventory_seed.seed(ctx)
    photo = Photo.objects.filter(room_type__isnull=False).first()
    with photo.image.open("rb") as handle:
        assert Image.open(io.BytesIO(handle.read())).getpixel((0, 0))[:3] == (10, 20, 30)


def test_is_idempotent_and_keeps_user_changes(ctx):
    inventory_seed.seed(ctx)
    aurora = ctx.properties["aurora"]
    Room.objects.filter(property=aurora, number="101").update(floor="PB")
    models = (Amenity, RoomType, Room, Bed, Photo, CustomFieldDefinition)
    counts = [model.objects.count() for model in models]
    inventory_seed.seed(ctx)
    assert counts == [model.objects.count() for model in models]
    assert Room.objects.get(property=aurora, number="101").floor == "PB"


def test_fills_the_property_profile_extras_without_overwriting(ctx):
    aurora = ctx.properties["aurora"]
    aurora.settings = {"languages": ["es"]}
    aurora.save()
    inventory_seed.seed(ctx)
    aurora.refresh_from_db()
    assert aurora.settings["languages"] == ["es"]  # kept
    assert "pool" in aurora.settings["amenities"] and "pets_allowed" in aurora.settings["policies"]
