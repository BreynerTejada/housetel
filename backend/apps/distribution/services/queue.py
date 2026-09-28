"""ARI queue (plan C3 › Salida).

Receivers of `inventory_changed` / `rates_changed` call `enqueue_ari`: one pending `AriUpdate` per
(connection, category) accumulates the union of the changed ranges and kinds (coalescing), and a Celery push
is scheduled `PUSH_COUNTDOWN` seconds later (debounce: every change of those seconds travels in the same
push). The values themselves are computed when the push runs (`services.ari`), so they are always the current
ones.

Ranges are half-open `[start, end)` and clamped to the sync window `[business_date, business_date + 365)`.
"""

import logging
from collections import defaultdict
from datetime import date, timedelta

from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core import alerts, audit
from apps.core.errors import ConflictError, DomainError
from apps.distribution.models import AriUpdate, ChannelConnection, SyncLog
from apps.distribution.services.logs import log

logger = logging.getLogger("housetel.distribution")

ARI_KINDS = ("availability", "rates", "restrictions")
RATE_KINDS = frozenset({"rates", "restrictions"})
PUSH_CHANNELS = (
    ChannelConnection.Channel.BOOKSIM,
    ChannelConnection.Channel.AIRSIM,
    ChannelConnection.Channel.CHANNEX,
)
HORIZON_DAYS = 365
PUSH_COUNTDOWN = 5  # seconds
MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 30  # 30 s, 2 min, 8 min, then every 30 min
BACKOFF_CAP_SECONDS = 30 * 60
STALE_SENDING = timedelta(minutes=10)
CLAIM_LIMIT = 500
KIND_LABELS = {"availability": "disponibilidad", "rates": "tarifas", "restrictions": "restricciones"}


def sync_window(property, start: date | None = None, end: date | None = None) -> tuple[date, date] | None:
    """`[start, end)` clamped to `[business_date, business_date + HORIZON_DAYS)`; None when nothing is left
    (an open end means the whole horizon)."""
    today = property.business_date
    horizon_end = today + timedelta(days=HORIZON_DAYS)
    start = max(start or today, today)
    end = min(end or horizon_end, horizon_end)
    return (start, end) if start < end else None


def enqueue_ari(
    property,
    *,
    room_type_ids=None,
    start=None,
    end=None,
    kinds=ARI_KINDS,
    rate_plan_ids=None,
    connection=None,
    schedule=True,
) -> list[AriUpdate]:
    """Queue the ARI of the changed categories (None = every mapped category) for every active push
    connection of the property (or only `connection`) and schedule the debounced push (`schedule=False` when
    the caller sends the queue itself, like `full_sync`).

    A pure rates change (`kinds` without availability) of plans no connection maps is ignored. iCal
    connections are pull-based and paused connections are skipped (resuming does a full sync)."""
    window = sync_window(property, start, end)
    if window is None:
        return []
    kinds = sorted(set(kinds))
    wanted_types = {str(pk) for pk in room_type_ids} if room_type_ids else None
    wanted_plans = {str(pk) for pk in rate_plan_ids} if rate_plan_ids else None
    connections = (
        ChannelConnection.objects.filter(property=property, channel_code__in=PUSH_CHANNELS)
        .exclude(status=ChannelConnection.Status.PAUSED)
        .prefetch_related("room_mappings", "rate_mappings")
    )
    if connection is not None:
        connections = connections.filter(pk=connection.pk)

    touched = []
    for conn in connections:
        if wanted_plans is not None and set(kinds) <= RATE_KINDS:
            mapped_plans = {str(m.rate_plan_id) for m in conn.rate_mappings.all() if m.rate_plan_id}
            if not mapped_plans & wanted_plans:
                continue
        type_ids = {str(mapping.room_type_id) for mapping in conn.room_mappings.all()}
        if wanted_types is not None:
            type_ids &= wanted_types
        for type_id in sorted(type_ids):
            touched.append(_coalesce(conn, type_id, window, kinds))
    if touched and schedule:
        schedule_push(property)
    return touched


def _coalesce(connection, room_type_id, window, kinds) -> AriUpdate:
    """Extend the pending update of (connection, category) or create it. A row locked by a push in progress
    is skipped (never waited for): the change then gets a new pending row."""
    start, end = window
    with transaction.atomic():
        row = (
            AriUpdate.objects.select_for_update(skip_locked=True)
            .filter(connection=connection, room_type_id=room_type_id, status=AriUpdate.Status.PENDING)
            .order_by("created_at")
            .first()
        )
        if row is None:
            return AriUpdate.objects.create(
                property_id=connection.property_id,
                connection=connection,
                room_type_id=room_type_id,
                start=start,
                end=end,
                kinds=kinds,
            )
        row.start, row.end = min(row.start, start), max(row.end, end)
        row.kinds = sorted(set(row.kinds) | set(kinds))
        row.save(update_fields=["start", "end", "kinds", "updated_at"])
        return row


