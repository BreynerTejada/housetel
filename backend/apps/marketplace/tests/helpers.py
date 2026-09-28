"""Builders shared by the marketplace tests (plain functions; fixtures live in conftest.py).

Time is frozen by the conftest at 2026-10-01 09:00 in Bogotá (a Thursday): "today" for online bookings.
"""

import io
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

TODAY = date(2026, 10, 1)


def day(offset: int) -> date:
    """TODAY + offset days (2026-10-01 is a Thursday)."""
    return TODAY + timedelta(days=offset)


def image_file(name="photo.jpg", color=(180, 88, 59), size=(48, 32), fmt="JPEG") -> SimpleUploadedFile:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    content_type = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[fmt]
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)


def add_photo(prop, *, room_type=None, sort_order=0, caption=None):
    from apps.inventory.models import Photo

    photo = Photo(property=prop, room_type=room_type, sort_order=sort_order, caption=caption or {})
    photo.image.save(f"{prop.slug}-{sort_order}.jpg", image_file(), save=False)
    photo.save()
    return photo


def global_amenity(code, category, icon, name):
    from apps.inventory.models import Amenity

    amenity, _ = Amenity.objects.get_or_create(
        organization=None, code=code, defaults={"category": category, "icon": icon, "name": name}
    )
    return amenity


def build_hotel(prop, *, city="Cartagena", listed=True, stars=4, property_type="boutique") -> SimpleNamespace:
    """A small sellable hotel in `prop`:

    - DBL (private, 2 adults + 1 child, max 3): rooms 101 and 102 — 320.000/night.
    - STE (private): room 301 — 650.000/night.
    - Plans: FLEX (base, public), NR (−12 %, public) and CORP (base, **not public**: direct only).
    - IVA 19 % on lodging, not included, exempt for foreign non-residents; IVA 19 % on extras.
    - Extras: breakfast 35.000 per person-night (sellable online) and a hidden minibar (not online).
    """
    from apps.inventory.tests.factories import RoomFactory, RoomTypeFactory
    from apps.rates.tests.factories import (
        CancellationPolicyFactory,
        DerivedRatePlanFactory,
        ExtraFactory,
        RatePlanFactory,
        RoomTypeRateDefaultsFactory,
        TaxFactory,
    )

    prop.city = city
    prop.department = {"Cartagena": "Bolívar", "Medellín": "Antioquia", "Bogotá": "Cundinamarca"}.get(
        city, ""
    )
    prop.marketplace_listed = listed
    prop.star_rating = stars
    prop.property_type = property_type
    prop.business_date = TODAY
    prop.settings = {**(prop.settings or {}), "amenities": ["pool", "wifi"]}
    prop.save()
    pool = global_amenity("pool", "property", "waves-ladder", {"es": "Piscina", "en": "Pool"})
    wifi = global_amenity("wifi", "room", "wifi", {"es": "Wifi", "en": "Wi-Fi"})
    ac = global_amenity("air_conditioning", "room", "air-vent", {"es": "Aire acondicionado", "en": "A/C"})
    dbl = RoomTypeFactory(property=prop, code="DBL", sort_order=1, amenities=[wifi, ac])
    ste = RoomTypeFactory(
        property=prop, code="STE", sort_order=2, max_adults=3, max_children=2, max_occupancy=4, amenities=[ac]
    )
    rooms = {
        "101": RoomFactory(room_type=dbl, number="101"),
        "102": RoomFactory(room_type=dbl, number="102"),
        "301": RoomFactory(room_type=ste, number="301", floor="3"),
    }
    flexible = CancellationPolicyFactory(property=prop)
    strict = CancellationPolicyFactory(
        property=prop, name={"es": "No reembolsable", "en": "Non-refundable"}, non_refundable=True
    )
    flex = RatePlanFactory(
        property=prop, code="FLEX", room_types=[dbl, ste], cancellation_policy=flexible, sort_order=1
    )
    nr = DerivedRatePlanFactory(
        property=prop, code="NR", parent=flex, room_types=[dbl, ste], cancellation_policy=strict, sort_order=2
    )
    corp = RatePlanFactory(property=prop, code="CORP", room_types=[dbl], is_public=False, sort_order=3)
    for room_type, price in ((dbl, "320000"), (ste, "650000")):
        RoomTypeRateDefaultsFactory(room_type=room_type, rate_plan=flex, price=Decimal(price))
    RoomTypeRateDefaultsFactory(room_type=dbl, rate_plan=corp, price=Decimal("250000"))
    iva = TaxFactory(property=prop, code="IVA", applies_to="room")
    iva_extras = TaxFactory(
        property=prop, code="IVA-EXT", applies_to="extras", exempt_foreign_non_residents=False
    )
    breakfast = ExtraFactory(
        property=prop, code="BRK", price=Decimal("35000"), charge_type="per_person_night", tax=iva_extras
    )
    minibar = ExtraFactory(property=prop, code="MINI", price=Decimal("20000"), sellable_online=False)
    return SimpleNamespace(
        prop=prop,
        dbl=dbl,
        ste=ste,
        rooms=rooms,
        flex=flex,
        nr=nr,
        corp=corp,
        iva=iva,
        iva_extras=iva_extras,
        breakfast=breakfast,
        minibar=minibar,
        amenities={"pool": pool, "wifi": wifi, "air_conditioning": ac},
    )


def new_property(organization=None, **kwargs):
    """Another property (own organization unless given) with its own active org."""
    from apps.core.tests.factories import OrganizationFactory, PropertyFactory

    org = organization or OrganizationFactory(status="active")
    return PropertyFactory(organization=org, **kwargs)


def guest_payload(**overrides) -> dict:
    values = {
        "first_name": "Laura",
        "last_name": "Gómez",
        "email": "laura@example.com",
        "phone": "+573001234567",
        "nationality": "CO",
        "country_of_residence": "CO",
        "data_processing_consent": True,
        "marketing_consent": False,
    }
    values.update(overrides)
    return values


def booking_payload(
    hotel, *, checkin=None, checkout=None, room_type=None, plan=None, quantity=1, **overrides
):
    values = {
        "property_slug": hotel.prop.slug,
        "via": "marketplace",
        "checkin": (checkin or day(8)).isoformat(),
        "checkout": (checkout or day(10)).isoformat(),
        "items": [
            {
                "room_type_id": str((room_type or hotel.dbl).pk),
                "rate_plan_id": str((plan or hotel.flex).pk),
                "quantity": quantity,
                "adults": 2,
                "children": 0,
                "children_ages": [],
            }
        ],
        "guest": guest_payload(),
        "extras": [],
        "promo_code": "",
        "special_requests": "",
        "eta": None,
        "payment_option": "pay_at_hotel",
        "language": "es",
    }
    values.update(overrides)
    return values
