"""`/api/v1/inventory/property/`: profile of the active property (B1 may edit core.Property, per the plan)."""

from datetime import time

import pytest
from django.core.files.storage import default_storage

from apps.core.models import AuditEvent, Property
from apps.inventory.tests.conftest import BASE
from apps.inventory.tests.factories import AmenityFactory

pytestmark = pytest.mark.django_db
URL = f"{BASE}/property/"


def test_get_returns_the_profile(api, prop):
    body = api.get(URL).json()
    assert (body["id"], body["name"], body["slug"], body["check_in_time"], body["check_out_time"]) == (
        str(prop.pk), prop.name, prop.slug, "15:00", "12:00",
    )  # fmt: skip
    assert body["languages"] == ["es"]  # default: the default language
    assert body["policies"] == {
        "pets_allowed": False,
        "smoking_allowed": False,
        "children_allowed": True,
        "events_allowed": False,
        "min_checkin_age": 18,
    }
    assert set(body) >= {
        "description", "address", "city", "department", "latitude", "longitude", "phone", "email", "website",
        "rnt_number", "nit", "legal_name", "star_rating", "default_language", "house_rules", "branding",
        "amenities", "business_date", "timezone", "currency", "property_type",
    }  # fmt: skip


def test_patch_updates_the_editable_fields(api, prop, owner):
    AmenityFactory(code="pool", category="property")
    response = api.patch(
        URL,
        {
            "name": "Hotel Aurora",
            "legal_name": "Aurora S.A.S.",
            "nit": "901.234.567-1",
            "rnt_number": "RNT 98765",
            "check_in_time": "14:30",
            "check_out_time": "11:00",
            "default_language": "en",
            "languages": ["es", "en", "fr"],
            "house_rules": {"es": "Sin fiestas", "en": "No parties"},
            "star_rating": 5,
            "latitude": "10.4236",
            "longitude": "-75.5518",
            "branding": {"primary_color": "#123456"},
            "policies": {"pets_allowed": True, "min_checkin_age": 21},
            "amenities": ["pool"],
        },
    )
    assert response.status_code == 200, response.json()
    prop.refresh_from_db()
    assert (prop.name, prop.legal_name, prop.nit, prop.check_in_time, prop.default_language) == (
        "Hotel Aurora", "Aurora S.A.S.", "901234567-1", time(14, 30), "en",
    )  # fmt: skip
    assert prop.house_rules == {"es": "Sin fiestas", "en": "No parties"} and prop.star_rating == 5
    assert prop.branding["primary_color"] == "#123456"
    body = response.json()
    assert body["policies"]["pets_allowed"] is True and body["policies"]["min_checkin_age"] == 21
    assert body["policies"]["children_allowed"] is True  # untouched keys keep their value
    assert (body["languages"], body["amenities"]) == (["es", "en", "fr"], ["pool"])
    event = AuditEvent.objects.get(action="inventory.property_updated")
    assert event.actor == owner and "name" in event.changes


def test_read_only_fields_are_ignored(api, prop):
    before = (prop.slug, prop.business_date, prop.marketplace_listed, prop.commission_rate)
    api.patch(
        URL,
        {"slug": "hack", "business_date": "2030-01-01", "marketplace_listed": True, "commission_rate": "0"},
    )
    prop.refresh_from_db()
    assert (prop.slug, prop.business_date, prop.marketplace_listed, prop.commission_rate) == before


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"star_rating": 6}, "star_rating"),
        ({"email": "no-es-email"}, "email"),
        ({"check_in_time": "25:00"}, "check_in_time"),
        ({"default_language": "fr"}, "default_language"),
        ({"branding": {"primary_color": "red"}}, "branding"),
        ({"latitude": "123"}, "latitude"),
        ({"name": ""}, "name"),
        ({"nit": "abc"}, "nit"),
        ({"languages": ["español"]}, "languages"),
        ({"policies": {"pets": True}}, "policies"),
        ({"amenities": ["moon"]}, "amenities"),
        ({"website": "not a url"}, "website"),
    ],
)
def test_validation(api, payload, field):
    response = api.patch(URL, payload)
    assert response.status_code == 400 and field in response.json()["fields"], response.json()


def test_logo_upload_and_removal(api, prop, make_image):
    response = api.post(f"{URL}logo/", {"image": make_image("logo.png")}, format="multipart")
    assert response.status_code == 200, response.json()
    logo = response.json()["branding"]["logo"]
    assert logo.startswith("/media/branding/")
    prop.refresh_from_db()
    name = logo.removeprefix("/media/")
    assert prop.branding["logo"] == logo and default_storage.exists(name)

    response = api.delete(f"{URL}logo/")
    assert response.status_code == 200 and response.json()["branding"].get("logo", "") == ""
    assert not default_storage.exists(name)


def test_front_desk_can_read_but_not_edit(front_api):
    assert front_api.get(URL).status_code == 200
    assert front_api.patch(URL, {"name": "X"}).status_code == 403


def test_the_profile_is_always_the_header_property(api, prop, organization):
    from apps.core.tests.factories import PropertyFactory

    other = PropertyFactory(organization=organization, name="Otra")
    api.patch(URL, {"name": "Cambiado", "id": str(other.pk)})
    assert Property.objects.get(pk=other.pk).name == "Otra"
