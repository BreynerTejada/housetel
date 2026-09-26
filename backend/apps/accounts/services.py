from django.db import transaction

from apps.accounts.models import Membership, Role
from apps.accounts.roles import ROLE_DESCRIPTIONS, ROLE_TEMPLATES
from apps.core.errors import DomainError


def ensure_system_roles(organization) -> dict[str, Role]:
    """Create or refresh the organization's copies of the system roles (idempotent)."""
    roles: dict[str, Role] = {}
    with transaction.atomic():
        for code, template in ROLE_TEMPLATES.items():
            role, _ = Role.objects.update_or_create(
                organization=organization,
                code=code,
                defaults={
                    "name": template["name"],
                    "permissions": list(template["permissions"]),
                    "description": ROLE_DESCRIPTIONS.get(code, ""),
                    "is_system": True,
                },
            )
            roles[code] = role
    return roles


def add_member(organization, user, role_code, *, all_properties=True, properties=None) -> Membership:
    """Create or update the user's single membership in `organization`."""
    with transaction.atomic():
        role = Role.objects.filter(organization=organization, code=role_code).first()
        if role is None:
            role = ensure_system_roles(organization).get(role_code)
        if role is None:
            raise DomainError(f"Rol desconocido: {role_code}", code="unknown_role")
        membership, _ = Membership.objects.update_or_create(
            user=user,
            organization=organization,
            defaults={"role": role, "all_properties": all_properties, "is_active": True},
        )
        membership.properties.set([] if all_properties else list(properties or []))
    return membership
