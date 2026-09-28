"""Bookings of pull-based channels (plan C3 › Entrada): Channex publishes booking revisions in a feed that
the PMS reads and acknowledges (`GET /booking_revisions/feed` + `POST /booking_revisions/:id/ack`); the
simulated Channex keeps the bookings made in the OTA simulator until they are pulled the same way.

Each revision goes through `importer.import_booking` (idempotent). Only revisions the PMS applied (or that
changed nothing) are acknowledged: a failed one stays in the feed and comes back on the next pull, while its
`channel_import_failed` alert tells the staff what to fix. Automation `distribution.pull_bookings`.
"""

from collections import Counter

from django.utils import timezone

from apps.core import alerts, integrations
from apps.distribution.errors import ChannelError
from apps.distribution.models import ChannelConnection, SyncLog
from apps.distribution.services.importer import import_booking
from apps.distribution.services.logs import log

PULL_CHANNELS = (ChannelConnection.Channel.CHANNEX,)
ACTIONS = ("created", "modified", "cancelled", "unchanged", "ignored", "failed")


def pull_bookings(property, *, connection=None, actor=None) -> dict:
    """Pull and apply the pending bookings of the property's pull-based connections (or only `connection`);
    returns the counts per action plus `acknowledged`, `errors` (feeds that could not be read) and
    `connections`."""
    summary = Counter({key: 0 for key in (*ACTIONS, "acknowledged", "errors")})
    connections = ChannelConnection.objects.filter(property=property, channel_code__in=PULL_CHANNELS).exclude(
        status=ChannelConnection.Status.PAUSED
    )
    if connection is not None:
        connections = connections.filter(pk=connection.pk)
    connections = list(connections.select_related("property"))
    if not connections:
        return dict(summary, connections=0)
    if not integrations.get_setting(property, "channel_channex").enabled:
        return dict(summary, connections=0, disabled=True)
    from apps.distribution.providers import provider_for

    for conn in connections:
        provider = provider_for(conn)
        try:
            bookings = provider.fetch_bookings(conn)
        except ChannelError as exc:
            summary["errors"] += 1
            _pull_failed(conn, exc.message)
            continue
        alerts.resolve_alert(conn.property, _dedupe(conn))
        for booking in bookings:
            result = import_booking(conn, booking, actor=actor)
            summary[result.action] += 1
            if result.action == "failed":  # not acknowledged: the channel keeps offering it
                if hasattr(provider, "reject"):
                    provider.reject(conn, booking, result.message)
                continue
            try:
                provider.acknowledge(conn, booking)
                summary["acknowledged"] += 1
            except ChannelError as exc:
                log(
                    conn,
                    SyncLog.Direction.IN,
                    "booking_ack",
                    SyncLog.Status.WARNING,
                    f"La reserva {booking.external_id} se aplicó pero no se pudo confirmar al canal: "
                    f"{exc.message}",
                    external_id=booking.external_id,
                    reservation=result.reservation,
                )
        ChannelConnection.objects.filter(pk=conn.pk).update(last_sync_at=timezone.now())
    return dict(summary, connections=len(connections))


def _dedupe(connection) -> str:
    return f"distribution:pull:{connection.pk}"


def _pull_failed(connection, message: str) -> None:
    log(
        connection,
        SyncLog.Direction.IN,
        "booking_pull",
        SyncLog.Status.ERROR,
        f"No se pudieron descargar las reservas: {message}",
    )
    alerts.raise_alert(
        property=connection.property,
        kind="channel_pull_failed",
        severity="warning",
        title=f"No se pudieron descargar las reservas de {connection.name}",
        message=(
            f"{message}. Las reservas nuevas, modificadas o canceladas en el canal no están llegando al PMS; "
            "se reintentará en la próxima descarga."
        ),
        link="/app/channels",
        dedupe_key=_dedupe(connection),
        data={"connection_id": str(connection.pk), "error": message},
        source="distribution",
    )
