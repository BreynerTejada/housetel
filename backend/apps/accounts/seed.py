"""Team demo (plan B3): a custom role and a pending invitation per demo organization.

`apps.core.seed.SEED_ORDER` has no `accounts` entry (it is fixed by core tests), so apps.guests.seed calls
this at its end. Idempotent; no email is sent while seeding.
"""

from apps.accounts.models import Invitation, Role

NIGHT_SHIFT_ROLE = {
    "code": "recepcion_nocturna",
    "name": "Recepción nocturna",
    "description": "Turno de noche: llegadas tardías, check-in/out y cobros; sin cancelar ni reembolsar.",
    "permissions": sorted([
        "frontdesk.view", "bookings.view", "bookings.manage", "bookings.checkin", "guests.view",
        "guests.manage", "finance.view", "finance.collect", "housekeeping.view", "messaging.view",
        "messaging.send", "inventory.view", "rates.view", "control.alerts",
    ]),
}  # fmt: skip

INVITATIONS = {
    # organization key: (email, role code, inviter key, restricted property keys or None = all)
    "aurora": ("nocturno@casaaurora.co", "recepcion_nocturna", "aurora_owner", None),
    "andino": ("reservas.bogota@grupoandino.co", "front_desk", "andino_owner", ["andino_bog"]),
}


def seed(ctx) -> None:
    for key, organization in ctx.orgs.items():
        Role.objects.get_or_create(
            organization=organization,
            code=NIGHT_SHIFT_ROLE["code"],
            defaults={**NIGHT_SHIFT_ROLE, "is_system": False},
        )
        if key not in INVITATIONS:
            continue
        email, role_code, inviter_key, property_keys = INVITATIONS[key]
        if Invitation.objects.filter(organization=organization, email=email).exists():
            continue
        role = Role.objects.filter(organization=organization, code=role_code).first()
        if role is None:
            continue
        invitation = Invitation.objects.create(
            organization=organization,
            email=email,
            role=role,
            all_properties=property_keys is None,
            invited_by=ctx.users.get(inviter_key),
        )
        if property_keys:
            invitation.properties.set([ctx.properties[p] for p in property_keys if p in ctx.properties])
    ctx.log("  equipo: rol «Recepción nocturna» e invitaciones pendientes")
