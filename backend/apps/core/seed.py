"""Demo data (spec §10, plan Step 8). `python manage.py seed_demo [--reset]`.

`seed_base()` creates the platform admin, the two demo organizations with their system roles, the three
properties and the demo users (password `housetel123`). Then every app in SEED_ORDER that has an
`apps/<app>/seed.py` gets `seed(ctx)` called with the shared SeedContext. Every seeder must be idempotent:
running it again must not duplicate data (and should not overwrite what the demo user changed).
"""

import random
import time as time_module
from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal
from importlib import import_module
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services import add_member, ensure_system_roles
from apps.core.models import Organization, Property
from apps.core.signals import seeding

# Phase P (P-INT): `corporate` right after `bookings` (P4: the finance seed then charges the guests' part
# and the compliance seed invoices the company folios in date order), `imports` last (P5: needs the guests).
SEED_ORDER = ["inventory", "rates", "guests", "bookings", "corporate", "finance", "housekeeping",
              "distribution", "marketplace", "guestportal", "messaging", "compliance", "revenue", "ai",
              "saas", "frontdesk", "reports", "control", "imports"]  # fmt: skip

DEMO_PASSWORD = "housetel123"
RNG_SEED = 20260925


@dataclass
class SeedContext:
    today: date
    rng: random.Random  # random.Random(20260925) — deterministic
    orgs: dict[str, Organization] = field(default_factory=dict)  # "aurora", "andino"
    properties: dict[str, Property] = field(default_factory=dict)  # "aurora", "andino_mde", "andino_bog"
    users: dict[str, User] = field(default_factory=dict)  # see USERS
    data: dict = field(default_factory=dict)  # shared space between seeders
    stdout: Any = None

    def log(self, msg: str) -> None:
        if self.stdout is None:
            return
        # Django's OutputWrapper appends its own newline.
        self.stdout.write(msg if getattr(self.stdout, "ending", None) else msg + "\n")


ORGANIZATIONS = {
    "aurora": {
        "slug": "casa-aurora",
        "name": "Casa Aurora",
        "legal_name": "Casa Aurora Hoteles S.A.S.",
        "nit": "901234567-1",
    },
    "andino": {
        "slug": "grupo-andino",
        "name": "Grupo Andino",
        "legal_name": "Grupo Hotelero Andino S.A.S.",
        "nit": "900765432-5",
    },
}

PROPERTIES = {
    "aurora": {
        "org": "aurora",
        "slug": "casa-aurora",
        "name": "Hotel Casa Aurora",
        "property_type": "boutique",
        "city": "Cartagena",
        "department": "Bolívar",
        "address": "Calle del Cuartel #36-77, Centro Histórico",
        "latitude": Decimal("10.4236"),
        "longitude": Decimal("-75.5518"),
        "phone": "+57 605 660 1234",
        "email": "reservas@casaaurora.co",
        "website": "https://casaaurora.co",
        "rnt_number": "RNT 98765",
        "star_rating": 4,
        "branding": {"primary_color": "#B4583B"},
        "description": {
            "es": (
                "Casa colonial restaurada en el corazón de la ciudad amurallada, a pasos de la Plaza de "
                "San Diego: patios con buganvilias, piscina en la terraza y suites con vista al mar Caribe."
            ),
            "en": (
                "A restored colonial house in the heart of the walled city, steps from Plaza de San Diego: "
                "bougainvillea courtyards, a rooftop pool and suites overlooking the Caribbean Sea."
            ),
        },
    },
    "andino_mde": {
        "org": "andino",
        "slug": "andino-medellin",
        "name": "Andino Medellín",
        "property_type": "hotel",
        "city": "Medellín",
        "department": "Antioquia",
        "address": "Carrera 37 #8A-32, El Poblado",
        "latitude": Decimal("6.2086"),
        "longitude": Decimal("-75.5659"),
        "phone": "+57 604 444 5566",
        "email": "medellin@grupoandino.co",
        "website": "https://grupoandino.co/medellin",
        "rnt_number": "RNT 54321",
        "star_rating": 4,
        "branding": {"primary_color": "#4E6C88"},
        "description": {
            "es": (
                "Hotel urbano en El Poblado, cerca del Parque Lleras: habitaciones amplias, coworking, "
                "gimnasio y desayuno con productos antioqueños."
            ),
            "en": (
                "An urban hotel in El Poblado near Parque Lleras: spacious rooms, coworking, a gym and "
                "breakfast with local Antioquian produce."
            ),
        },
    },
    "andino_bog": {
        "org": "andino",
        "slug": "andino-hostel-bogota",
        "name": "Andino Hostel Bogotá",
        "property_type": "hostel",
        "city": "Bogotá",
        "department": "Cundinamarca",
        "address": "Calle 12B #2-58, La Candelaria",
        "latitude": Decimal("4.5981"),
        "longitude": Decimal("-74.0758"),
        "phone": "+57 601 333 7788",
        "email": "bogota@grupoandino.co",
        "website": "https://grupoandino.co/bogota",
        "rnt_number": "RNT 67890",
        "star_rating": 3,
        "branding": {"primary_color": "#5F7F66"},
        "description": {
            "es": (
                "Hostal en La Candelaria con dormitorios compartidos y habitaciones privadas, cocina común, "
                "terraza con vista a Monserrate y tours a pie por el centro histórico."
            ),
            "en": (
                "A hostel in La Candelaria with shared dorms and private rooms, a communal kitchen, a "
                "terrace facing Monserrate and walking tours of the historic center."
            ),
        },
    },
}

