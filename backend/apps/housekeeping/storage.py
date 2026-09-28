"""Private storage for maintenance-ticket photos.

Damage photos can show guests' belongings, so they never live under MEDIA_ROOT (served without authentication
at /media/): they go to the `private` storage of `settings.STORAGES` (`apps.core.storage`, plan P1) — local
disk at `settings.PRIVATE_MEDIA_ROOT` or `<media>-private` (the same private root as guest documents), or a
private S3-compatible bucket. They have no public URL; the only way to read one is
`GET /api/v1/housekeeping/ticket-photos/<id>/file/` (authenticated, property-scoped).
"""

import uuid
from pathlib import Path

from apps.core.storage import PrivateStorage
from apps.core.storage import private_media_root as private_media_root  # noqa: F401 - kept for callers


class PrivateMediaStorage(PrivateStorage):
    """The `private` storage (P-INT: S3-capable). The class name stays: migrations reference it."""


def ticket_photo_upload_to(instance, filename: str) -> str:
    """Random name per property; the original file name is not kept."""
    suffix = Path(filename).suffix.lower()
    return f"ticket-photos/{instance.ticket.property_id}/{uuid.uuid4().hex}{suffix}"
