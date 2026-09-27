"""Base demo seed (plan Step 8, spec §10). App seeders are isolated here (each app tests its own seed.py)."""

import random
import sys
from datetime import date
from decimal import Decimal
from io import StringIO
from types import ModuleType, SimpleNamespace

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import Membership, Role, User
from apps.accounts.tests.factories import UserFactory
from apps.core import seed
from apps.core.models import Organization, Property
from apps.core.tests.factories import OrganizationFactory

pytestmark = pytest.mark.django_db

USERS = {
    "admin": "admin@housetel.co",
    "aurora_owner": "owner@casaaurora.co",
    "aurora_front": "recepcion@casaaurora.co",
    "aurora_hk": "limpieza@casaaurora.co",
    "aurora_acct": "contabilidad@casaaurora.co",
    "andino_owner": "owner@grupoandino.co",
    "andino_front": "recepcion@grupoandino.co",
    "andino_hk": "limpieza@grupoandino.co",
}


@pytest.fixture(autouse=True)
def base_only(monkeypatch):
    monkeypatch.setattr(seed, "_load_seeder", lambda app: None)


def counts():
    return {
        "orgs": Organization.objects.count(),
        "properties": Property.objects.count(),
        "users": User.objects.count(),
        "memberships": Membership.objects.count(),
        "roles": Role.objects.count(),
    }


def test_seed_order_is_the_planned_one():
    assert seed.SEED_ORDER == [
        "inventory", "rates", "guests", "bookings", "finance", "housekeeping", "distribution", "marketplace",
        "guestportal", "messaging", "compliance", "revenue", "ai", "saas", "frontdesk", "reports", "control",
    ]  # fmt: skip


class TestBase:
    def test_creates_the_platform_admin(self):
        seed.run()
        admin = User.objects.get(email="admin@housetel.co")
        assert admin.is_platform_admin and admin.is_superuser and admin.is_staff
        assert admin.check_password("housetel123")
        assert not admin.memberships.exists()

    def test_creates_the_two_active_organizations_with_system_roles(self):
        ctx = seed.run()
        assert set(ctx.orgs) == {"aurora", "andino"}
        assert {(o.slug, o.name, o.status) for o in Organization.objects.all()} == {
            ("casa-aurora", "Casa Aurora", "active"),
            ("grupo-andino", "Grupo Andino", "active"),
        }
        for org in ctx.orgs.values():
            assert Role.objects.filter(organization=org, is_system=True).count() == 7

    def test_creates_the_three_demo_properties(self):
        ctx = seed.run()
        assert set(ctx.properties) == {"aurora", "andino_mde", "andino_bog"}
        rows = {
            p.slug: (p.organization.slug, p.property_type, p.city, p.department, p.latitude, p.longitude)
            for p in Property.objects.select_related("organization")
        }
        assert rows == {
            "casa-aurora": (
                "casa-aurora",
                "boutique",
                "Cartagena",
                "Bolívar",
                Decimal("10.423600"),
                Decimal("-75.551800"),
            ),
            "andino-medellin": (
                "grupo-andino",
                "hotel",
                "Medellín",
                "Antioquia",
                Decimal("6.208600"),
                Decimal("-75.565900"),
            ),
            "andino-hostel-bogota": (
                "grupo-andino",
                "hostel",
                "Bogotá",
                "Cundinamarca",
                Decimal("4.598100"),
                Decimal("-74.075800"),
            ),
        }
        for prop in Property.objects.all():
            assert prop.marketplace_listed and prop.business_date == timezone.localdate()
            assert prop.description["es"] and prop.description["en"]
            assert prop.rnt_number and prop.nit and prop.legal_name and prop.status == "active"
        assert Property.objects.get(slug="casa-aurora").name == "Hotel Casa Aurora"

    def test_creates_the_eight_demo_users_with_their_roles(self):
        ctx = seed.run()
        assert {key: user.email for key, user in ctx.users.items()} == USERS
        roles = {
            (m.user.email, m.organization.slug): (m.role.code, m.all_properties)
            for m in Membership.objects.select_related("user", "organization", "role")
        }
        assert roles == {
            ("owner@casaaurora.co", "casa-aurora"): ("owner", True),
            ("recepcion@casaaurora.co", "casa-aurora"): ("front_desk", True),
            ("limpieza@casaaurora.co", "casa-aurora"): ("housekeeping", True),
            ("contabilidad@casaaurora.co", "casa-aurora"): ("accountant", True),
            ("owner@grupoandino.co", "grupo-andino"): ("owner", True),
            ("recepcion@grupoandino.co", "grupo-andino"): ("front_desk", True),
            ("limpieza@grupoandino.co", "grupo-andino"): ("housekeeping", False),
        }
        hk = Membership.objects.get(user__email="limpieza@grupoandino.co")
        assert [p.slug for p in hk.properties.all()] == ["andino-medellin"]
        assert all(User.objects.get(email=email).check_password("housetel123") for email in USERS.values())


