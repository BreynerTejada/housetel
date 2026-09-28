"""Sync log helper: every exchange with a channel leaves one `SyncLog` row."""

from apps.distribution.models import SyncLog


def log(
    connection,
    direction: str,
    kind: str,
    status: str,
    message: str = "",
    *,
    payload: dict | None = None,
    external_id: str = "",
    reservation=None,
) -> SyncLog:
    return SyncLog.objects.create(
        connection=connection,
        direction=direction,
        kind=kind,
        status=status,
        message=message[:4000],
        payload=payload or {},
        external_id=(external_id or "")[:120],
        reservation=reservation,
    )
