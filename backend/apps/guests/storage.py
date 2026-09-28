"""Private storage for guest identity documents (ID photos, passports, signatures).

`config/urls.py` serves everything under MEDIA_ROOT at /media/ without authentication (DEBUG helper), so
these files live OUTSIDE it, in the `private` storage of `settings.STORAGES` (`apps.core.storage`, plan P1):
local disk at `settings.PRIVATE_MEDIA_ROOT` when defined, otherwise a sibling of MEDIA_ROOT named
`<media>-private` (`backend/media-private/` in development), or a private S3-compatible bucket when
`AWS_STORAGE_BUCKET_NAME` is set. They have no public URL at all (`storage.url()` raises); the only way to
read one is `GET /api/v1/guests/documents/<id>/file/` (authenticated, organization-scoped, `guests.view`).
"""

import uuid
from pathlib import Path

from apps.core.storage import PrivateStorage
from apps.core.storage import private_media_root as private_media_root  # noqa: F401 - kept for callers


class PrivateDocumentStorage(PrivateStorage):
    """The `private` storage (P-INT: S3-capable). The class name stays: migrations reference it."""


def document_upload_to(instance, filename: str) -> str:
    """Random name per organization: the original file name (often "cedula-juan-perez.jpg") is not kept."""
    suffix = Path(filename).suffix.lower()
    return f"guest-documents/{instance.guest.organization_id}/{uuid.uuid4().hex}{suffix}"
