"""Private storage for legal documents (invoice PDF/XML, SIRE files).

Invoices carry the customer's name and identity document; SIRE files carry passport numbers. `/media/` is
served without authentication (DEBUG helper), so these files live OUTSIDE MEDIA_ROOT, like the guest identity
documents: `settings.PRIVATE_MEDIA_ROOT` when defined, otherwise `<MEDIA_ROOT>-private`. They have no public
URL (`storage.url()` raises); staff read them through `/api/v1/compliance/...` and guests through the signed
portal link (`/api/v1/public/compliance/portal/<token>/invoices/<id>/pdf/`).
"""

import os
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage


def private_root() -> Path:
    configured = getattr(settings, "PRIVATE_MEDIA_ROOT", None)
    if configured:
        return Path(configured)
    media = Path(settings.MEDIA_ROOT)
    return media.with_name(f"{media.name}-private")


class ComplianceStorage(FileSystemStorage):
    """FileSystemStorage rooted at `private_root()` (read on every use, so settings overrides apply), without
    a base URL."""

    @property
    def base_location(self):
        return str(private_root())

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None

    def _save(self, name, content):
        root = Path(self.location)
        root.mkdir(parents=True, exist_ok=True)
        marker = root / ".gitignore"
        if not marker.exists():  # the development root sits inside the repository's bind mount
            marker.write_text("*\n")
        return super()._save(name, content)


def invoice_upload_to(instance, filename: str) -> str:
    return f"compliance/{instance.property_id}/invoices/{filename}"


def sire_upload_to(instance, filename: str) -> str:
    return f"compliance/{instance.property_id}/sire/{filename}"
