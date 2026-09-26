"""Auth API (spec §3): csrf → login → me → logout, session cookie + CSRF, exact `Me` shape."""

from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Membership, User
from apps.accounts.tests.factories import UserFactory
from apps.core.tests.factories import OrganizationFactory, PropertyFactory

pytestmark = pytest.mark.django_db

CSRF_URL = "/api/v1/accounts/auth/csrf/"
LOGIN_URL = "/api/v1/accounts/auth/login/"
LOGOUT_URL = "/api/v1/accounts/auth/logout/"
ME_URL = "/api/v1/accounts/me/"


def csrf_client():
    """A browser-like client: enforces CSRF and carries the csrftoken cookie from the csrf endpoint."""
    client = APIClient(enforce_csrf_checks=True)
    response = client.get(CSRF_URL)
    assert response.status_code == 200
    return client, response.cookies["csrftoken"].value


def login(client, token, email, password="pass1234"):
    return client.post(
        LOGIN_URL, {"email": email, "password": password}, format="json", HTTP_X_CSRFTOKEN=token
    )


class TestCsrf:
    def test_sets_the_csrftoken_cookie_readable_by_javascript(self):
        response = APIClient().get(CSRF_URL)
        assert response.status_code == 200
        cookie = response.cookies["csrftoken"]
        assert cookie.value and not cookie["httponly"]


class TestLogin:
    def test_valid_credentials_start_a_session_and_return_me(self, owner):
        client, token = csrf_client()
        response = login(client, token, owner.email)
        assert response.status_code == 200
        assert response.json()["email"] == owner.email
        assert "sessionid" in response.cookies
        assert client.get(ME_URL).status_code == 200

    def test_email_is_case_insensitive(self, owner):
        client, token = csrf_client()
        assert login(client, token, owner.email.upper()).status_code == 200

    @pytest.mark.parametrize(
        ("email", "password"), [("user@example.com", "wrong-pass"), ("nobody@example.com", "x")]
    )
    def test_bad_credentials_are_400_invalid_credentials(self, email, password):
        UserFactory(email="user@example.com")
        client, token = csrf_client()
        response = login(client, token, email, password)
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_credentials"
        assert "sessionid" not in response.cookies

    def test_inactive_users_cannot_log_in(self):
        user = UserFactory(is_active=False)
        client, token = csrf_client()
        assert login(client, token, user.email).json()["code"] == "invalid_credentials"

    def test_missing_fields_are_a_validation_error(self):
        client, token = csrf_client()
        response = client.post(LOGIN_URL, {"email": ""}, format="json", HTTP_X_CSRFTOKEN=token)
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == "validation_error"
        assert set(body["fields"]) == {"email", "password"}

    def test_requires_the_csrf_token(self, owner):
        client, _token = csrf_client()
        response = client.post(LOGIN_URL, {"email": owner.email, "password": "pass1234"}, format="json")
        assert response.status_code == 403
        assert response.json()["code"] == "csrf_failed"

    def test_is_throttled_after_ten_attempts_per_minute(self):
        client, token = csrf_client()
        codes = [login(client, token, "nobody@example.com", "x").status_code for _ in range(11)]
        assert codes[:10] == [400] * 10
        assert codes[10] == 429


