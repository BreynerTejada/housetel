"""`GET /api/v1/core/context/`: the property context a staff request runs in (A3).

The first real property-scoped endpoint: it goes through `PropertyScopedAPIView` + `PropertyAccess` with
the `X-Property-Id` header, so it exercises the tenancy rules end to end (header → property → membership →
role) and gives the SPA a cheap way to confirm the active property and its permissions.
"""

import uuid
from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.core.tests.factories import OrganizationFactory, PropertyFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/core/context/"


def test_returns_the_active_property_organization_role_and_permissions(make_member, organization):
    prop = PropertyFactory(
        organization=organization,
        name="Hotel Casa Aurora",
        slug="casa-aurora",
        property_type="boutique",
        business_date=date(2026, 9, 25),
    )
    user = make_member("front_desk")
    membership = user.memberships.get()
    client = APIClient()
    client.force_authenticate(user)

    response = client.get(URL, HTTP_X_PROPERTY_ID=str(prop.pk))

    assert response.status_code == 200
    assert response.json() == {
        "property": {
            "id": str(prop.pk),
            "name": "Hotel Casa Aurora",
            "slug": "casa-aurora",
            "property_type": "boutique",
            "timezone": "America/Bogota",
            "currency": "COP",
            "business_date": "2026-09-25",
        },
        "organization": {
            "id": str(organization.pk),
            "name": organization.name,
            "slug": organization.slug,
            "status": "active",
        },
        "role": {"id": str(membership.role.pk), "name": "Recepción", "code": "front_desk"},
        "permissions": membership.role.permissions,
    }


def test_the_property_header_is_required(api_for, owner):
    client = api_for(owner, PropertyFactory())
    client.credentials()  # drop the header
    response = client.get(URL)
    assert (response.status_code, response.json()["code"]) == (400, "property_required")


def test_anonymous_requests_get_401(prop):
    response = APIClient().get(URL, HTTP_X_PROPERTY_ID=str(prop.pk))
    assert (response.status_code, response.json()["code"]) == (401, "not_authenticated")


@pytest.mark.parametrize("header", ["not-a-uuid", str(uuid.uuid4())])
def test_unknown_properties_are_404(owner, header):
    client = APIClient()
    client.force_authenticate(owner)
    response = client.get(URL, HTTP_X_PROPERTY_ID=header)
    assert (response.status_code, response.json()["code"]) == (404, "not_found")


def test_a_property_of_another_organization_is_404(api_for, owner):
    foreign = PropertyFactory(organization=OrganizationFactory())
    response = api_for(owner, foreign).get(URL)
    assert (response.status_code, response.json()["code"]) == (404, "not_found")


def test_a_membership_restricted_to_another_property_is_404(make_member, organization, prop, api_for):
    other = PropertyFactory(organization=organization)
    user = make_member("housekeeping", properties=[other])
    assert api_for(user, prop).get(URL).status_code == 404
    assert api_for(user, other).get(URL).json()["property"]["id"] == str(other.pk)


def test_suspended_organizations_get_402(api, organization):
    organization.status = "suspended"
    organization.save(update_fields=["status"])
    response = api.get(URL)
    assert (response.status_code, response.json()["code"]) == (402, "organization_suspended")


def test_is_read_only(api):
    response = api.post(URL, {}, format="json")
    assert (response.status_code, response.json()["code"]) == (405, "method_not_allowed")


def test_is_documented_with_the_property_header():
    from drf_spectacular.generators import SchemaGenerator

    operation = SchemaGenerator().get_schema(request=None, public=True)["paths"][URL]["get"]
    headers = [p["name"] for p in operation.get("parameters", []) if p["in"] == "header"]
    assert "X-Property-Id" in headers
    assert "200" in operation["responses"]
