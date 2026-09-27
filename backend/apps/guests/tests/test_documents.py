"""Identity documents are private: stored outside MEDIA_ROOT (never served by /media/), with random names,
only images or PDFs, and only reachable through the authenticated, organization-scoped file endpoint."""

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.tests.factories import OrganizationFactory, PropertyFactory
from apps.guests.services import add_document
from apps.guests.tests.factories import GuestFactory

pytestmark = pytest.mark.django_db

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PDF = b"%PDF-1.7\n" + b"0" * 64


@pytest.fixture(autouse=True)
def private_media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    return settings.PRIVATE_MEDIA_ROOT


def upload(content=PNG, name="Cédula Juan Pérez.png"):
    return SimpleUploadedFile(name, content)


class TestStorage:
    def test_files_live_outside_the_public_media_root_with_random_names(self, organization, settings):
        document = add_document(GuestFactory(organization=organization), kind="id_front", file=upload())

        path = Path(document.file.path)
        assert path.is_relative_to(settings.PRIVATE_MEDIA_ROOT)
        assert not path.is_relative_to(settings.MEDIA_ROOT)
        assert "Juan" not in document.file.name and "dula" not in document.file.name
        assert path.read_bytes() == PNG
        assert path.suffix == ".png"

    def test_the_private_root_is_kept_out_of_version_control(self, organization, private_media):
        # backend/ is a bind mount of the repository: identity documents must never be committed.
        add_document(GuestFactory(organization=organization), kind="id_front", file=upload())
        assert (Path(private_media) / ".gitignore").read_text().strip() == "*"

    def test_files_have_no_public_url(self, organization):
        document = add_document(GuestFactory(organization=organization), kind="id_front", file=upload())
        with pytest.raises(ValueError):
            document.file.url  # noqa: B018 — the property itself must refuse

    @pytest.mark.parametrize(("content", "suffix"), [(JPEG, ".jpg"), (PDF, ".pdf"), (PNG, ".png")])
    def test_accepts_images_and_pdfs_whatever_the_file_name_says(self, organization, content, suffix):
        document = add_document(
            GuestFactory(organization=organization), kind="other", file=upload(content, name="scan.bin")
        )
        assert document.file.name.endswith(suffix)

    @pytest.mark.parametrize(
        "content", [b"<html><script>alert(1)</script></html>", b"<svg onload=alert(1)>", b"GIF89a....", b""]
    )
    def test_rejects_anything_else(self, organization, content):
        from apps.core.errors import DomainError

        with pytest.raises(DomainError) as exc:
            add_document(GuestFactory(organization=organization), kind="other", file=upload(content, "x.png"))
        assert exc.value.code == "invalid_file_type"

    def test_rejects_files_over_10_mb(self, organization):
        from apps.core.errors import DomainError

        big = upload(PNG + b"0" * (10 * 1024 * 1024))
        with pytest.raises(DomainError) as exc:
            add_document(GuestFactory(organization=organization), kind="other", file=big)
        assert exc.value.code == "file_too_large"


def file_url(document):
    return f"/api/v1/guests/documents/{document.pk}/file/"


class TestFileEndpoint:
    def test_member_downloads_the_file_with_safe_headers(self, api, organization):
        document = add_document(GuestFactory(organization=organization), kind="id_front", file=upload())

        response = api.get(file_url(document))

        assert response.status_code == 200
        assert b"".join(response.streaming_content) == PNG
        assert response["Content-Type"] == "image/png"
        assert response["X-Content-Type-Options"] == "nosniff"
        assert "no-store" in response["Cache-Control"]
        assert response["Content-Disposition"].startswith("inline")

    def test_download_flag_makes_it_an_attachment(self, api, organization):
        document = add_document(GuestFactory(organization=organization), kind="passport", file=upload(PDF))
        response = api.get(file_url(document), {"download": "1"})
        assert response["Content-Disposition"].startswith("attachment")
        assert response["Content-Type"] == "application/pdf"

    def test_documents_of_another_organization_are_not_found(self, api):
        stranger = GuestFactory(organization=OrganizationFactory())
        document = add_document(stranger, kind="id_front", file=upload())
        assert api.get(file_url(document)).status_code == 404

    def test_needs_the_guests_view_permission(self, api_for, make_member, prop, organization):
        document = add_document(GuestFactory(organization=organization), kind="id_front", file=upload())
        housekeeper = make_member("housekeeping")
        response = api_for(housekeeper, prop).get(file_url(document))
        assert (response.status_code, response.json()["permission"]) == (403, "guests.view")

    def test_restricted_member_of_another_property_of_the_chain_still_sees_org_guests(
        self, api_for, make_member, prop, organization
    ):
        other = PropertyFactory(organization=organization)
        clerk = make_member("front_desk", properties=[other])
        document = add_document(GuestFactory(organization=organization), kind="id_front", file=upload())
        assert api_for(clerk, other).get(file_url(document)).status_code == 200

    def test_anonymous_and_headerless_requests_are_refused(self, public_api, api, owner, organization):
        document = add_document(GuestFactory(organization=organization), kind="id_front", file=upload())
        assert public_api.get(file_url(document)).status_code == 401
        public_api.force_authenticate(owner)
        assert public_api.get(file_url(document)).json()["code"] == "property_required"
