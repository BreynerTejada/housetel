"""Roles API (B3): system roles are read-only templates; custom roles hold explicit permission codes (or
patterns) from the catalog; nobody creates a role with permissions they lack."""

import pytest

from apps.accounts.models import Invitation, Role
from apps.accounts.services import add_member, ensure_system_roles
from apps.accounts.tests.factories import RoleFactory, UserFactory
from apps.core.models import AuditEvent
from apps.core.tests.factories import OrganizationFactory

pytestmark = pytest.mark.django_db

ROLES = "/api/v1/accounts/roles/"
CATALOG = "/api/v1/accounts/permissions/"


def system(organization, code):
    return Role.objects.get(organization=organization, code=code, is_system=True)


class TestList:
    def test_lists_system_and_custom_roles_of_the_organization(self, api, make_member, organization):
        custom = RoleFactory(
            organization=organization, name="Recepción nocturna", permissions=["bookings.view"]
        )
        make_member("front_desk")
        RoleFactory(organization=OrganizationFactory(), name="Ajeno")

        rows = api.get(ROLES).json()

        by_name = {row["name"]: row for row in rows}
        assert "Ajeno" not in by_name and len(rows) == 8  # 7 system roles + 1 custom
        assert by_name["Recepción"]["members_count"] == 1 and by_name["Recepción"]["is_system"] is True
        assert by_name["Recepción nocturna"]["id"] == str(custom.pk)
        assert (by_name["Dueño"]["assignable"], by_name["Dueño"]["editable"]) == (True, False)
        assert by_name["Recepción nocturna"]["editable"] is True

    def test_user_admins_without_roles_manage_can_read_roles_to_assign_them(
        self, api_for, organization, prop
    ):
        admin_role = RoleFactory(organization=organization, permissions=["accounts.users_manage", "guests.*"])
        user = UserFactory()
        add_member(organization, user, admin_role.code)
        client = api_for(user, prop)

        rows = client.get(ROLES).json()

        assignable = {row["code"] for row in rows if row["assignable"]}
        assert admin_role.code in assignable and "owner" not in assignable
        assert client.post(ROLES, {"name": "X", "permissions": []}).status_code == 403

    def test_front_desk_cannot_see_roles(self, api_for, make_member, prop):
        assert api_for(make_member("front_desk"), prop).get(ROLES).status_code == 403


class TestCreate:
    def test_creates_a_custom_role(self, api, organization):
        response = api.post(
            ROLES,
            {
                "name": "Recepción nocturna",
                "description": "Turno de noche",
                "permissions": ["bookings.view", "bookings.checkin", "guests.view", "bookings.view"],
            },
        )
        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["permissions"] == ["bookings.checkin", "bookings.view", "guests.view"]
        assert (body["is_system"], body["code"]) == (False, "recepcion_nocturna")
        assert Role.objects.get(pk=body["id"]).organization == organization
        assert AuditEvent.objects.filter(action="accounts.role_created").exists()

    def test_codes_are_unique_and_names_too(self, api):
        api.post(ROLES, {"name": "Auditor", "permissions": []})
        second = api.post(ROLES, {"name": "auditor", "permissions": []})
        assert second.status_code == 400 and "name" in second.json()["fields"]
        other = api.post(ROLES, {"name": "Dueño", "permissions": []})  # same name as the system owner role
        assert other.status_code == 400
        ok = api.post(ROLES, {"name": "Owner", "permissions": []})
        assert ok.json()["code"] == "owner_2"  # never the system code

    def test_unknown_permissions_are_rejected(self, api):
        response = api.post(ROLES, {"name": "Rara", "permissions": ["bookings.view", "bookings.fly"]})
        assert (response.status_code, response.json()["code"]) == (400, "invalid_permissions")
        assert response.json()["unknown"] == ["bookings.fly"]

    def test_nobody_creates_a_role_with_permissions_they_lack(self, api_for, make_member, prop):
        manager = api_for(make_member("manager"), prop)
        assert manager.post(ROLES, {"name": "Casi dueño", "permissions": ["bookings.*"]}).status_code == 201
        response = manager.post(ROLES, {"name": "Dueño 2", "permissions": ["saas.billing_manage"]})
        assert (response.status_code, response.json()["code"]) == (403, "permission_escalation")
        response = manager.post(ROLES, {"name": "Todo", "permissions": ["*"]})
        assert response.status_code == 403