class TestIdempotency:
    def test_running_twice_does_not_duplicate(self):
        seed.run()
        first = counts()
        seed.run()
        assert counts() == first == {"orgs": 2, "properties": 3, "users": 8, "memberships": 7, "roles": 14}

    def test_existing_data_is_kept(self):
        seed.run()
        Property.objects.filter(slug="casa-aurora").update(business_date=date(2020, 1, 1), phone="+57 1")
        seed.run()
        prop = Property.objects.get(slug="casa-aurora")
        assert (prop.business_date, prop.phone) == (date(2020, 1, 1), "+57 1")

    def test_reset_removes_other_data_but_keeps_superusers(self):
        seed.run()
        admin_pk = User.objects.get(email="admin@housetel.co").pk
        OrganizationFactory(slug="otra")
        UserFactory(email="stranger@example.com")
        root = User.objects.create_superuser("root@example.com", "x")

        seed.run(reset=True)

        assert counts()["orgs"] == 2 and not Organization.objects.filter(slug="otra").exists()
        assert not User.objects.filter(email="stranger@example.com").exists()
        assert User.objects.get(email="admin@housetel.co").pk == admin_pk
        assert User.objects.filter(pk=root.pk).exists()


class TestAppSeeders:
    def test_runs_existing_app_seeders_in_seed_order_with_the_context(self, monkeypatch):
        calls = []

        def loader(app):
            if app not in {"control", "inventory", "rates"}:
                return None
            return SimpleNamespace(
                seed=lambda ctx: calls.append((app, ctx.properties["aurora"].slug, ctx.today))
            )

        monkeypatch.setattr(seed, "_load_seeder", loader)
        seed.run()
        today = timezone.localdate()
        assert calls == [
            ("inventory", "casa-aurora", today),
            ("rates", "casa-aurora", today),
            ("control", "casa-aurora", today),
        ]

    @pytest.mark.django_db(transaction=True)
    def test_seeders_and_their_on_commit_signals_run_while_is_seeding_is_true(self, monkeypatch):
        # transaction=True: like production, run()'s atomic blocks are outermost, so on_commit
        # callbacks (where signals are dispatched) fire inside run() and must still see the flag.
        from django.db import transaction

        from apps.core.signals import is_seeding

        observed = []

        def seeder(ctx):
            observed.append(("seed", is_seeding()))
            transaction.on_commit(lambda: observed.append(("on_commit", is_seeding())))

        monkeypatch.setattr(
            seed, "_load_seeder", lambda app: SimpleNamespace(seed=seeder) if app == "inventory" else None
        )
        seed.run()
        assert observed == [("seed", True), ("on_commit", True)]
        assert is_seeding() is False

    def test_seeders_share_data_and_a_deterministic_rng(self, monkeypatch):
        seen = {}

        def loader(app):
            if app == "inventory":
                return SimpleNamespace(seed=lambda ctx: ctx.data.update(first=ctx.rng.random()))
            if app == "rates":
                return SimpleNamespace(seed=lambda ctx: seen.update(ctx.data))
            return None

        monkeypatch.setattr(seed, "_load_seeder", loader)
        seed.run()
        assert seen == {"first": random.Random(20260925).random()}

    def test_load_seeder_imports_the_app_module(self, monkeypatch):
        monkeypatch.undo()  # real loader
        fake = ModuleType("apps.frontdesk.seed")
        fake.seed = lambda ctx: None
        monkeypatch.setitem(sys.modules, "apps.frontdesk.seed", fake)
        assert seed._load_seeder("frontdesk") is fake

    def test_load_seeder_skips_apps_without_seed_but_surfaces_real_import_errors(self, monkeypatch):
        monkeypatch.undo()

        def fake_import(name):
            raise ModuleNotFoundError(
                f"No module named {name!r}",
                name=name if name.endswith("frontdesk.seed") else "missing_dependency",
            )

        monkeypatch.setattr(seed, "import_module", fake_import)
        assert seed._load_seeder("frontdesk") is None
        with pytest.raises(ModuleNotFoundError):
            seed._load_seeder("reports")


def test_management_command_seeds_and_reports_progress():
    out = StringIO()
    call_command("seed_demo", stdout=out)
    call_command("seed_demo", "--reset", stdout=out)
    assert "Seed completo" in out.getvalue()
    assert counts()["properties"] == 3
