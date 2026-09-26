import uuid

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Membership, Role
from apps.accounts.services import add_member, ensure_system_roles
from apps.accounts.tests.factories import UserFactory
from apps.core.models import Alert, Organization
from apps.core.tests.factories import OrganizationFactory, PropertyFactory

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.core.tests.tenancy_urls")]


def client_for(user, prop=None, header=None):
    client = APIClient()
    client.force_authenticate(user=user)
    value = header if header is not None else (str(prop.pk) if prop is not None else None)
    if value is not None:
        client.credentials(HTTP_X_PROPERTY_ID=value)
    return client


class TestAuthentication:
    def test_anonymous_requests_get_401_so_the_spa_can_redirect_to_login(self, prop):
        response = APIClient().get("/t/ping/", HTTP_X_PROPERTY_ID=str(prop.pk))
        assert response.status_code == 401
        assert response.json()["code"] == "not_authenticated"
        assert response.has_header("WWW-Authenticate")

    def test_session_users_must_send_the_csrf_token_on_writes(self, owner, prop):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(owner)
        response = client.post("/t/ping/", {}, HTTP_X_PROPERTY_ID=str(prop.pk))
        assert response.status_code == 403
        assert response.json()["code"] == "csrf_failed"

    def test_session_users_with_the_csrf_token_pass(self, owner, prop):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(owner)
        client.get("/t/ping/", HTTP_X_PROPERTY_ID=str(prop.pk))  # any request gets a session; set a token:
        from django.middleware.csrf import _get_new_csrf_string

        token = _get_new_csrf_string()
        client.cookies["csrftoken"] = token
        response = client.post("/t/ping/", {}, HTTP_X_PROPERTY_ID=str(prop.pk), HTTP_X_CSRFTOKEN=token)
        assert response.status_code == 200


class TestPropertyResolution:
    def test_member_gets_the_property_organization_and_membership(self, owner, prop):
        response = client_for(owner, prop).get("/t/ping/")
        assert response.status_code == 200
        assert response.json() == {
            "property": str(prop.pk),
            "organization": str(prop.organization_id),
            "role": "owner",
        }

    def test_missing_header_is_400_property_required(self, owner):
        response = client_for(owner).get("/t/ping/")
        assert (response.status_code, response.json()["code"]) == (400, "property_required")

    @pytest.mark.parametrize("header", ["not-a-uuid", str(uuid.uuid4())])
    def test_malformed_or_unknown_property_is_404(self, owner, header):
        response = client_for(owner, header=header).get("/t/ping/")
        assert (response.status_code, response.json()["code"]) == (404, "not_found")

    def test_property_of_another_organization_is_404(self, owner):
        foreign = PropertyFactory(organization=OrganizationFactory())
        response = client_for(owner, foreign).get("/t/ping/")
        assert response.status_code == 404

    def test_membership_restricted_to_another_property_is_404(self, make_member, prop, organization):
        other = PropertyFactory(organization=organization)
        user = make_member("owner", properties=[other])
        assert client_for(user, prop).get("/t/ping/").status_code == 404
        assert client_for(user, other).get("/t/ping/").status_code == 200

    def test_inactive_membership_is_404(self, owner, prop):
        Membership.objects.filter(user=owner).update(is_active=False)
        assert client_for(owner, prop).get("/t/ping/").status_code == 404


class TestPermissions:
    def test_missing_permission_is_403_naming_the_permission(self, make_member, prop):
        user = make_member("front_desk")
        response = client_for(user, prop).post("/t/ping/", {})
        assert response.status_code == 403
        assert response.json() == {
            "detail": "No tienes permiso para esta acción",
            "code": "permission_denied",
            "permission": "finance.refund",
        }

    def test_granted_permission_passes(self, make_member, prop):
        user = make_member("accountant")  # finance.*
        assert client_for(user, prop).post("/t/ping/", {}).status_code == 200

    def test_star_entry_applies_to_every_method(self, make_member, prop):
        housekeeper = make_member("housekeeping")
        assert client_for(housekeeper, prop).get("/t/billing/").status_code == 403


class TestSuspendedOrganizations:
    def test_suspended_organization_gets_402(self, owner, prop):
        Organization.objects.filter(pk=prop.organization_id).update(status="suspended")
        response = client_for(owner, prop).get("/t/ping/")
        assert (response.status_code, response.json()["code"]) == (402, "organization_suspended")

    def test_views_that_allow_suspended_still_answer(self, owner, prop):
        Organization.objects.filter(pk=prop.organization_id).update(status="suspended")
        assert client_for(owner, prop).get("/t/billing/").status_code == 200


class TestPropertyScopedViewSet:
    def test_list_only_shows_rows_of_the_header_property(self, owner, prop, organization):
        other = PropertyFactory(organization=organization)
        Alert.objects.create(property=prop, kind="k", title="Mía", dedupe_key="a")
        Alert.objects.create(property=other, kind="k", title="Otra", dedupe_key="a")
        response = client_for(owner, prop).get("/t/alerts/")
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1 and [row["title"] for row in body["results"]] == ["Mía"]

    def test_rows_of_another_property_are_404(self, owner, prop, organization):
        foreign = Alert.objects.create(
            property=PropertyFactory(organization=organization), kind="k", title="t", dedupe_key="a"
        )
        assert client_for(owner, prop).get(f"/t/alerts/{foreign.pk}/").status_code == 404

    def test_create_takes_the_property_from_the_header_never_from_the_body(self, owner, prop, organization):
        other = PropertyFactory(organization=organization)
        payload = {"property": str(other.pk), "kind": "k", "title": "Nueva", "dedupe_key": "n"}
        response = client_for(owner, prop).post("/t/alerts/", payload)
        assert response.status_code == 201
        assert Alert.objects.get(pk=response.json()["id"]).property == prop


class TestOrganizationScopedMixin:
    def test_lists_only_rows_of_the_request_organization(self, owner, prop, organization):
        other_org = OrganizationFactory()
        ensure_system_roles(other_org)
        response = client_for(owner, prop).get("/t/roles/")
        assert response.status_code == 200
        ids = {row["id"] for row in response.json()}
        assert ids == {
            str(pk) for pk in Role.objects.filter(organization=organization).values_list("pk", flat=True)
        }

    def test_member_of_another_organization_cannot_use_this_property(self, prop):
        stranger_org = OrganizationFactory()
        stranger = UserFactory()
        add_member(stranger_org, stranger, "owner")
        assert client_for(stranger, prop).get("/t/roles/").status_code == 404
