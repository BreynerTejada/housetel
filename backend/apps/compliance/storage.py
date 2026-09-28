"""Private storage for legal documents (invoice PDF/XML, SIRE files).

Invoices carry the customer's name and identity document; SIRE files carry passport numbers. `/media/` is
served without authentication (DEBUG helper), so these files live OUTSIDE MEDIA_ROOT, like the guest identity
documents: the `private` storage of `settings.STORAGES` (`apps.core.storage`, plan P1) — local disk at
`settings.PRIVATE_MEDIA_ROOT` or `<MEDIA_ROOT>-private`, or a private S3-compatible bucket. They have no
public URL (`storage.url()` raises); staff read them through `/api/v1/compliance/...` and guests through the
signed portal link (`/api/v1/public/compliance/portal/<token>/invoices/<id>/pdf/`).
"""

from apps.core.storage import PrivateStorage
from apps.core.storage import private_media_root as private_root  # noqa: F401 - kept for callers


class ComplianceStorage(PrivateStorage):
    """The `private` storage (P-INT: S3-capable). The class name stays: migrations reference it."""


def invoice_upload_to(instance, filename: str) -> str:
    return f"compliance/{instance.property_id}/invoices/{filename}"


def sire_upload_to(instance, filename: str) -> str:
    return f"compliance/{instance.property_id}/sire/{filename}"