class TestUpdateAndDelete:
    def test_updates_a_custom_role(self, api, organization):
        custom = RoleFactory(organization=organization, permissions=["bookings.view"])
        response = api.patch(f"{ROLES}{custom.pk}/", {"name": "Nuevo nombre", "permissions": ["guests.view"]})
        assert response.status_code == 200
        custom.refresh_from_db()
        assert (custom.name, custom.permissions) == ("Nuevo nombre", ["guests.view"])

    def test_system_roles_are_read_only(self, api, organization):
        owner_role = system(organization, "owner")
        assert api.patch(f"{ROLES}{owner_role.pk}/", {"name": "Jefe"}).json()["code"] == "system_role"
        assert api.delete(f"{ROLES}{owner_role.pk}/").json()["code"] == "system_role"

    def test_a_manager_cannot_edit_a_role_above_them(self, api_for, make_member, organization, prop):
        powerful = RoleFactory(organization=organization, permissions=["saas.billing_manage"])
        response = api_for(make_member("manager"), prop).patch(f"{ROLES}{powerful.pk}/", {"permissions": []})
        assert (response.status_code, response.json()["code"]) == (403, "permission_escalation")

    def test_delete_unused_role(self, api, organization):
        custom = RoleFactory(organization=organization)
        assert api.delete(f"{ROLES}{custom.pk}/").status_code == 204
        assert not Role.objects.filter(pk=custom.pk).exists()

    @pytest.mark.parametrize("usage", ["member", "invitation"])
    def test_role_in_use_is_kept(self, api, organization, usage):
        custom = RoleFactory(organization=organization)
        if usage == "member":
            add_member(organization, UserFactory(), custom.code)
        else:
            Invitation.objects.create(organization=organization, email="x@hotel.co", role=custom)
        response = api.delete(f"{ROLES}{custom.pk}/")
        assert (response.status_code, response.json()["code"]) == (409, "role_in_use")

    def test_roles_of_another_organization_are_not_found(self, api):
        other = OrganizationFactory()
        foreign = ensure_system_roles(other)["manager"]
        assert api.get(f"{ROLES}{foreign.pk}/").status_code == 404
        assert api.post(f"{ROLES}{foreign.pk}/duplicate/").status_code == 404


class TestDuplicate:
    def test_duplicates_a_system_role_as_an_editable_copy(self, api, organization):
        front_desk = system(organization, "front_desk")
        response = api.post(f"{ROLES}{front_desk.pk}/duplicate/")
        assert response.status_code == 201
        body = response.json()
        assert (body["name"], body["is_system"]) == ("Copia de Recepción", False)
        assert body["permissions"] == sorted(front_desk.permissions) and body["editable"] is True
        again = api.post(f"{ROLES}{front_desk.pk}/duplicate/").json()
        assert again["name"] == "Copia de Recepción (2)"

    def test_a_manager_cannot_copy_the_owner_role(self, api_for, make_member, organization, prop):
        response = api_for(make_member("manager"), prop).post(
            f"{ROLES}{system(organization, 'owner').pk}/duplicate/"
        )
        assert (response.status_code, response.json()["code"]) == (403, "permission_escalation")


def test_catalog_endpoint_is_grouped_by_module(api):
    modules = api.get(CATALOG).json()
    assert modules[0]["code"] == "accounts"
    guests = next(m for m in modules if m["code"] == "guests")
    # declaration order of apps/guests/permissions.py (view first), not alphabetical
    assert [p["code"] for p in guests["permissions"]] == [
        "guests.view",
        "guests.manage",
        "guests.merge",
        "guests.export",
    ]
    assert guests["label_en"] == "Guests"
