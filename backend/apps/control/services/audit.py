"""Audit timeline of a property (plan C12): filters, detail with before/after, and the generic undo.

Scope: the events of the property **plus the organization-level events** (`property` null, same
organization: guests, users, roles…). Platform events (organization null) are never shown.
"""

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import CharField, Count, Q, QuerySet
from django.db.models.functions import Cast

from apps.control.services.scrub import scrub
from apps.control.services.targets import reservation_filter, resolve_links
from apps.core import audit as core_audit
from apps.core.errors import ConfirmationRequired, ConflictError, DomainError, NotFoundError
from apps.core.models import AuditEvent

MAX_ROW_CHANGES = 120


class UndoConflict(ConflictError):
    code = "undo_conflict"


def scoped(property):
    return AuditEvent.objects.filter(
        Q(property=property) | Q(property__isnull=True, organization_id=property.organization_id)
    )


def _parse_day(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise DomainError(
            "Fecha inválida (usa AAAA-MM-DD)", code="validation_error", fields={field: ["Fecha inválida"]}
        ) from None


def filtered(property, params) -> QuerySet:
    """Filters (all optional): action (exact), app (prefix before the dot), source, actor (user id),
    target_type, target_id, reversible=1, undone=0|1, start/end (YYYY-MM-DD, inclusive, in the hotel's
    time zone), q (summary, actor or action), reservation (id: the reservation and everything it owns)."""
    qs = scoped(property).select_related("actor", "undone_by", "property")
    if value := params.get("action"):
        qs = qs.filter(action=value)
    if value := params.get("app"):
        qs = qs.filter(action__startswith=f"{value}.")
    if value := params.get("source"):
        sources = [item for item in str(value).split(",") if item]
        qs = qs.filter(source__in=sources)
    if value := params.get("actor"):
        if value == "none":
            qs = qs.filter(actor__isnull=True)
        else:
            qs = qs.filter(actor_id=value)
    if value := params.get("target_type"):
        qs = qs.filter(target_type=value)
    if value := params.get("target_id"):
        qs = qs.filter(target_id=value)
    if params.get("reversible") in {"1", "true"}:
        qs = qs.filter(reversible=True)
    undone = params.get("undone")
    if undone in {"1", "true"}:
        qs = qs.filter(undone_at__isnull=False)
    elif undone in {"0", "false"}:
        qs = qs.filter(undone_at__isnull=True)
    zone = ZoneInfo(property.timezone or "America/Bogota")
    if value := params.get("start"):
        start = datetime.combine(_parse_day(value, "start"), time.min, tzinfo=zone)
        qs = qs.filter(created_at__gte=start)
    if value := params.get("end"):
        end = datetime.combine(_parse_day(value, "end") + timedelta(days=1), time.min, tzinfo=zone)
        qs = qs.filter(created_at__lt=end)
    if value := (params.get("q") or "").strip():
        qs = qs.filter(
            Q(summary__icontains=value) | Q(actor_label__icontains=value) | Q(action__icontains=value)
        )
    if value := params.get("reservation"):
        from apps.bookings.models import Reservation

        reservation = (
            Reservation.objects.filter(pk=value, property=property).first() if _is_uuid(value) else None
        )
        if reservation is None:
            return qs.none()
        owned = reservation_filter(reservation)
        # …plus the "Deshizo: …" events that undid any of them
        owned_ids = (
            scoped(property).filter(owned).annotate(sid=Cast("id", output_field=CharField())).values("sid")
        )
        qs = qs.filter(owned | Q(action="core.undo", target_type="core.auditevent", target_id__in=owned_ids))
    return qs.order_by("-created_at", "-id")


def _is_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


# ---- Serialization ---------------------------------------------------------------------------------------


def _user_ref(user) -> dict | None:
    if user is None:
        return None
    return {"id": str(user.pk), "email": user.email, "name": user.full_name or user.email}


def undoable(event) -> bool:
    return bool(event.reversible and event.undone_at is None and event.action in core_audit._UNDO_HANDLERS)


def serialize(event, *, link: str = "") -> dict:
    return {
        "id": str(event.pk),
        "created_at": event.created_at,
        "action": event.action,
        "app": event.action.split(".", 1)[0],
        "source": event.source,
        "actor": _user_ref(event.actor),
        "actor_label": event.actor_label,
        "summary": event.summary,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "target_link": link,
        "scope": "property" if event.property_id else "organization",
        "property": {"id": str(event.property_id), "name": event.property.name}
        if event.property_id
        else None,
        "has_changes": bool(event.changes),
        "reversible": event.reversible,
        "undoable": undoable(event),
        "undone_at": event.undone_at,
        "undone_by": _user_ref(event.undone_by),
    }


def serialize_page(events) -> list[dict]:
    events = list(events)
    links = resolve_links(events)
    return [serialize(event, link=links.get(str(event.pk), "")) for event in events]


def _is_diff(changes: dict) -> bool:
    return bool(changes) and all(isinstance(value, list) and len(value) == 2 for value in changes.values())


def _row_changes(undo_data: dict) -> list[dict]:
    """Per-row before/after from an `undo_data["rows"]` snapshot (e.g. the nights of a rate edit)."""
    rows = undo_data.get("rows") if isinstance(undo_data, dict) else None
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows[:MAX_ROW_CHANGES]:
        if not isinstance(row, dict) or "after" not in row:
            continue
        before = row.get("before") or {}
        after = row.get("after") or {}
        if not isinstance(before, dict) or not isinstance(after, dict):
            continue
        fields = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
        if not before:  # a new row: its empty/false fields are not changes worth showing
            fields = [key for key in fields if after.get(key) not in (None, False, "", [], {})]
        result.append(
            {
                "label": str(row.get("date") or row.get("label") or row.get("id") or ""),
                "created": not row.get("before"),
                "changes": [
                    {"field": key, "before": before.get(key), "after": after.get(key)} for key in fields
                ],
            }
        )
    return result


def detail(property, pk) -> dict:
    event = scoped(property).select_related("actor", "undone_by", "property").filter(pk=pk).first()
    if event is None:
        raise NotFoundError("Evento de auditoría no encontrado")
    link = resolve_links([event]).get(str(event.pk), "")
    changes = scrub(event.changes or {})
    diff = []
    details = []
    if _is_diff(changes):
        diff = [{"field": key, "before": value[0], "after": value[1]} for key, value in changes.items()]
    else:
        details = [{"field": key, "value": value} for key, value in changes.items()]
    rows = scrub(_row_changes(event.undo_data or {}))
    undo_event = None
    if event.undone_at:
        undo = (
            scoped(property)
            .filter(action="core.undo", target_type="core.auditevent", target_id=str(event.pk))
            .order_by("-created_at")
            .first()
        )
        undo_event = str(undo.pk) if undo else None
    original = None
    if event.action == "core.undo" and event.target_type == "core.auditevent":
        original = event.target_id
    return {
        **serialize(event, link=link),
        "changes": changes,
        "diff": diff,
        "details": details,
        "row_changes": rows,
        "row_changes_total": len((event.undo_data or {}).get("rows") or [])
        if isinstance(event.undo_data, dict)
        else 0,
        "request_id": event.request_id,
        "undo_event_id": undo_event,
        "original_event_id": original,
    }


def facets(property) -> dict:
    """Values to fill the timeline filters (actions, apps, sources and people seen in this scope)."""
    qs = scoped(property)
    actions = list(qs.values("action").annotate(count=Count("id")).order_by("action"))
    sources = list(qs.values("source").annotate(count=Count("id")).order_by("source"))
    actors = [
        {
            "id": str(row["actor"]),
            "name": row["actor__full_name"] or row["actor__email"],
            "email": row["actor__email"],
        }
        for row in qs.filter(actor__isnull=False)
        .values("actor", "actor__full_name", "actor__email")
        .annotate(count=Count("id"))
        .order_by("actor__full_name", "actor__email")
    ]
    apps = {}
    for row in actions:
        app = row["action"].split(".", 1)[0]
        apps[app] = apps.get(app, 0) + row["count"]
    return {
        "actions": actions,
        "apps": [{"app": app, "count": count} for app, count in sorted(apps.items())],
        "sources": sources,
        "actors": actors,
        "total": sum(row["count"] for row in actions),
    }


# ---- Undo ------------------------------------------------------------------------------------------------


def undo(property, pk, *, actor, confirm: bool) -> dict:
    """`core.audit.undo` with the control center's safeguards: explicit confirmation, the event must be in the
    property's scope, and the most recent change of the same object goes first."""
    if not confirm:
        raise ConfirmationRequired("Confirma que quieres deshacer esta acción (confirm: true)")
    event = scoped(property).filter(pk=pk).first()
    if event is None:
        raise NotFoundError("Evento de auditoría no encontrado")
    if event.reversible and event.undone_at is None and event.target_type and event.target_id:
        newer = (
            scoped(property)
            .filter(
                target_type=event.target_type,
                target_id=event.target_id,
                reversible=True,
                undone_at__isnull=True,
                created_at__gt=event.created_at,
            )
            .exclude(pk=event.pk)
            .order_by("-created_at")
            .first()
        )
        if newer is not None:
            raise UndoConflict(
                "Hay un cambio más reciente sobre este mismo objeto: deshaz primero ese cambio",
                newer_event_id=str(newer.pk),
            )
    try:
        core_audit.undo(event, actor=actor)
    except ObjectDoesNotExist:
        raise ConflictError(
            "El objeto de esta acción ya no existe; no se puede deshacer", code="undo_target_missing"
        ) from None
    return detail(property, event.pk)
