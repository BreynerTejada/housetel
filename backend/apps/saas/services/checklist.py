"""The "getting started" checklist of a property (`GET /api/v1/saas/getting-started/`).

Every step is computed from real data (read-only ORM reads of other apps):
profile → inventory profile fields; rooms → sellable units; rates → every active category has a base price;
payments → online payments integration in real mode; channels → marketplace listing or a channel connection;
team → another member or a pending invitation; first_booking → any reservation (or import them: P5).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.utils import timezone

PROFILE_FIELDS = ("legal_name", "nit", "rnt_number", "phone", "email", "address", "city")


def _profile_missing(prop) -> list[str]:
    missing = [name for name in PROFILE_FIELDS if not getattr(prop, name, "")]
    description = prop.description or {}
    if not (description.get("es") or description.get("en")):
        missing.append("description")
    return missing


def getting_started(prop, organization) -> dict:
    from apps.accounts.models import Invitation, Membership
    from apps.bookings.models import Reservation
    from apps.core.integrations import get_setting, is_live
    from apps.inventory.services import inventory_summary
    from apps.rates.models import RoomTypeRateDefaults

    summary = inventory_summary(prop)
    units = summary["totals"]["units"]
    active_types = [rt for rt in summary["room_types"] if rt["is_active"]]
    missing = _profile_missing(prop)

    priced_types = set(
        RoomTypeRateDefaults.objects.filter(
            room_type__property=prop, rate_plan__kind="base", rate_plan__is_active=True, price__gt=0
        ).values_list("room_type_id", flat=True)
    )
    unpriced = [rt for rt in active_types if rt["id"] not in {str(pk) for pk in priced_types}]

    payments = get_setting(prop, "payments")

    connections = 0
    if django_apps.is_installed("apps.distribution"):
        try:
            ChannelConnection = django_apps.get_model("distribution", "ChannelConnection")
            connections = ChannelConnection.objects.filter(property=prop).count()
        except LookupError:
            connections = 0

    members = Membership.objects.filter(organization=organization, is_active=True).count()
    invitations = Invitation.objects.filter(
        organization=organization, accepted_at__isnull=True, expires_at__gt=timezone.now()
    ).count()
    reservations = Reservation.objects.filter(property=prop).count()

    steps = [
        {
            "id": "profile",
            "done": not missing,
            "detail": {"missing": missing},
            "link": "/app/settings/property",
        },
        {
            "id": "rooms",
            "done": units > 0,
            "detail": {"room_types": len(active_types), "units": units, "warnings": len(summary["warnings"])},
            "link": "/app/settings/room-types",
            "alt_link": "/app/onboarding",
        },
        {
            "id": "rates",
            "done": bool(active_types) and not unpriced,
            "detail": {"priced": len(active_types) - len(unpriced), "room_types": len(active_types)},
            "link": "/app/rates",
        },
        {
            "id": "payments",
            # P-INT: done when Wompi really works (real, on and with its keys), not just switched to real.
            "done": is_live(prop, "payments"),
            "detail": {"mode": payments.mode, "enabled": payments.enabled},
            "link": "/app/settings/integrations",
        },
        {
            "id": "channels",
            "done": bool(prop.marketplace_listed or connections),
            "detail": {"marketplace_listed": prop.marketplace_listed, "connections": connections},
            "link": "/app/settings/booking-engine",
            "alt_link": "/app/channels",
        },
        {
            "id": "team",
            "done": members > 1 or invitations > 0,
            "detail": {"members": members, "invitations": invitations},
            "link": "/app/settings/users",
        },
        {
            "id": "first_booking",
            "done": reservations > 0,
            "detail": {"reservations": reservations},
            "link": "/app/reservations/new",
            "alt_link": "/app/settings/import",  # P5: bring the bookings and guests of the previous PMS
        },
    ]
    completed = sum(1 for step in steps if step["done"])
    return {
        "property": {"id": str(prop.pk), "name": prop.name, "slug": prop.slug},
        "steps": steps,
        "completed": completed,
        "total": len(steps),
        "percent": round(completed * 100 / len(steps)),
    }
