"""Self-service signup (`POST /api/v1/public/saas/signup/`): organization in trial + property + owner +
subscription `trialing` (plan by estimated units) + default taxes, policies and rate plans."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import User
from apps.accounts.services import add_member, ensure_system_roles
from apps.core import audit
from apps.core.errors import DomainError
from apps.core.models import Organization, Property
from apps.saas.services import billing
from apps.saas.services.plans import ensure_default_plans


@dataclass
class SignupResult:
    user: User
    organization: Organization
    property: Property


def unique_slug(model, name: str, *, max_length: int = 60) -> str:
    base = slugify(name)[:max_length].strip("-") or "hotel"
    slug, n = base, 2
    while model.objects.filter(slug=slug).exists():
        suffix = f"-{n}"
        slug = f"{base[: max_length - len(suffix)]}{suffix}"
        n += 1
    return slug


def signup(data: dict, *, language: str = "es") -> SignupResult:
    """`data` is already validated by the serializer (email free, password valid, terms accepted)."""
    email = data["email"].strip().lower()
    if User.objects.filter(email__iexact=email).exists():
        raise DomainError(
            "Ya existe una cuenta con este email. Inicia sesión o usa otro correo.",
            code="email_taken",
            fields={"email": ["Ya existe una cuenta con este email"]},
        )
    ensure_default_plans()
    now = timezone.now()
    with transaction.atomic():
        org = Organization.objects.create(
            name=data["hotel_name"].strip(),
            slug=unique_slug(Organization, data["hotel_name"]),
            country="CO",
            status=Organization.Status.TRIAL,
            trial_ends_at=now + timedelta(days=billing.TRIAL_DAYS),
        )
        ensure_system_roles(org)
        prop = Property.objects.create(
            organization=org,
            name=data["hotel_name"].strip(),
            slug=unique_slug(Property, data["hotel_name"]),
            property_type=data["property_type"],
            city=data.get("city", "").strip(),
            department=data.get("department", "").strip(),
            phone=data.get("phone", "").strip(),
            email=email,
            default_language=language,
            business_date=timezone.localdate(),
            marketplace_listed=False,
            settings={"signup": {"rooms_estimate": data["rooms_estimate"], "at": now.isoformat()}},
        )
        user = User.objects.create_user(
            email,
            data["password"],
            full_name=data["owner_name"].strip(),
            phone=data.get("phone", "").strip(),
            language=language,
        )
        add_member(org, user, "owner", all_properties=True)
        sub = billing.create_trial_subscription(org, units=int(data["rooms_estimate"]))
        _default_rates(prop, user)
        audit.record(
            action="saas.signup",
            target=org,
            organization=org,
            property=prop,
            actor=user,
            source="user",
            summary=f"Registro de {org.name} (plan {sub.plan.code}, prueba de {billing.TRIAL_DAYS} días)",
            changes={"plan": sub.plan.code, "rooms_estimate": data["rooms_estimate"]},
        )
    return SignupResult(user=user, organization=org, property=prop)


def _default_rates(prop, user) -> None:
    """Default taxes (IVA 19 % with the exemption for foreign non-residents), cancellation policies and the
    FLEX / NR / BB plans, so the hotel only has to create its categories and set prices."""
    from apps.rates.services.provision import provision_rates

    provision_rates(prop, room_type_prices={}, actor=user)
