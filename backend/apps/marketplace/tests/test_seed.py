"""Demo seed of the marketplace: booking engine and listing of the three demo hotels (plan C4 › Seed)."""

import random
import time

import pytest

from apps.core.seed import SeedContext
from apps.core.tests.factories import PropertyFactory
from apps.marketplace.models import BookingEngineSettings, ListingContent
from apps.marketplace.seed import seed
from apps.marketplace.tests.helpers import TODAY, add_photo

pytestmark = pytest.mark.django_db


@pytest.fixture
def ctx(organization):
    from apps.inventory.tests.factories import RoomTypeFactory

    aurora = PropertyFactory(organization=organization, slug="casa-aurora", city="Cartagena")
    medellin = PropertyFactory(organization=organization, slug="andino-medellin", city="Medellín")
    hostel = PropertyFactory(organization=organization, slug="andino-hostel-bogota", property_type="hostel")
    for prop in (aurora, medellin, hostel):
        for index in range(3):
            add_photo(prop, sort_order=index)
        add_photo(prop, room_type=RoomTypeFactory(property=prop), sort_order=0)
    return SeedContext(
        today=TODAY,
        rng=random.Random(20260925),
        properties={"aurora": aurora, "andino_mde": medellin, "andino_bog": hostel},
    )


def test_every_demo_hotel_gets_its_engine_and_listing_with_its_own_brand(ctx):
    started = time.monotonic()
    seed(ctx)
    assert time.monotonic() - started < 60

    colors = set()
    for key in ("aurora", "andino_mde", "andino_bog"):
        prop = ctx.properties[key]
        prop.refresh_from_db()
        engine = BookingEngineSettings.objects.get(property=prop)
        listing = ListingContent.objects.get(property=prop)
        assert engine.enabled and engine.headline["es"] and engine.headline["en"]
        assert engine.primary_color.startswith("#") and len(engine.primary_color) == 7
        assert prop.branding["primary_color"] == engine.primary_color  # the brand follows the engine color
        assert listing.neighborhood and listing.tagline["es"] and listing.tagline["en"]
        assert 2 <= len(listing.highlights) <= 6
        assert listing.listing_photos.count() >= 2
        assert prop.marketplace_listed is True
        colors.add(engine.primary_color)
    assert len(colors) == 3  # each hotel has its own color
    assert ListingContent.objects.get(property=ctx.properties["aurora"]).neighborhood == "Centro Histórico"


def test_seeding_twice_changes_nothing_and_keeps_what_the_hotel_edited(ctx):
    seed(ctx)
    engine = BookingEngineSettings.objects.get(property=ctx.properties["aurora"])
    engine.headline = {"es": "Editado por el hotel"}
    engine.save(update_fields=["headline"])

    seed(ctx)

    assert BookingEngineSettings.objects.count() == 3
    assert ListingContent.objects.count() == 3
    assert BookingEngineSettings.objects.get(pk=engine.pk).headline == {"es": "Editado por el hotel"}


def test_missing_demo_properties_are_skipped(organization):
    lone = PropertyFactory(organization=organization, slug="casa-aurora")
    ctx = SeedContext(today=TODAY, rng=random.Random(1), properties={"aurora": lone})

    seed(ctx)

    assert BookingEngineSettings.objects.filter(property=lone).exists()
    assert ListingContent.objects.get(property=lone).listing_photos.count() == 0
