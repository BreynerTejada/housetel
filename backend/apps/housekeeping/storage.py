"""Private storage for maintenance-ticket photos.

Damage photos can show guests' belongings, so they never live under MEDIA_ROOT (served without authentication
at /media/): they go to `settings.PRIVATE_MEDIA_ROOT` when defined, otherwise to a sibling of MEDIA_ROOT
named `<media>-private` (the same private root as guest documents). They have no public URL; the only way to
read one is `GET /api/v1/housekeeping/ticket-photos/<id>/file/` (authenticated, property-scoped).
"""

import os
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage


def private_media_root() -> Path:
    configured = getattr(settings, "PRIVATE_MEDIA_ROOT", None)
    if configured:
        return Path(configured)
    media = Path(settings.MEDIA_ROOT)
    return media.with_name(f"{media.name}-private")


class PrivateMediaStorage(FileSystemStorage):
    """FileSystemStorage rooted at `private_media_root()` (read on every use, so settings overrides apply in
    tests) and without a base URL (`url()` raises)."""

    @property
    def base_location(self):
        return str(private_media_root())

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None

    def _save(self, name, content):
        root = Path(self.location)
        root.mkdir(parents=True, exist_ok=True)
        marker = root / ".gitignore"  # the development root sits inside the repository's bind mount
        if not marker.exists():
            marker.write_text("*\n")
        return super()._save(name, content)


def ticket_photo_upload_to(instance, filename: str) -> str:
    """Random name per property; the original file name is not kept."""
    suffix = Path(filename).suffix.lower()
    return f"ticket-photos/{instance.ticket.property_id}/{uuid.uuid4().hex}{suffix}"