class TestMe:
    def test_anonymous_gets_401(self):
        response = APIClient().get(ME_URL)
        assert response.status_code == 401
        assert response.json()["code"] == "not_authenticated"

    def test_has_the_spec_shape_plus_the_editable_phone(self, organization):
        # Spec §3 fields, plus `phone`: PATCH /me/ accepts it, so GET must return it (A3) or the profile
        # dialog would show it empty and erase it on the next save.
        prop = PropertyFactory(
            organization=organization,
            name="Hotel Casa Aurora",
            slug="casa-aurora",
            property_type="boutique",
            business_date=date(2026, 9, 25),
        )
        user = UserFactory(
            email="owner@casaaurora.co", full_name="Ana Aurora", language="es", phone="+573001112233"
        )
        from apps.accounts.services import add_member

        membership = add_member(organization, user, "front_desk")
        client = APIClient()
        client.force_authenticate(user)

        body = client.get(ME_URL).json()

        assert body == {
            "id": str(user.pk),
            "email": "owner@casaaurora.co",
            "full_name": "Ana Aurora",
            "language": "es",
            "phone": "+573001112233",
            "is_platform_admin": False,
            "memberships": [
                {
                    "organization": {
                        "id": str(organization.pk),
                        "name": organization.name,
                        "slug": organization.slug,
                        "status": "active",
                    },
                    "role": {"id": str(membership.role.pk), "name": "Recepción", "code": "front_desk"},
                    "permissions": membership.role.permissions,
                    "properties": [
                        {
                            "id": str(prop.pk),
                            "name": "Hotel Casa Aurora",
                            "slug": "casa-aurora",
                            "property_type": "boutique",
                            "timezone": "America/Bogota",
                            "currency": "COP",
                            "business_date": "2026-09-25",
                        }
                    ],
                }
            ],
        }

    def test_permission_patterns_are_exposed_as_stored(self, owner):
        client = APIClient()
        client.force_authenticate(owner)
        assert client.get(ME_URL).json()["memberships"][0]["permissions"] == ["*"]

    def test_all_properties_membership_lists_every_property_sorted_by_name(self, owner, organization):
        PropertyFactory(organization=organization, name="Zeta")
        PropertyFactory(organization=organization, name="Alfa")
        client = APIClient()
        client.force_authenticate(owner)
        names = [p["name"] for p in client.get(ME_URL).json()["memberships"][0]["properties"]]
        assert names == sorted(names) and {"Zeta", "Alfa"} <= set(names)

    def test_restricted_membership_lists_only_its_properties(self, make_member, organization):
        allowed = PropertyFactory(organization=organization)
        PropertyFactory(organization=organization)
        user = make_member("housekeeping", properties=[allowed])
        client = APIClient()
        client.force_authenticate(user)
        properties = client.get(ME_URL).json()["memberships"][0]["properties"]
        assert [p["id"] for p in properties] == [str(allowed.pk)]

    def test_inactive_memberships_are_hidden_and_several_orgs_are_listed(self, owner, organization):
        from apps.accounts.services import add_member

        second = OrganizationFactory(name="Zzz Hoteles")
        add_member(second, owner, "manager")
        third = OrganizationFactory(name="Aaa Inactiva")
        add_member(third, owner, "owner")
        Membership.objects.filter(user=owner, organization=third).update(is_active=False)
        client = APIClient()
        client.force_authenticate(owner)
        orgs = [m["organization"]["name"] for m in client.get(ME_URL).json()["memberships"]]
        assert orgs == sorted([organization.name, "Zzz Hoteles"])

    def test_platform_admin_without_memberships(self):
        admin = UserFactory(is_platform_admin=True)
        client = APIClient()
        client.force_authenticate(admin)
        body = client.get(ME_URL).json()
        assert (body["is_platform_admin"], body["memberships"]) == (True, [])

    def test_patch_updates_language_full_name_and_phone_only(self, owner):
        client = APIClient()
        client.force_authenticate(owner)
        response = client.patch(
            ME_URL,
            {
                "language": "en",
                "full_name": "New Name",
                "phone": "+573001112233",
                "is_platform_admin": True,
                "email": "hacker@example.com",
            },
            format="json",
        )
        assert response.status_code == 200
        body = response.json()
        assert (body["language"], body["full_name"], body["phone"]) == ("en", "New Name", "+573001112233")
        owner.refresh_from_db()
        assert (owner.language, owner.phone) == ("en", "+573001112233")
        assert owner.is_platform_admin is False and owner.email != "hacker@example.com"

    def test_patch_rejects_unknown_languages(self, owner):
        client = APIClient()
        client.force_authenticate(owner)
        response = client.patch(ME_URL, {"language": "fr"}, format="json")
        assert response.status_code == 400
        assert "language" in response.json()["fields"]


class TestLogout:
    def test_ends_the_session(self, owner):
        client, token = csrf_client()
        login(client, token, owner.email)
        token = client.cookies["csrftoken"].value  # rotated on login
        response = client.post(LOGOUT_URL, HTTP_X_CSRFTOKEN=token)
        assert response.status_code == 204
        assert client.get(ME_URL).status_code == 401

    def test_requires_the_csrf_token_for_a_logged_in_session(self, owner):
        client, token = csrf_client()
        login(client, token, owner.email)
        response = client.post(LOGOUT_URL)
        assert (response.status_code, response.json()["code"]) == (403, "csrf_failed")

    def test_is_harmless_without_a_session(self):
        assert APIClient().post(LOGOUT_URL).status_code == 204


def test_user_model_is_the_custom_one():
    from django.contrib.auth import get_user_model

    assert get_user_model() is User
