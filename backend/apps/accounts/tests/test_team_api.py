"""Team API (B3): members of the organization, invitations by email (Mailpit locally) and their public
acceptance page; the last owner is protected and nobody grants permissions they do not have."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Invitation, Membership, Role, User
from apps.accounts.services import add_member, ensure_system_roles
from apps.accounts.tests.factories import RoleFactory, UserFactory
from apps.core.models import AuditEvent
from apps.core.tests.factories import OrganizationFactory, PropertyFactory

pytestmark = pytest.mark.django_db

USERS = "/api/v1/accounts/users/"
INVITATIONS = "/api/v1/accounts/invitations/"
PUBLIC = "/api/v1/public/accounts/invitations/"


@pytest.fixture(autouse=True)
def frontend_url(settings):
    settings.FRONTEND_URL = "http://front.test"


def role(organization, code):
    return Role.objects.get(organization=organization, code=code)


def membership_of(user, organization):
    return Membership.objects.get(user=user, organization=organization)


def invite(api, organization, email="nuevo@hotel.co", code="front_desk", **extra):
    return api.post(USERS, {"email": email, "role_id": str(role(organization, code).pk), **extra})


class TestMembers:
    def test_lists_the_organization_members_including_inactive(self, api, owner, make_member, organization):
        clerk = make_member("front_desk", full_name="Andrés Gómez")
        gone = make_member("housekeeping")
        Membership.objects.filter(user=gone).update(is_active=False)
        make_member("owner", org=OrganizationFactory())  # another organization

        rows = api.get(USERS).json()["results"]

        by_email = {row["user"]["email"]: row for row in rows}
        assert set(by_email) == {owner.email, clerk.email, gone.email}
        row = by_email[clerk.email]
        assert row["role"]["code"] == "front_desk" and row["user"]["full_name"] == "Andrés Gómez"
        assert (row["is_active"], row["all_properties"], row["editable"]) == (True, True, True)
        assert by_email[gone.email]["is_active"] is False
        assert by_email[owner.email]["is_self"] is True and by_email[owner.email]["is_owner"] is True

    def test_needs_users_manage(self, api_for, make_member, prop):
        response = api_for(make_member("front_desk"), prop).get(USERS)
        assert (response.status_code, response.json()["permission"]) == (403, "accounts.users_manage")

    def test_change_role_and_properties(self, api, make_member, organization, prop):
        other = PropertyFactory(organization=organization)
        user = make_member("front_desk")
        member = membership_of(user, organization)

        response = api.patch(
            f"{USERS}{member.pk}/",
            {
                "role_id": str(role(organization, "accountant").pk),
                "all_properties": False,
                "property_ids": [str(other.pk)],
            },
        )

        assert response.status_code == 200, response.json()
        member.refresh_from_db()
        assert member.role.code == "accountant" and not member.all_properties
        assert list(member.properties.all()) == [other]
        assert AuditEvent.objects.filter(action="accounts.member_updated").exists()

    def test_deactivate_and_reactivate(self, api, make_member, organization):
        member = membership_of(make_member("front_desk"), organization)
        assert api.patch(f"{USERS}{member.pk}/", {"is_active": False}).json()["is_active"] is False
        assert api.patch(f"{USERS}{member.pk}/", {"is_active": True}).json()["is_active"] is True

    def test_nobody_deactivates_themselves(self, api, owner, organization):
        response = api.patch(f"{USERS}{membership_of(owner, organization).pk}/", {"is_active": False})
        assert (response.status_code, response.json()["code"]) == (400, "cannot_deactivate_self")

    def test_properties_must_belong_to_the_organization(self, api, make_member, organization):
        member = membership_of(make_member("front_desk"), organization)
        foreign = PropertyFactory(organization=OrganizationFactory())
        response = api.patch(
            f"{USERS}{member.pk}/", {"all_properties": False, "property_ids": [str(foreign.pk)]}
        )
        assert response.status_code == 400 and "property_ids" in response.json()["fields"]

    def test_members_of_another_organization_are_not_found(self, api):
        stranger = UserFactory()
        other = OrganizationFactory()
        ensure_system_roles(other)
        member = add_member(other, stranger, "front_desk")
        assert api.patch(f"{USERS}{member.pk}/", {"is_active": False}).status_code == 404


def test_the_team_stays_manageable_while_the_organization_is_suspended(api, make_member, organization):
    # Spec §3: a suspended organization gets 402 on the staff API except `accounts` (and saas billing): the
    # owner can still cut a former employee's access or bring in someone to settle the bill.
    clerk = membership_of(make_member("front_desk"), organization)
    organization.status = "suspended"
    organization.save(update_fields=["status"])

    for path in (USERS, INVITATIONS, "/api/v1/accounts/roles/", "/api/v1/accounts/permissions/"):
        assert api.get(path).status_code == 200, path
    response = api.patch(f"{USERS}{clerk.pk}/", {"is_active": False})
    assert (response.status_code, response.json()["is_active"]) == (200, False)


class TestLastOwner:
    def test_the_last_owner_cannot_step_down(self, api_for, owner, organization, prop):
        member = membership_of(owner, organization)
        response = api_for(owner, prop).patch(
            f"{USERS}{member.pk}/", {"role_id": str(role(organization, "manager").pk)}
        )
        assert (response.status_code, response.json()["code"]) == (409, "last_owner")

    def test_a_manager_cannot_touch_the_owner(self, api_for, owner, make_member, organization, prop):
        # the owner holds permissions the manager lacks (saas.billing_manage)
        member = membership_of(owner, organization)
        response = api_for(make_member("manager"), prop).patch(f"{USERS}{member.pk}/", {"is_active": False})
        assert (response.status_code, response.json()["code"]) == (403, "permission_escalation")
        assert membership_of(owner, organization).is_active

    def test_with_two_owners_one_can_step_down(self, api_for, owner, make_member, organization, prop):
        second = make_member("owner")
        member = membership_of(owner, organization)
        response = api_for(second, prop).patch(
            f"{USERS}{member.pk}/", {"role_id": str(role(organization, "manager").pk)}
        )
        assert response.status_code == 200
        own = membership_of(second, organization)
        response = api_for(second, prop).patch(
            f"{USERS}{own.pk}/", {"role_id": str(role(organization, "manager").pk)}
        )
        assert (response.status_code, response.json()["code"]) == (409, "last_owner")


class TestEscalation:
    def test_a_manager_cannot_make_someone_owner(self, api_for, make_member, organization, prop):
        manager = make_member("manager")
        clerk = membership_of(make_member("front_desk"), organization)
        response = api_for(manager, prop).patch(
            f"{USERS}{clerk.pk}/", {"role_id": str(role(organization, "owner").pk)}
        )
        assert (response.status_code, response.json()["code"]) == (403, "permission_escalation")
        assert (
            invite(api_for(manager, prop), organization, code="owner").json()["code"]
            == "permission_escalation"
        )

    def test_a_manager_can_invite_and_assign_lower_roles(self, api_for, make_member, organization, prop):
        manager = api_for(make_member("manager"), prop)
        assert invite(manager, organization, code="front_desk").status_code == 201

    def test_a_manager_cannot_revoke_or_downgrade_an_owner_invitation(
        self, api, api_for, make_member, organization, prop
    ):
        pending = invite(api, organization, email="socio@hotel.co", code="owner").json()
        manager = api_for(make_member("manager"), prop)

        revoked = manager.delete(f"{INVITATIONS}{pending['id']}/")
        downgraded = invite(manager, organization, email="socio@hotel.co", code="front_desk")

        assert (revoked.status_code, revoked.json()["code"]) == (403, "permission_escalation")
        assert (downgraded.status_code, downgraded.json()["code"]) == (403, "permission_escalation")
        assert Invitation.objects.get(pk=pending["id"]).role.code == "owner"

    def test_a_manager_never_gets_the_link_of_an_owner_invitation(
        self, api, api_for, make_member, organization, prop
    ):
        # The link is a bearer secret: whoever opens it can create that account and join with that role.
        invite(api, organization, email="socio@hotel.co", code="owner")
        rows = api_for(make_member("manager"), prop).get(INVITATIONS).json()
        assert [(row["email"], row["invite_url"], row["editable"]) for row in rows] == [
            ("socio@hotel.co", None, False)
        ]

    def test_custom_user_admin_cannot_hand_out_what_it_lacks(self, api_for, make_member, organization, prop):
        admin_role = RoleFactory(
            organization=organization, permissions=["accounts.users_manage", "guests.view"]
        )
        user = UserFactory()
        add_member(organization, user, admin_role.code)
        response = invite(api_for(user, prop), organization, code="front_desk")
        assert (response.status_code, response.json()["code"]) == (403, "permission_escalation")


class TestHotelScope:
    """A member restricted to some hotels only hands out access to those hotels (same rule as permissions:
    nobody grants what they do not have)."""

    @pytest.fixture
    def other_hotel(self, organization):
        return PropertyFactory(organization=organization)

    @pytest.fixture
    def local_admin(self, api_for, make_member, prop):
        return api_for(make_member("manager", properties=[prop]), prop)

    def test_cannot_invite_to_every_hotel(self, local_admin, organization):
        response = invite(local_admin, organization)  # all_properties defaults to True
        assert (response.status_code, response.json()["code"]) == (403, "permission_escalation")

    def test_cannot_invite_to_a_hotel_outside_their_access(self, local_admin, organization, other_hotel):
        response = invite(local_admin, organization, all_properties=False, property_ids=[str(other_hotel.pk)])
        assert (response.status_code, response.json()["code"]) == (403, "permission_escalation")

    def test_invites_to_their_own_hotels(self, local_admin, organization, prop):
        response = invite(local_admin, organization, all_properties=False, property_ids=[str(prop.pk)])
        assert response.status_code == 201, response.json()

    def test_cannot_change_someone_with_wider_access(self, local_admin, make_member, organization):
        clerk = membership_of(make_member("front_desk"), organization)  # every hotel
        rows = {row["id"]: row for row in local_admin.get(USERS).json()["results"]}
        assert rows[str(clerk.pk)]["editable"] is False
        response = local_admin.patch(f"{USERS}{clerk.pk}/", {"is_active": False})
        assert (response.status_code, response.json()["code"]) == (403, "permission_escalation")

    def test_manages_people_of_their_hotels_without_widening_them(
        self, local_admin, make_member, organization, prop, other_hotel
    ):
        clerk = membership_of(make_member("front_desk", properties=[prop]), organization)
        rows = {row["id"]: row for row in local_admin.get(USERS).json()["results"]}
        assert rows[str(clerk.pk)]["editable"] is True
        changed = local_admin.patch(
            f"{USERS}{clerk.pk}/", {"role_id": str(role(organization, "accountant").pk)}
        )
        assert changed.status_code == 200, changed.json()
        for payload in (
            {"all_properties": True},
            {"all_properties": False, "property_ids": [str(prop.pk), str(other_hotel.pk)]},
        ):
            response = local_admin.patch(f"{USERS}{clerk.pk}/", payload)
            assert (response.status_code, response.json()["code"]) == (403, "permission_escalation")

    def test_cannot_resend_an_invitation_wider_than_their_access(self, api, local_admin, organization):
        wide = invite(api, organization).json()  # the owner invited someone to every hotel
        response = local_admin.post(f"{INVITATIONS}{wide['id']}/resend/")
        assert (response.status_code, response.json()["code"]) == (403, "permission_escalation")

    def test_cannot_revoke_an_invitation_wider_than_their_access(self, api, local_admin, organization):
        wide = invite(api, organization).json()
        response = local_admin.delete(f"{INVITATIONS}{wide['id']}/")
        assert (response.status_code, response.json()["code"]) == (403, "permission_escalation")
        assert Invitation.objects.filter(pk=wide["id"]).exists()

    def test_cannot_replace_an_invitation_wider_than_their_access(self, api, local_admin, organization, prop):
        wide = invite(api, organization, email="x@hotel.co").json()
        response = invite(
            local_admin, organization, email="x@hotel.co", all_properties=False, property_ids=[str(prop.pk)]
        )
        assert (response.status_code, response.json()["code"]) == (403, "permission_escalation")
        invitation = Invitation.objects.get(pk=wide["id"])
        assert invitation.all_properties and invitation.token in wide["invite_url"]  # untouched

    def test_invitations_say_whether_they_can_be_managed(self, api, local_admin, organization, prop):
        invite(api, organization, email="wide@hotel.co")
        invite(api, organization, email="local@hotel.co", all_properties=False, property_ids=[str(prop.pk)])
        rows = {row["email"]: row["editable"] for row in local_admin.get(INVITATIONS).json()}
        assert rows == {"wide@hotel.co": False, "local@hotel.co": True}

    def test_only_links_within_their_reach_are_shown(self, api, local_admin, organization, prop):
        invite(api, organization, email="wide@hotel.co")
        invite(api, organization, email="local@hotel.co", all_properties=False, property_ids=[str(prop.pk)])
        links = {row["email"]: row["invite_url"] for row in local_admin.get(INVITATIONS).json()}
        assert links["wide@hotel.co"] is None
        token = Invitation.objects.get(email="local@hotel.co").token
        assert links["local@hotel.co"] == f"http://front.test/invite/{token}"


class TestInvite:
    def test_invites_by_email_with_a_link_to_the_frontend(self, api, organization, prop, mailoutbox):
        response = invite(
            api, organization, email="Nuevo@Hotel.co", all_properties=False, property_ids=[str(prop.pk)]
        )

        assert response.status_code == 201, response.json()
        body = response.json()
        invitation = Invitation.objects.get(pk=body["id"])
        assert invitation.email == "nuevo@hotel.co" and invitation.role.code == "front_desk"
        assert list(invitation.properties.all()) == [prop] and not invitation.all_properties
        assert body["invite_url"] == f"http://front.test/invite/{invitation.token}"
        assert (body["status"], body["email_sent"]) == ("pending", True)
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == ["nuevo@hotel.co"] and body["invite_url"] in mailoutbox[0].body
        assert organization.name in mailoutbox[0].subject

    def test_existing_active_member_is_a_409(self, api, make_member, organization):
        clerk = make_member("front_desk")
        response = invite(api, organization, email=clerk.email.upper())
        assert (response.status_code, response.json()["code"]) == (409, "already_member")

    def test_inviting_again_refreshes_the_pending_invitation(self, api, organization, mailoutbox):
        first = invite(api, organization).json()
        second = invite(api, organization, code="accountant").json()
        assert second["id"] == first["id"] and second["invite_url"] != first["invite_url"]
        assert Invitation.objects.get(pk=first["id"]).role.code == "accountant"
        assert len(mailoutbox) == 2

    def test_role_of_another_organization_is_rejected(self, api):
        other = OrganizationFactory()
        foreign_role = ensure_system_roles(other)["front_desk"]
        response = api.post(USERS, {"email": "x@hotel.co", "role_id": str(foreign_role.pk)})
        assert response.status_code == 400 and "role_id" in response.json()["fields"]

    def test_restricted_invitation_needs_properties(self, api, organization):
        response = invite(api, organization, all_properties=False, property_ids=[])
        assert response.status_code == 400 and "property_ids" in response.json()["fields"]

    def test_a_failing_mail_server_still_creates_the_invitation(self, api, organization, settings):
        settings.EMAIL_BACKEND = "apps.accounts.tests.test_team_api.BrokenEmailBackend"
        body = invite(api, organization).json()
        assert body["email_sent"] is False and body["invite_url"]


class BrokenEmailBackend:
    def __init__(self, *args, **kwargs):
        pass

    def send_messages(self, messages):
        raise ConnectionRefusedError("SMTP down")


class TestInvitations:
    def test_lists_pending_invitations_of_the_organization(self, api, organization):
        invite(api, organization, email="a@hotel.co")
        other = OrganizationFactory()
        Invitation.objects.create(
            organization=other, email="b@x.co", role=ensure_system_roles(other)["owner"]
        )
        rows = api.get(INVITATIONS).json()
        assert [row["email"] for row in rows] == ["a@hotel.co"]

    def test_expired_invitations_are_marked(self, api, organization):
        invitation_id = invite(api, organization).json()["id"]
        Invitation.objects.filter(pk=invitation_id).update(expires_at=timezone.now() - timedelta(days=1))
        assert api.get(INVITATIONS).json()[0]["status"] == "expired"

    def test_resend_rotates_the_link_and_extends_it(self, api, organization, mailoutbox):
        first = invite(api, organization).json()
        Invitation.objects.filter(pk=first["id"]).update(expires_at=timezone.now() - timedelta(days=1))
        resent = api.post(f"{INVITATIONS}{first['id']}/resend/").json()
        assert resent["invite_url"] != first["invite_url"] and resent["status"] == "pending"
        assert len(mailoutbox) == 2

    def test_revoke(self, api, organization):
        invitation_id = invite(api, organization).json()["id"]
        assert api.delete(f"{INVITATIONS}{invitation_id}/").status_code == 204
        assert not Invitation.objects.filter(pk=invitation_id).exists()

    def test_invitations_of_another_organization_are_not_found(self, api):
        other = OrganizationFactory()
        foreign = Invitation.objects.create(
            organization=other, email="b@x.co", role=ensure_system_roles(other)["owner"]
        )
        assert api.delete(f"{INVITATIONS}{foreign.pk}/").status_code == 404
        assert api.post(f"{INVITATIONS}{foreign.pk}/resend/").status_code == 404


def csrf_client():
    client = APIClient(enforce_csrf_checks=True)
    token = client.get("/api/v1/accounts/auth/csrf/").cookies["csrftoken"].value
    return client, token


@pytest.fixture
def invitation(api, organization, prop):
    body = invite(
        api, organization, email="nueva@hotel.co", all_properties=False, property_ids=[str(prop.pk)]
    ).json()
    return Invitation.objects.get(pk=body["id"])


class TestPublicAcceptance:
    def test_shows_the_invitation_to_whoever_has_the_link(self, invitation, organization, owner):
        body = APIClient().get(f"{PUBLIC}{invitation.token}/").json()
        assert body["email"] == "nueva@hotel.co" and body["organization"]["name"] == organization.name
        assert (body["role"]["name"], body["status"], body["user_exists"]) == ("Recepción", "pending", False)
        assert body["invited_by"] == owner.full_name
        assert "token" not in body and "invite_url" not in body

    def test_unknown_link_is_404(self):
        assert APIClient().get(f"{PUBLIC}nope/").status_code == 404

    def test_new_user_accepts_logs_in_and_can_log_in_again(self, invitation, organization, prop):
        client, token = csrf_client()

        response = client.post(
            f"{PUBLIC}{invitation.token}/accept/",
            {"full_name": "Nueva Recepcionista", "password": "Clave-segura-2026"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )

        assert response.status_code == 200, response.json()
        me = response.json()
        assert me["email"] == "nueva@hotel.co" and me["full_name"] == "Nueva Recepcionista"
        assert [p["id"] for p in me["memberships"][0]["properties"]] == [str(prop.pk)]
        assert client.get("/api/v1/accounts/me/").status_code == 200  # the session started
        invitation.refresh_from_db()
        assert invitation.accepted_at is not None
        user = User.objects.get(email="nueva@hotel.co")
        assert membership_of(user, organization).role.code == "front_desk"
        fresh, fresh_token = csrf_client()
        login = fresh.post(
            "/api/v1/accounts/auth/login/",
            {"email": "nueva@hotel.co", "password": "Clave-segura-2026"},
            format="json",
            HTTP_X_CSRFTOKEN=fresh_token,
        )
        assert login.status_code == 200

    def test_existing_user_confirms_with_their_own_password(self, api, organization):
        existing = UserFactory(email="ya@otro.co")
        body = invite(api, organization, email="ya@otro.co").json()
        token = Invitation.objects.get(pk=body["id"]).token
        assert APIClient().get(f"{PUBLIC}{token}/").json()["user_exists"] is True

        client, csrf = csrf_client()
        wrong = client.post(
            f"{PUBLIC}{token}/accept/", {"password": "otra"}, format="json", HTTP_X_CSRFTOKEN=csrf
        )
        assert (wrong.status_code, wrong.json()["code"]) == (400, "invalid_credentials")
        ok = client.post(
            f"{PUBLIC}{token}/accept/", {"password": "pass1234"}, format="json", HTTP_X_CSRFTOKEN=csrf
        )
        assert ok.status_code == 200
        existing.refresh_from_db()
        assert existing.check_password("pass1234")  # never reset by an invitation
        assert membership_of(existing, organization).role.code == "front_desk"

    def test_weak_password_and_missing_name_are_field_errors(self, invitation):
        client, token = csrf_client()
        response = client.post(
            f"{PUBLIC}{invitation.token}/accept/", {"full_name": "", "password": "123"}, format="json",
            HTTP_X_CSRFTOKEN=token,
        )  # fmt: skip
        assert response.status_code == 400
        assert {"full_name", "password"} <= set(response.json()["fields"])

    def test_used_and_expired_links_are_refused(self, invitation):
        client, token = csrf_client()
        payload = {"full_name": "Nueva", "password": "Clave-segura-2026"}
        url = f"{PUBLIC}{invitation.token}/accept/"
        Invitation.objects.filter(pk=invitation.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        expired = client.post(url, payload, format="json", HTTP_X_CSRFTOKEN=token)
        assert (expired.status_code, expired.json()["code"]) == (409, "invitation_expired")
        assert APIClient().get(f"{PUBLIC}{invitation.token}/").json()["status"] == "expired"

        Invitation.objects.filter(pk=invitation.pk).update(
            expires_at=timezone.now() + timedelta(days=1), accepted_at=timezone.now()
        )
        used = client.post(url, payload, format="json", HTTP_X_CSRFTOKEN=token)
        assert (used.status_code, used.json()["code"]) == (409, "invitation_used")

    def test_an_active_member_cannot_accept_and_keeps_their_role(self, api, organization, make_member):
        body = invite(api, organization, email="dueno.dos@hotel.co", code="front_desk").json()
        token = Invitation.objects.get(pk=body["id"]).token
        owner_two = make_member("owner", email="dueno.dos@hotel.co")  # joined meanwhile (e.g. by the admin)

        client, csrf = csrf_client()
        response = client.post(
            f"{PUBLIC}{token}/accept/", {"password": "pass1234"}, format="json", HTTP_X_CSRFTOKEN=csrf
        )

        assert (response.status_code, response.json()["code"]) == (409, "already_member")
        assert membership_of(owner_two, organization).role.code == "owner"

    def test_accepting_requires_the_csrf_token(self, invitation):
        client, _token = csrf_client()
        response = client.post(
            f"{PUBLIC}{invitation.token}/accept/",
            {"full_name": "N", "password": "Clave-segura-2026"},
            format="json",
        )
        assert (response.status_code, response.json()["code"]) == (403, "csrf_failed")
