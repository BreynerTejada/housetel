"""Private storage for guest identity documents (ID photos, passports, signatures).

`config/urls.py` serves everything under MEDIA_ROOT at /media/ without authentication (DEBUG helper), so
these files live OUTSIDE it: `settings.PRIVATE_MEDIA_ROOT` when defined, otherwise a sibling of MEDIA_ROOT
named `<media>-private` (`backend/media-private/` in development). They have no public URL at all
(`storage.url()` raises); the only way to read one is `GET /api/v1/guests/documents/<id>/file/`
(authenticated, organization-scoped, `guests.view`).
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


class PrivateDocumentStorage(FileSystemStorage):
    """FileSystemStorage rooted at `private_media_root()` (read on every use, so settings overrides apply)
    and without a base URL."""

    @property
    def base_location(self):
        return str(private_media_root())

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None  # FileSystemStorage.url() raises "This file is not accessible via a URL."

    def _save(self, name, content):
        self._keep_out_of_version_control()
        return super()._save(name, content)

    def _keep_out_of_version_control(self) -> None:
        """In development the root sits inside the repository's bind mount (`backend/`): a `.gitignore` that
        ignores everything keeps identity documents from ever being committed."""
        root = Path(self.location)
        root.mkdir(parents=True, exist_ok=True)
        marker = root / ".gitignore"
        if not marker.exists():
            marker.write_text("*\n")


def document_upload_to(instance, filename: str) -> str:
    """Random name per organization: the original file name (often "cedula-juan-perez.jpg") is not kept."""
    suffix = Path(filename).suffix.lower()
    return f"guest-documents/{instance.guest.organization_id}/{uuid.uuid4().hex}{suffix}"
