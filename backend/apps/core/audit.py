"""Audit trail + generic undo. Contract (spec §4.2):

record(*, action, target=None, summary="", actor=None, source="user", changes=None,
       reversible=False, undo_data=None, property=None, organization=None, actor_label=None) -> AuditEvent
register_undo(action, handler)        # handler(event) reverts the change
undo(event, *, actor) -> AuditEvent   # returns the original event, now marked undone
"""

from collections.abc import Callable

from django.db import transaction
from django.utils import timezone

from apps.core.context import current_request_id
from apps.core.errors import ConflictError
from apps.core.models import AuditEvent, Organization, Property

SOURCE_LABELS = {
    "user": "Usuario",
    "automation": "Automatización",
    "ai": "IA",
    "channel": "Canal",
    "guest": "Huésped",
    "system": "Sistema",
    "api": "API",
}

_UNDO_HANDLERS: dict[str, Callable[[AuditEvent], None]] = {}


class UndoError(ConflictError):
    code = "undo_error"


def _target_reference(target) -> tuple[str, str]:
    if target is None:
        return "", ""
    meta = getattr(target, "_meta", None)
    if meta is None:
        return type(target).__name__.lower(), str(getattr(target, "pk", "") or "")
    return f"{meta.app_label}.{meta.model_name}", str(target.pk)


def _tenant_of(target, property, organization):
    if property is None:
        if isinstance(target, Property):
            property = target
        else:
            candidate = getattr(target, "property", None)
            property = candidate if isinstance(candidate, Property) else None
    if organization is None:
        if property is not None:
            organization = property.organization
        elif isinstance(target, Organization):
            organization = target
        else:
            candidate = getattr(target, "organization", None)
            organization = candidate if isinstance(candidate, Organization) else None
    return property, organization


def record(
    *,
    action,
    target=None,
    summary="",
    actor=None,
    source="user",
    changes=None,
    reversible=False,
    undo_data=None,
    property=None,
    organization=None,
    actor_label=None,
) -> AuditEvent:
    user = actor if actor is not None and getattr(actor, "is_authenticated", False) else None
    property, organization = _tenant_of(target, property, organization)
    target_type, target_id = _target_reference(target)
    if actor_label is None:
        actor_label = user.email if user is not None else SOURCE_LABELS.get(source, source)
    return AuditEvent.objects.create(
        organization=organization,
        property=property,
        actor=user,
        actor_label=actor_label[:200],
        source=source,
        action=action,
        target_type=target_type,
        target_id=target_id,
        summary=summary,
        changes=changes or {},
        reversible=reversible,
        undo_data=undo_data or {},
        request_id=current_request_id()[:64],
    )


def register_undo(action: str, handler: Callable[[AuditEvent], None]) -> None:
    _UNDO_HANDLERS[action] = handler


def undo(event, *, actor) -> AuditEvent:
    if not event.reversible:
        raise UndoError("Esta acción no se puede deshacer", code="not_reversible")
    handler = _UNDO_HANDLERS.get(event.action)
    if handler is None:
        raise UndoError("Esta acción no tiene forma de deshacerse", code="undo_not_supported")
    with transaction.atomic():
        locked = AuditEvent.objects.select_for_update().get(pk=event.pk)
        if locked.undone_at is not None:
            raise UndoError("La acción ya fue deshecha", code="already_undone")
        handler(locked)
        locked.undone_at = timezone.now()
        locked.undone_by = actor
        locked.save(update_fields=["undone_at", "undone_by", "updated_at"])
        record(
            action="core.undo",
            target=locked,
            summary=f"Deshizo: {locked.summary or locked.action}",
            actor=actor,
            property=locked.property,
            organization=locked.organization,
            changes={"undone_action": locked.action},
        )
    return locked


def diff(before: dict, after: dict) -> dict:
    """{"field": [before, after]} for every key whose value changed."""
    keys = dict.fromkeys([*before, *after])
    return {key: [before.get(key), after.get(key)] for key in keys if before.get(key) != after.get(key)}
