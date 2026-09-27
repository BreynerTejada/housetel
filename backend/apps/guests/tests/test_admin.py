"""Django admin and private guest documents: the storage has no public URL, so the admin shows the stored
name and serves the file only through an admin-protected download view."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import User
from apps.guests.services import add_document
from apps.guests.tests.factories import GuestFactory

pytestmark = pytest.mark.django_db

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


@pytest.fixture(autouse=True)
def private_media(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"


@pytest.fixture
def document(organization):
    guest = GuestFactory(organization=organization)
    return add_document(guest, kind="passport", file=SimpleUploadedFile("pasaporte.png", PNG))


@pytest.fixture
def admin_client(client):
    client.force_login(User.objects.create_superuser("root@example.com", "pass1234"))
    return client


def file_url(document):
    return reverse("admin:guests_guestdocument_file", args=[document.pk])


def test_guest_change_page_with_documents_renders_without_media_links(admin_client, document):
    response = admin_client.get(reverse("admin:guests_guest_change", args=[document.guest_id]))
    assert response.status_code == 200
    assert b"/media/" not in response.content
    assert file_url(document).encode() in response.content


def test_document_change_page_renders_with_a_download_link(admin_client, document):
    response = admin_client.get(reverse("admin:guests_guestdocument_change", args=[document.pk]))
    assert response.status_code == 200
    assert file_url(document).encode() in response.content
    assert b"/media/" not in response.content


def test_admin_download_view_streams_the_file_to_staff_only(admin_client, client, document):
    response = admin_client.get(file_url(document))
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == PNG
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "no-store" in response["Cache-Control"]

    client.logout()
    anonymous = client.get(file_url(document))
    assert anonymous.status_code == 302 and "/login/" in anonymous["Location"]


def test_admin_uploads_get_the_same_checks_as_the_api(admin_client, organization):
    guest = GuestFactory(organization=organization)
    url = reverse("admin:guests_guestdocument_add")
    payload = {"guest": str(guest.pk), "kind": "other", "uploaded_via": "staff"}

    rejected = admin_client.post(url, {**payload, "file": SimpleUploadedFile("x.png", b"<html></html>")})
    assert rejected.status_code == 200 and not guest.documents.exists()  # form redisplayed with the error

    accepted = admin_client.post(url, {**payload, "file": SimpleUploadedFile("scan.bin", PNG)})
    assert accepted.status_code == 302
    assert guest.documents.get().file.name.endswith(".png")