HOUSE_RULES = {
    "es": (
        "Check-in desde las 15:00 y check-out hasta las 12:00. No se permite fumar dentro de las "
        "habitaciones. Silencio entre las 22:00 y las 7:00."
    ),
    "en": (
        "Check-in from 3 pm, check-out until 12 pm. No smoking inside the rooms. "
        "Quiet hours from 10 pm to 7 am."
    ),
}

# key: (email, full name, organization key, role code, restricted property keys or None = all properties)
USERS = {
    "aurora_owner": ("owner@casaaurora.co", "Valentina Rojas", "aurora", "owner", None),
    "aurora_front": ("recepcion@casaaurora.co", "Andrés Gómez", "aurora", "front_desk", None),
    "aurora_hk": ("limpieza@casaaurora.co", "Luz Marina Pérez", "aurora", "housekeeping", None),
    "aurora_acct": ("contabilidad@casaaurora.co", "Carolina Díaz", "aurora", "accountant", None),
    "aurora_maint": ("mantenimiento@casaaurora.co", "Jorge Castillo", "aurora", "maintenance", None),
    "andino_owner": ("owner@grupoandino.co", "Santiago Restrepo", "andino", "owner", None),
    "andino_front": ("recepcion@grupoandino.co", "Daniela Ospina", "andino", "front_desk", None),
    "andino_hk": ("limpieza@grupoandino.co", "José Martínez", "andino", "housekeeping", ["andino_mde"]),
}


def run(*, reset: bool = False, stdout=None) -> SeedContext:
    ctx = SeedContext(today=timezone.localdate(), rng=random.Random(RNG_SEED), stdout=stdout)
    with seeding():
        with transaction.atomic():
            if reset:
                _reset(ctx)
            seed_base(ctx)
        for app in SEED_ORDER:
            module = _load_seeder(app)
            if module is None:
                continue
            ctx.log(f"→ {app}")
            started = time_module.monotonic()
            with transaction.atomic():
                module.seed(ctx)
            ctx.log(f"  {app}: {time_module.monotonic() - started:.1f} s")
    ctx.log("Seed completo")
    return ctx


def seed_base(ctx: SeedContext) -> None:
    ctx.log("→ base (plataforma, organizaciones, propiedades, usuarios)")
    ctx.users["admin"] = _user("admin@housetel.co", "Administración Housetel", platform_admin=True)
    for key, values in ORGANIZATIONS.items():
        org, _ = Organization.objects.get_or_create(
            slug=values["slug"],
            defaults={
                "name": values["name"],
                "legal_name": values["legal_name"],
                "nit": values["nit"],
                "country": "CO",
                "status": Organization.Status.ACTIVE,
            },
        )
        ensure_system_roles(org)
        ctx.orgs[key] = org
    for key, values in PROPERTIES.items():
        values = dict(values)
        org = ctx.orgs[values.pop("org")]
        prop, _ = Property.objects.get_or_create(
            slug=values.pop("slug"),
            defaults={
                **values,
                "organization": org,
                "legal_name": org.legal_name,
                "nit": org.nit,
                "house_rules": HOUSE_RULES,
                "check_in_time": time(15, 0),
                "check_out_time": time(12, 0),
                "marketplace_listed": True,
                "business_date": ctx.today,
                "status": Property.Status.ACTIVE,
            },
        )
        ctx.properties[key] = prop
    for key, (email, full_name, org_key, role_code, restricted_to) in USERS.items():
        user = _user(email, full_name)
        properties = [ctx.properties[p] for p in restricted_to] if restricted_to else None
        add_member(
            ctx.orgs[org_key], user, role_code, all_properties=properties is None, properties=properties
        )
        ctx.users[key] = user


def _user(email: str, full_name: str, *, platform_admin: bool = False) -> User:
    user = User.objects.filter(email=email).first()
    if user is None:
        user = User.objects.create_user(email, DEMO_PASSWORD, full_name=full_name, language="es")
    if platform_admin and not (user.is_platform_admin and user.is_superuser and user.is_staff):
        user.is_platform_admin = user.is_superuser = user.is_staff = True
        user.save(update_fields=["is_platform_admin", "is_superuser", "is_staff", "updated_at"])
    return user


def _reset(ctx: SeedContext) -> None:
    ctx.log("→ reset: borrando organizaciones y usuarios que no son superadmin")
    Organization.objects.all().delete()  # cascades every tenant-scoped row
    User.objects.filter(is_superuser=False).delete()


def _load_seeder(app: str):
    """`apps.<app>.seed` if the app has one, else None (errors inside an existing module propagate)."""
    name = f"apps.{app}.seed"
    try:
        return import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name == name:
            return None
        raise
