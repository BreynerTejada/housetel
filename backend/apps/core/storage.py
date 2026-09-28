"""Private file storage (plan P1): identity documents, signatures, damage photos, invoices, SIRE files.

Two storages live in `settings.STORAGES`:
- `default`: public media (room photos, logos, booking-engine images), served at `/media/...`;
- `private`: files that only authenticated API views may stream (`FieldFile.open("rb")`); they never have a
  public URL. Local disk outside MEDIA_ROOT by default (`LocalPrivateStorage`: `PRIVATE_MEDIA_ROOT` or
  `<MEDIA_ROOT>-private`), a private S3-compatible bucket/prefix when `AWS_STORAGE_BUCKET_NAME` is set.

Model fields use `PrivateStorage()`, a proxy that resolves the `private` alias on every call, so the backend
follows the settings (and test overrides) and the field deconstructs the same in migrations whatever the
backend is. The apps' own storage classes (`guests.storage.PrivateDocumentStorage`,
`housekeeping.storage.PrivateMediaStorage`, `compliance.storage.ComplianceStorage`) become S3-capable by
subclassing it (see docs/integration-notes/P1-production.md).
"""

import os
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage, Storage, storages
from django.utils.deconstruct import deconstructible

PRIVATE_ALIAS = "private"


def private_media_root() -> Path:
    """`PRIVATE_MEDIA_ROOT`, or a sibling of MEDIA_ROOT named `<media>-private` (never under MEDIA_ROOT)."""
    configured = getattr(settings, "PRIVATE_MEDIA_ROOT", None)
    if configured:
        return Path(configured)
    media = Path(settings.MEDIA_ROOT)
    return media.with_name(f"{media.name}-private")


class LocalPrivateStorage(FileSystemStorage):
    """FileSystemStorage rooted at `private_media_root()` (read on every use, so settings overrides apply) and
    without a base URL (`url()` raises "This file is not accessible via a URL.")."""

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
        marker = root / ".gitignore"  # in development the root sits inside the repository's bind mount
        if not marker.exists():
            marker.write_text("*\n")
        return super()._save(name, content)


def private_storage() -> Storage:
    """The configured private storage backend (`settings.STORAGES["private"]`)."""
    return storages[PRIVATE_ALIAS]


@deconstructible
class PrivateStorage(Storage):
    """Proxy to `private_storage()`. Private files have no URL: `url()` raises ValueError, like
    FileSystemStorage without a base URL; read them with `open("rb")` inside an authorized view."""

    @property
    def backend(self) -> Storage:
        return private_storage()

    def open(self, name, mode="rb"):
        return self.backend.open(name, mode)

    def save(self, name, content, max_length=None):
        return self.backend.save(name, content, max_length=max_length)

    def _open(self, name, mode="rb"):
        return self.backend.open(name, mode)

    def _save(self, name, content):
        return self.backend.save(name, content)

    def delete(self, name):
        return self.backend.delete(name)

    def exists(self, name):
        return self.backend.exists(name)

    def listdir(self, path):
        return self.backend.listdir(path)

    def size(self, name):
        return self.backend.size(name)

    def path(self, name):
        return self.backend.path(name)  # local disk only; S3 raises NotImplementedError

    def url(self, name):
        raise ValueError("This file is not accessible via a URL.")

    def get_valid_name(self, name):
        return self.backend.get_valid_name(name)

    def get_alternative_name(self, file_root, file_ext):
        return self.backend.get_alternative_name(file_root, file_ext)

    def get_available_name(self, name, max_length=None):
        return self.backend.get_available_name(name, max_length=max_length)

    def generate_filename(self, filename):
        return self.backend.generate_filename(filename)

    def get_accessed_time(self, name):
        return self.backend.get_accessed_time(name)

    def get_created_time(self, name):
        return self.backend.get_created_time(name)

    def get_modified_time(self, name):
        return self.backend.get_modified_time(name)