def schedule_push(property) -> None:
    """Schedule one push of the property's queue `PUSH_COUNTDOWN` seconds after the current transaction
    commits; further calls within that window are absorbed (debounce)."""
    if not cache.add(f"distribution:push-scheduled:{property.pk}", 1, timeout=PUSH_COUNTDOWN):
        return
    from apps.distribution.tasks import push_ari_queue

    property_id = str(property.pk)
    transaction.on_commit(lambda: push_ari_queue.apply_async(args=[property_id], countdown=PUSH_COUNTDOWN))


# --- push ---------------------------------------------------------------------------------------------------


def backoff(attempts: int) -> timedelta:
    """Wait before retrying an update that failed `attempts` times."""
    return timedelta(seconds=min(BACKOFF_BASE_SECONDS * 4 ** (attempts - 1), BACKOFF_CAP_SECONDS))


def process_queue(property=None, *, connection=None, force=False) -> dict:
    """Send the due pending updates (of one property, one connection or all), one provider call per
    connection.

    Claimed rows go `sending` (so new changes open a new pending row instead of waiting for this push);
    rows a crashed push left `sending` for more than 10 minutes are pending again. Success → `sent`;
    failure → back to pending with exponential backoff and, after `MAX_ATTEMPTS` (or a non-retryable
    error), `failed` + the alert `channel_sync_failed` and the connection in `error`. The next successful
    push clears both. `force` ignores the backoff (full sync, "retry now"). Paused connections keep their
    queue."""
    now = timezone.now()
    scope = AriUpdate.objects.all()
    if property is not None:
        scope = scope.filter(property=property)
    if connection is not None:
        scope = scope.filter(connection=connection)
    scope.filter(status=AriUpdate.Status.SENDING, updated_at__lt=now - STALE_SENDING).update(
        status=AriUpdate.Status.PENDING, updated_at=now
    )
    with transaction.atomic():
        due = (
            scope.select_for_update(skip_locked=True, of=("self",))
            .filter(status=AriUpdate.Status.PENDING)
            .exclude(connection__status=ChannelConnection.Status.PAUSED)
        )
        if not force:
            due = due.filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
        claimed = list(due.order_by("created_at")[:CLAIM_LIMIT])
        AriUpdate.objects.filter(pk__in=[row.pk for row in claimed]).update(
            status=AriUpdate.Status.SENDING, updated_at=now
        )
    by_connection = defaultdict(list)
    for row in claimed:
        by_connection[row.connection_id].append(row)
    summary = {"sent": 0, "retrying": 0, "failed": 0, "connections": len(by_connection)}
    for connection_id, rows in by_connection.items():
        conn = (
            ChannelConnection.objects.select_related("property")
            .prefetch_related(
                "room_mappings",
                "rate_mappings__rate_plan__parent",
                "rate_mappings__rate_plan__room_types",
            )
            .get(pk=connection_id)
        )
        _push_connection(conn, rows, summary)
    return summary


def _push_connection(connection, rows, summary) -> None:
    from apps.distribution.providers import provider_for
    from apps.distribution.services.ari import build_batch
    from apps.inventory.models import RoomType

    merged: dict = {}
    for row in rows:
        start, end, kinds = merged.get(row.room_type_id, (row.start, row.end, set()))
        merged[row.room_type_id] = (min(start, row.start), max(end, row.end), kinds | set(row.kinds))
    mapped = {mapping.room_type_id for mapping in connection.room_mappings.all() if not mapping.room_id}
    room_types = RoomType.objects.in_bulk([type_id for type_id in merged if type_id in mapped])
    batches = [
        build_batch(connection, room_types[type_id], start, end, kinds)
        for type_id, (start, end, kinds) in merged.items()
        if type_id in room_types
    ]
    payload = _summary(batches, rows)
    if not batches:  # the categories were unmapped after being queued: nothing to tell the channel
        _mark_sent(rows, payload, {"skipped": "unmapped"})
        summary["sent"] += len(rows)
        return
    try:
        response = provider_for(connection).push_ari(connection, batches)
    except Exception as exc:  # noqa: BLE001 - any failure is retried and recorded, never lost
        if not isinstance(exc, DomainError):
            logger.exception("ARI push failed (connection=%s)", connection.pk)
        _failed_push(connection, rows, exc, payload, summary)
        return
    _mark_sent(rows, payload, response or {})
    summary["sent"] += len(rows)
    connection.last_sync_at = timezone.now()
    connection.last_error = ""
    if connection.status == ChannelConnection.Status.ERROR:
        connection.status = ChannelConnection.Status.ACTIVE
    connection.save(update_fields=["last_sync_at", "last_error", "status", "updated_at"])
    alerts.resolve_alert(connection.property, f"distribution:ari:{connection.pk}")
    warnings = list((response or {}).get("warnings") or [])
    if warnings:  # the channel accepted the call but refused some values (e.g. Channex `meta.warnings`)
        log(
            connection,
            SyncLog.Direction.OUT,
            "ari",
            SyncLog.Status.WARNING,
            f"{_describe(payload)} · el canal rechazó {len(warnings)} valor(es): "
            f"{_warning_text(warnings[0])}",
            payload={**payload, "warnings": warnings[:50]},
        )
        return
    log(connection, SyncLog.Direction.OUT, "ari", SyncLog.Status.SUCCESS, _describe(payload), payload=payload)


