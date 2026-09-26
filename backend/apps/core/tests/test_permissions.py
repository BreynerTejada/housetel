import pytest

from apps.accounts.models import Membership
from apps.accounts.roles import ROLE_TEMPLATES
from apps.accounts.services import add_member, ensure_system_roles
from apps.accounts.tests.factories import UserFactory
from apps.core import permissions
from apps.core.permissions import catalog, codes_match, has_perm
from apps.core.tests.factories import OrganizationFactory, PropertyFactory

# Plan §D — the definitive catalog every app must declare in apps/<app>/permissions.py.
PLAN_CODES = {
    "accounts.users_manage", "accounts.roles_manage",
    "inventory.view", "inventory.manage",
    "rates.view", "rates.manage",
    "bookings.view", "bookings.manage", "bookings.checkin", "bookings.cancel", "bookings.waive_fee",
    "bookings.checkout_with_balance", "bookings.overbook",
    "guests.view", "guests.manage", "guests.merge", "guests.export",
    "finance.view", "finance.collect", "finance.void", "finance.refund", "finance.cashier",
    "frontdesk.view", "frontdesk.night_audit",
    "housekeeping.view", "housekeeping.work", "housekeeping.supervise", "housekeeping.maintenance",
    "distribution.view", "distribution.manage",
    "marketplace.manage",
    "guestportal.view", "guestportal.manage",
    "messaging.view", "messaging.send", "messaging.templates",
    "compliance.view", "compliance.invoice", "compliance.void_invoice", "compliance.sire", "compliance.tra",
    "compliance.settings",
    "revenue.view", "revenue.manage",
    "ai.copilot", "ai.onboarding", "ai.settings",
    "reports.operational", "reports.financial", "reports.performance",
    "saas.billing_view", "saas.billing_manage",
    "control.integrations", "control.automations", "control.audit", "control.audit_undo", "control.alerts",
}  # fmt: skip


@pytest.mark.parametrize(
    ("granted", "code", "expected"),
    [
        (["*"], "finance.refund", True),
        (["finance.refund"], "finance.refund", True),
        (["bookings.*"], "bookings.manage", True),
        (["bookings.*"], "guests.view", False),
        (["bookings.*"], "bookingsx.view", False),
        (["finance.view"], "finance.refund", False),
        (["finance.view", "guests.*"], "guests.merge", True),
        ([], "finance.view", False),
        (None, "finance.view", False),
    ],
)
def test_codes_match(granted, code, expected):
    assert codes_match(granted, code) is expected


def test_catalog_contains_every_plan_permission_with_both_labels():
    permissions.autodiscover()
    found = catalog()
    assert PLAN_CODES - set(found) == set()
    for code in PLAN_CODES:
        label_es, label_en = found[code]
        assert label_es.strip() and label_en.strip()


def test_every_role_template_entry_matches_some_registered_permission():
    codes = set(catalog())
    for role_code, template in ROLE_TEMPLATES.items():
        for granted in template["permissions"]:
            assert any(codes_match([granted], code) for code in codes), (
                f"{role_code}: '{granted}' matches nothing"
            )


@pytest.mark.django_db
class TestHasPerm:
    def test_owner_has_every_permission(self, owner, prop):
        assert has_perm(owner, prop, "saas.billing_manage")

    def test_front_desk_manages_bookings_but_not_rates(self, make_member, prop):
        user = make_member("front_desk")
        assert has_perm(user, prop, "bookings.manage")
        assert not has_perm(user, prop, "rates.manage")

    def test_manager_gets_everything_except_saas_billing_manage(self, make_member, prop):
        user = make_member("manager")
        assert has_perm(user, prop, "control.audit_undo")
        assert has_perm(user, prop, "saas.billing_view")
        assert not has_perm(user, prop, "saas.billing_manage")

    def test_membership_restricted_to_another_property_grants_nothing_here(
        self, make_member, prop, organization
    ):
        other = PropertyFactory(organization=organization)
        user = make_member("owner", properties=[other])
        assert not has_perm(user, prop, "bookings.view")
        assert has_perm(user, other, "bookings.view")

    def test_inactive_membership_grants_nothing(self, owner, prop):
        Membership.objects.filter(user=owner).update(is_active=False)
        assert not has_perm(owner, prop, "bookings.view")

    def test_member_of_another_organization_grants_nothing(self, prop):
        other_org = OrganizationFactory()
        ensure_system_roles(other_org)
        stranger = UserFactory()
        add_member(other_org, stranger, "owner")
        assert not has_perm(stranger, prop, "bookings.view")
