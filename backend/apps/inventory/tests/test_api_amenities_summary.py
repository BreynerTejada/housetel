"""`amenities/` (global catalog + the organization's own) and `summary/` (checklist / onboarding)."""

import pytest

from apps.core.tests.factories import OrganizationFactory
from apps.inventory.models import Amenity
from apps.inventory.tests.conftest import BASE
from apps.inventory.tests.factories import (
    AmenityFactory,
    BedFactory,
    DormRoomTypeFactory,
    RoomFactory,
    RoomTypeFactory,
)

pytestmark = pytest.mark.django_db
AMENITIES = f"{BASE}/amenities/"
SUMMARY = f"{BASE}/summary/"


class TestAmenities:
    def test_lists_the_global_catalog_and_the_organization_amenities(self, api, organization):
        AmenityFactory(code="wifi", icon="wifi", category="room")
        AmenityFactory(code="hammock", organization=organization)
        AmenityFactory(code="foreign", organization=OrganizationFactory())
        rows = {row["code"]: row for row in api.get(AMENITIES).json()}
        assert set(rows) == {"wifi", "hammock"}
        assert (rows["wifi"]["is_global"], rows["hammock"]["is_global"]) == (True, False)
        assert set(rows["wifi"]) >= {"id", "code", "name", "icon", "category"}

    def test_creates_an_organization_amenity(self, api, organization):
        response = api.post(
            AMENITIES,
            {
                "code": "Rooftop Bar",
                "name": {"es": "Bar en la terraza"},
                "icon": "wine",
                "category": "property",
            },
        )
        assert response.status_code == 201, response.json()
        amenity = Amenity.objects.get(pk=response.json()["id"])
        assert (amenity.organization, amenity.code, amenity.icon) == (organization, "rooftop-bar", "wine")

    def test_codes_of_the_global_catalog_are_taken(self, api):
        AmenityFactory(code="wifi")
        response = api.post(AMENITIES, {"code": "wifi", "name": "Wifi"})
        assert response.status_code == 400 and "code" in response.json()["fields"]

    def test_global_amenities_are_read_only(self, api):
        wifi = AmenityFactory(code="wifi")
        assert api.patch(f"{AMENITIES}{wifi.pk}/", {"icon": "tv"}).status_code == 403
        assert api.delete(f"{AMENITIES}{wifi.pk}/").status_code == 403

    def test_own_amenities_can_be_edited_and_deleted(self, api, organization):
        own = AmenityFactory(code="hammock", organization=organization)
        assert api.patch(f"{AMENITIES}{own.pk}/", {"icon": "tree-palm"}).status_code == 200
        assert api.delete(f"{AMENITIES}{own.pk}/").status_code == 204

    def test_own_amenity_changes_are_audited(self, api, owner, organization):
        from apps.core.models import AuditEvent

        amenity_id = api.post(AMENITIES, {"code": "hammock", "name": "Hamaca"}).json()["id"]
        api.patch(f"{AMENITIES}{amenity_id}/", {"icon": "tree-palm"})
        api.delete(f"{AMENITIES}{amenity_id}/")

        events = AuditEvent.objects.filter(target_id=amenity_id).order_by("created_at")
        assert [event.action for event in events] == [
            "inventory.amenity_created",
            "inventory.amenity_updated",
            "inventory.amenity_deleted",
        ]
        assert all(event.actor == owner and event.organization == organization for event in events)
        assert events[1].changes == {"icon": ["sparkles", "tree-palm"]}

    def test_the_property_profiles_follow_a_deleted_or_recoded_amenity(self, api, prop, organization):
        from apps.core.tests.factories import PropertyFactory

        AmenityFactory(code="pool", category="property")
        sister = PropertyFactory(organization=organization, settings={"amenities": ["hammock", "pool"]})
        hammock = AmenityFactory(code="hammock", organization=organization, category="property")
        rooftop = AmenityFactory(code="rooftop", organization=organization, category="property")
        assert (
            api.patch(f"{BASE}/property/", {"amenities": ["pool", "hammock", "rooftop"]}).status_code == 200
        )

        assert api.patch(f"{AMENITIES}{rooftop.pk}/", {"code": "terrace-bar"}).status_code == 200
        assert api.delete(f"{AMENITIES}{hammock.pk}/").status_code == 204

        assert api.get(f"{BASE}/property/").json()["amenities"] == ["pool", "terrace-bar"]
        sister.refresh_from_db()
        assert sister.settings["amenities"] == ["pool"]
        # the profile still saves (no unknown code left behind)
        response = api.patch(f"{BASE}/property/", {"amenities": ["pool", "terrace-bar"], "name": "Aurora"})
        assert response.status_code == 200, response.json()

    def test_housekeeping_cannot_create(self, hk_api):
        assert hk_api.get(AMENITIES).status_code == 200
        assert hk_api.post(AMENITIES, {"code": "x", "name": "X"}).status_code == 403


class TestSummary:
    def test_counts_units_statuses_and_warns_about_dorms_without_beds(self, api, prop):
        double = RoomTypeFactory(property=prop, code="DBL")
        RoomFactory(room_type=double, housekeeping_status="clean")
        RoomFactory(room_type=double, housekeeping_status="dirty")
        RoomFactory(room_type=double, is_active=False)
        dorm = DormRoomTypeFactory(property=prop, code="D6")
        full = RoomFactory(room_type=dorm, number="D1")
        BedFactory(room=full)
        BedFactory(room=full)
        empty = RoomFactory(room_type=dorm, number="D2")
        RoomTypeFactory(property=prop, code="EMPTY")

        body = api.get(SUMMARY).json()

        types = {row["code"]: row for row in body["room_types"]}
        assert (types["DBL"]["units"], types["DBL"]["rooms"], types["DBL"]["active_rooms"]) == (2, 3, 2)
        assert (types["D6"]["units"], types["D6"]["beds"]) == (2, 2)
        assert body["totals"] == {
            "room_types": 3, "active_room_types": 3, "rooms": 5, "active_rooms": 4, "beds": 2, "units": 4,
        }  # fmt: skip
        assert body["housekeeping"] == {"clean": 3, "dirty": 1, "inspected": 0, "out_of_service": 0}
        warnings = {(w["code"], w.get("room_id")) for w in body["warnings"]}
        assert ("dorm_room_without_beds", str(empty.pk)) in warnings
        assert ("room_type_without_rooms", None) in warnings

    def test_lists_missing_profile_fields(self, api, prop):
        prop.rnt_number = ""
        prop.save()
        assert "rnt_number" in api.get(SUMMARY).json()["profile_missing"]
