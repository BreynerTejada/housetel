"""Where an audited object lives in the app (`target_link`) and which audit targets belong to a reservation.

Only ORM reads of other apps' models (plan §B allows reading). Models are looked up lazily by label so the
control center keeps working if an app is missing.
"""

from collections import defaultdict

from django.apps import apps as django_apps
from django.db.models import Q

MAX_IDS_PER_RELATION = 2000
# Reservation-owned objects whose own children are also part of the reservation's history.
EXPAND = {"bookings.reservation", "bookings.stay", "finance.folio", "finance.payment"}
SKIP = {"core.auditevent", "core.alert"}

# target_type → a fixed page of the app (objects without a detail page of their own).
STATIC_LINKS = {
    "core.integrationsetting": "/app/settings/integrations",
    "core.automationsetting": "/app/settings/automations",
    "core.automationrun": "/app/settings/automations",
    "core.alert": "/app/alerts",
    "core.property": "/app/settings/property",
    "finance.cashshift": "/app/cashier",
    "rates.rateplan": "/app/rates/plans",
    "rates.dailyrate": "/app/rates",
    "rates.season": "/app/rates/plans?tab=seasons",
    "rates.seasonrate": "/app/rates/plans?tab=seasons",
    "rates.roomtyperatedefaults": "/app/rates/plans?tab=defaults",
    "rates.promocode": "/app/rates/promos",
    "rates.tax": "/app/settings/taxes",
    "rates.cancellationpolicy": "/app/settings/policies",
    "rates.extra": "/app/settings/extras",
    "inventory.roomblock": "/app/settings/rooms",
    "inventory.customfielddefinition": "/app/settings/custom-fields",
    "housekeeping.housekeepingtask": "/app/housekeeping",
    "housekeeping.maintenanceticket": "/app/maintenance",
    "housekeeping.housekeepingsettings": "/app/settings/housekeeping",
    "distribution.channelconnection": "/app/channels",
    "revenue.revenuesettings": "/app/revenue",
    "revenue.pricingrule": "/app/revenue",
    "revenue.raterecommendation": "/app/revenue",
    "revenue.revenuerun": "/app/revenue",
    "revenue.pricebounds": "/app/revenue",
    "messaging.conversation": "/app/inbox",
    "accounts.membership": "/app/settings/users",
    "accounts.invitation": "/app/settings/users",
    "accounts.role": "/app/settings/roles",
    "compliance.compliancesettings": "/app/settings/compliance",
    "compliance.invoiceresolution": "/app/settings/compliance",
    "compliance.sirereport": "/app/compliance?tab=sire",
    "messaging.messagetemplate": "/app/settings/messaging",
    "messaging.lifecyclerule": "/app/settings/messaging",
    "marketplace.bookingenginesettings": "/app/settings/booking-engine",
    "marketplace.listingcontent": "/app/settings/booking-engine",
    "guestportal.guestportalsettings": "/app/settings/guest-portal",
    "ai.aisettings": "/app/settings/ai",
    "ai.propertyfaq": "/app/settings/chatbot",
}

# target_type → path to the reservation id (resolved in one query per type).
RESERVATION_PATHS = {
    "bookings.stay": "reservation_id",
    "finance.folio": "reservation_id",
    "finance.charge": "folio__reservation_id",
    "finance.payment": "folio__reservation_id",
    "finance.paymentintent": "folio__reservation_id",
    "finance.refund": "payment__folio__reservation_id",
    "guestportal.onlinecheckin": "reservation_id",
    "guestportal.servicerequest": "reservation_id",
    "compliance.invoice": "reservation_id",
    "compliance.traregistration": "reservation_id",
}


def _model(label: str):
    try:
        return django_apps.get_model(label)
    except (LookupError, ValueError):
        return None


def resolve_links(events) -> dict[str, str]:
    """{event_id: link} for a page of audit events (a few queries, never one per event)."""
    by_type: dict[str, set[str]] = defaultdict(set)
    for event in events:
        if event.target_type in RESERVATION_PATHS and event.target_id:
            by_type[event.target_type].add(event.target_id)
    reservation_of: dict[tuple[str, str], str] = {}
    for label, ids in by_type.items():
        model = _model(label)
        if model is None:
            continue
        path = RESERVATION_PATHS[label]
        try:
            rows = model._default_manager.filter(pk__in=list(ids)).values_list("pk", path)
            for pk, reservation_id in rows:
                if reservation_id:
                    reservation_of[(label, str(pk))] = str(reservation_id)
        except Exception:  # noqa: BLE001 - a renamed field must not break the timeline
            continue

    links: dict[str, str] = {}
    for event in events:
        link = ""
        target_type, target_id = event.target_type, event.target_id
        if target_type == "bookings.reservation" and target_id:
            link = f"/app/reservations/{target_id}"
        elif (target_type, target_id) in reservation_of:
            link = f"/app/reservations/{reservation_of[(target_type, target_id)]}"
        elif target_type == "guests.guest" and target_id:
            link = f"/app/guests/{target_id}"
        elif target_type == "inventory.roomtype" and target_id:
            link = f"/app/settings/room-types/{target_id}"
        elif target_type == "inventory.room" and target_id:
            link = f"/app/settings/rooms/{target_id}"
        elif target_type == "compliance.invoice" and target_id:
            link = f"/app/compliance?tab=invoices&invoice={target_id}"
        elif target_type in STATIC_LINKS:
            link = STATIC_LINKS[target_type]
        links[str(event.pk)] = link
    return links


def reservation_filter(reservation) -> Q:
    """Audit events of a reservation: its own, its stays', folios', charges', payments', refunds', and those
    of every other object that points to it (online check-in, invoices, requests…), found generically through
    the reverse relations."""
    collected: dict[str, set[str]] = defaultdict(set)
    collected["bookings.reservation"].add(str(reservation.pk))
    frontier = [(type(reservation), [reservation.pk])]
    depth = 0
    while frontier and depth < 3:
        next_frontier = []
        for model, ids in frontier:
            for rel in model._meta.related_objects:
                if rel.many_to_many or not getattr(rel, "field", None):
                    continue
                related = rel.related_model
                label = related._meta.label_lower
                if label in SKIP or not related.__module__.startswith("apps."):
                    continue
                try:
                    found = list(
                        related._default_manager.filter(**{f"{rel.field.name}__in": ids}).values_list(
                            "pk", flat=True
                        )[:MAX_IDS_PER_RELATION]
                    )
                except Exception:  # noqa: BLE001
                    continue
                new_ids = [pk for pk in found if str(pk) not in collected[label]]
                collected[label].update(str(pk) for pk in found)
                if new_ids and label in EXPAND:
                    next_frontier.append((related, new_ids))
        frontier = next_frontier
        depth += 1
    query = Q()
    for label, ids in collected.items():
        if ids:
            query |= Q(target_type=label, target_id__in=list(ids))
    return query