def _warning_text(warning) -> str:
    if isinstance(warning, dict):
        return str(warning.get("warning") or warning.get("title") or warning)[:300]
    return str(warning)[:300]


def _mark_sent(rows, payload, response) -> None:
    now = timezone.now()
    for row in rows:
        row.status, row.sent_at, row.attempts = AriUpdate.Status.SENT, now, row.attempts + 1
        row.payload, row.response, row.last_error, row.next_attempt_at = payload, response, "", None
        row.save(
            update_fields=[
                "status",
                "sent_at",
                "attempts",
                "payload",
                "response",
                "last_error",
                "next_attempt_at",
                "updated_at",
            ]
        )


def _failed_push(connection, rows, exc, payload, summary) -> None:
    now = timezone.now()
    message = (getattr(exc, "message", "") or str(exc) or type(exc).__name__)[:1000]
    retryable = getattr(exc, "retryable", True)
    gave_up = False
    for row in rows:
        row.attempts += 1
        row.last_error = message
        if retryable and row.attempts < MAX_ATTEMPTS:
            row.status, row.next_attempt_at = AriUpdate.Status.PENDING, now + backoff(row.attempts)
            summary["retrying"] += 1
        else:
            row.status, row.next_attempt_at = AriUpdate.Status.FAILED, None
            summary["failed"] += 1
            gave_up = True
        row.save(update_fields=["attempts", "last_error", "status", "next_attempt_at", "updated_at"])
    connection.last_error = message
    fields = ["last_error", "updated_at"]
    if gave_up:
        connection.status = ChannelConnection.Status.ERROR
        fields.append("status")
    connection.save(update_fields=fields)
    log(
        connection,
        SyncLog.Direction.OUT,
        "ari",
        SyncLog.Status.ERROR,
        f"No se pudo enviar el ARI: {message}",
        payload={**payload, "attempts": max(row.attempts for row in rows)},
    )
    if gave_up:
        alerts.raise_alert(
            property=connection.property,
            kind="channel_sync_failed",
            severity="critical",
            title=f"No se pudo actualizar {connection.name}",
            message=(
                f"El envío de disponibilidad y tarifas a {connection.name} falló {MAX_ATTEMPTS} veces: "
                f"{message}. El canal puede estar vendiendo con datos viejos: revisa la conexión y haz una "
                "sincronización completa."
            ),
            link="/app/channels",
            dedupe_key=f"distribution:ari:{connection.pk}",
            data={
                "connection_id": str(connection.pk),
                "connection": connection.name,
                "attempts": MAX_ATTEMPTS,
                "error": message,
            },
            source="distribution",
        )


def _summary(batches, rows) -> dict:
    if not batches:
        return {"updates": [str(row.pk) for row in rows], "room_types": []}
    kinds = sorted({kind for batch in batches for kind in batch.kinds})
    return {
        "updates": [str(row.pk) for row in rows],
        "room_types": [batch.room_type_code for batch in batches],
        "start": min(batch.start for batch in batches).isoformat(),
        "end": max(batch.end for batch in batches).isoformat(),
        "kinds": kinds,
        "nights": sum(len(batch.availability) for batch in batches),
        "rates": sorted({rate.external_rate_id for batch in batches for rate in batch.rates}),
    }


def _describe(payload) -> str:
    kinds = ", ".join(KIND_LABELS.get(kind, kind) for kind in payload.get("kinds", []))
    return (
        f"ARI enviado ({kinds}): {', '.join(payload.get('room_types', []))} · "
        f"{payload.get('start')} → {payload.get('end')}"
    )


# --- full sync ----------------------------------------------------------------------------------------------


def full_sync(connection, *, actor=None) -> dict:
    """Send the whole sync window (365 days) of every mapped category now, whatever the channel had."""
    if connection.status == ChannelConnection.Status.PAUSED:
        raise ConflictError("La conexión está pausada: reanúdala para sincronizar", code="connection_paused")
    if connection.channel_code not in PUSH_CHANNELS:
        raise DomainError(
            "Esta conexión no envía ARI: el canal lee el calendario exportado", code="not_supported"
        )
    enqueue_ari(connection.property, connection=connection, kinds=ARI_KINDS, schedule=False)
    summary = process_queue(connection=connection, force=True)
    audit.record(
        action="distribution.full_sync",
        target=connection,
        summary=f"Sincronización completa de {connection.name}",
        actor=actor,
        source="user" if actor is not None else "system",
        property=connection.property,
        changes={"sent": summary["sent"], "failed": summary["failed"], "retrying": summary["retrying"]},
    )
    return summary
