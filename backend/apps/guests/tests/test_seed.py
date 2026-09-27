"""Demo guests (plan B3 seed): ~180 per organization (65 % Colombian with CC, 35 % foreign with passport and
residence in their country), 5 % VIP, tags, consents and a few intentional duplicates for the merge demo.
The B3 seeder also adds the team demo (a custom role and a pending invitation)."""

import random
from datetime import date

import pytest

from apps.accounts.models import Invitation, Role
from apps.accounts.services import add_member
from apps.accounts.tests.factories import UserFactory
from apps.core.seed import SeedContext
from apps.core.tests.factories import OrganizationFactory, PropertyFactory
from apps.guests import seed as guests_seed
from apps.guests.models import Guest
from apps.guests.services import find_duplicates

pytestmark = pytest.mark.django_db

FOREIGN = {"US", "ES", "FR", "DE", "BR", "AR", "MX", "CA", "GB"}


@pytest.fixture
def ctx(organization):
    andino = OrganizationFactory(name="Grupo Andino")
    owner = UserFactory(email="owner@casaaurora.co")
    add_member(organization, owner, "owner")
    context = SeedContext(today=date(2026, 9, 25), rng=random.Random(20260925))
    context.orgs = {"aurora": organization, "andino": andino}
    context.properties = {
        "aurora": PropertyFactory(organization=organization),
        "andino_mde": PropertyFactory(organization=andino),
        "andino_bog": PropertyFactory(organization=andino),
    }
    context.users = {"aurora_owner": owner, "andino_owner": UserFactory(email="owner@grupoandino.co")}
    add_member(andino, context.users["andino_owner"], "owner")
    return context


def test_creates_a_realistic_mix_per_organization(ctx, organization):
    guests_seed.seed(ctx)

    guests = list(Guest.objects.filter(organization=organization))
    assert 180 <= len(guests) <= 190
    colombians = [g for g in guests if g.nationality == "CO"]
    foreigners = [g for g in guests if g.nationality != "CO"]
    assert 0.6 <= len(colombians) / len(guests) <= 0.7
    assert {g.nationality for g in foreigners} <= FOREIGN and len({g.nationality for g in foreigners}) >= 6
    assert all(g.country_of_residence == g.nationality for g in foreigners)
    assert all(g.is_foreign_non_resident for g in foreigners)
    # the demo duplicates were "typed" without a document type (or without a document at all)
    assert all(g.document_type in {"CC", ""} for g in colombians)
    assert sum(g.document_type == "CC" for g in colombians) >= len(colombians) - 2
    assert all(g.document_type in {"PA", ""} for g in foreigners)
    assert sum(g.document_type == "PA" for g in foreigners) >= len(foreigners) - 1
    assert 0.03 <= sum(g.is_vip for g in guests) / len(guests) <= 0.08
    tags = {tag for g in guests for tag in g.tags}
    assert {"frecuente", "corporativo", "luna de miel"} <= tags
    assert sum(g.data_processing_consent_at is not None for g in guests) / len(guests) >= 0.8
    assert all(g.phone.startswith("+") for g in guests if g.phone)  # E.164
    assert sum(bool(g.phone) for g in guests) >= 180
    reserved = ("@example.com", "@example.org", "@example.net")  # never real inboxes
    assert all(g.email.lower().endswith(reserved) for g in guests if g.email)
    assert Guest.objects.filter(organization=ctx.orgs["andino"]).count() >= 180


def test_includes_duplicates_ready_for_the_merge_demo(ctx, organization):
    guests_seed.seed(ctx)

    reasons = set()
    for guest in Guest.objects.filter(organization=organization, merged_into__isnull=True):
        for duplicate in find_duplicates(guest):
            reasons.update(duplicate.duplicate_reasons)
    assert {"document", "email", "phone_name"} <= reasons


def test_is_idempotent_and_shares_the_guest_ids(ctx, organization):
    guests_seed.seed(ctx)
    first = Guest.objects.count()
    ids = set(ctx.data["guests"]["aurora"])

    ctx.data.clear()
    guests_seed.seed(ctx)

    assert Guest.objects.count() == first
    assert set(ctx.data["guests"]["aurora"]) == ids
    assert ids == set(Guest.objects.filter(organization=organization).values_list("pk", flat=True))


def test_adds_the_team_demo(ctx, organization):
    guests_seed.seed(ctx)
    guests_seed.seed(ctx)

    role = Role.objects.get(organization=organization, code="recepcion_nocturna")
    assert not role.is_system and "bookings.checkin" in role.permissions
    invitation = Invitation.objects.get(organization=organization, email="nocturno@casaaurora.co")
    assert (invitation.role, invitation.accepted_at) == (role, None)
    assert Invitation.objects.filter(email="nocturno@casaaurora.co").count() == 1
