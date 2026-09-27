"""Photos of categories (`room-types/{id}/photos/`) and of the property (`property/photos/`).

Photos are public (the marketplace shows them): their `url` is a plain media URL, no session needed.
"""

import json

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.inventory.models import Photo
from apps.inventory.tests.conftest import BASE
from apps.inventory.tests.factories import RoomTypeFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def room_type(prop):
    return RoomTypeFactory(property=prop)


def photos_url(room_type=None, suffix=""):
    base = f"{BASE}/room-types/{room_type.pk}/photos/" if room_type else f"{BASE}/property/photos/"
    return f"{base}{suffix}"


def upload(api, url, image, **fields):
    return api.post(url, {"image": image, **fields}, format="multipart")


class TestUpload:
    def test_uploads_a_photo_with_a_translated_caption(self, api, prop, room_type, make_image):
        caption = json.dumps({"es": "Vista al mar", "en": "Sea view"})
        response = upload(api, photos_url(room_type), make_image(), caption=caption)
        assert response.status_code == 201, response.json()
        body = response.json()
        photo = Photo.objects.get(pk=body["id"])
        assert (photo.property, photo.room_type, photo.caption) == (
            prop,
            room_type,
            {"es": "Vista al mar", "en": "Sea view"},
        )
        assert body["url"].startswith("/media/photos/") and body["url"].endswith(".png")
        assert default_storage.exists(photo.image.name)

    def test_files_go_to_the_dated_photos_folder_once(self, api, room_type, make_image):
        import re

        body = upload(api, photos_url(room_type), make_image()).json()
        name = Photo.objects.get(pk=body["id"]).image.name
        assert re.fullmatch(r"photos/\d{4}/\d{2}/[0-9a-f]{32}\.png", name), name
        assert body["url"] == f"/media/{name}"

    def test_a_plain_caption_is_spanish_and_photos_go_last(self, api, room_type, make_image):
        upload(api, photos_url(room_type), make_image())
        body = upload(api, photos_url(room_type), make_image("b.jpg", "JPEG"), caption="Baño").json()
        assert body["caption"] == {"es": "Baño"}
        assert body["sort_order"] > Photo.objects.order_by("sort_order").first().sort_order

    def test_rejects_files_that_are_not_images(self, api, room_type):
        fake = SimpleUploadedFile("notes.png", b"not an image", content_type="image/png")
        response = upload(api, photos_url(room_type), fake)
        assert response.status_code == 400 and "image" in response.json()["fields"]
        assert not Photo.objects.exists()

    def test_property_photos_belong_to_no_category(self, api, prop, make_image):
        response = upload(api, photos_url(), make_image())
        assert response.status_code == 201
        photo = Photo.objects.get(pk=response.json()["id"])
        assert (photo.property, photo.room_type, photo.room) == (prop, None, None)

    def test_a_category_of_another_property_is_not_found(self, api, make_image):
        foreign = RoomTypeFactory()
        assert upload(api, photos_url(foreign), make_image()).status_code == 404


class TestManage:
    def test_lists_photos_in_order(self, api, prop, room_type):
        Photo.objects.create(property=prop, room_type=room_type, image="photos/2.jpg", sort_order=2)
        Photo.objects.create(property=prop, room_type=room_type, image="photos/1.jpg", sort_order=1)
        Photo.objects.create(property=prop, image="photos/p.jpg")  # property photo
        response = api.get(photos_url(room_type))
        assert [photo["url"] for photo in response.json()] == ["/media/photos/1.jpg", "/media/photos/2.jpg"]

    def test_edits_the_caption(self, api, prop, room_type):
        photo = Photo.objects.create(property=prop, room_type=room_type, image="photos/1.jpg")
        response = api.patch(
            photos_url(room_type, f"{photo.pk}/"), {"caption": {"es": "Suite", "en": "Suite"}}
        )
        assert response.status_code == 200
        photo.refresh_from_db()
        assert photo.caption == {"es": "Suite", "en": "Suite"}

    def test_deleting_removes_the_file(self, api, room_type, make_image, django_capture_on_commit_callbacks):
        photo_id = upload(api, photos_url(room_type), make_image()).json()["id"]
        name = Photo.objects.get(pk=photo_id).image.name
        with django_capture_on_commit_callbacks(execute=True):
            assert api.delete(photos_url(room_type, f"{photo_id}/")).status_code == 204
        assert not Photo.objects.filter(pk=photo_id).exists()
        assert not default_storage.exists(name)

    def test_reorders_every_photo(self, api, prop, room_type):
        first, second, third = (
            Photo.objects.create(property=prop, room_type=room_type, image=f"photos/{n}.jpg", sort_order=n)
            for n in (1, 2, 3)
        )
        ids = [str(third.pk), str(first.pk), str(second.pk)]
        response = api.post(photos_url(room_type, "reorder/"), {"ids": ids})
        assert response.status_code == 200
        assert [photo["id"] for photo in response.json()] == ids

    def test_reorder_needs_exactly_the_category_photos(self, api, prop, room_type):
        photo = Photo.objects.create(property=prop, room_type=room_type, image="photos/1.jpg")
        other = Photo.objects.create(property=prop, image="photos/p.jpg")
        response = api.post(photos_url(room_type, "reorder/"), {"ids": [str(photo.pk), str(other.pk)]})
        assert response.status_code == 400

    def test_caption_edits_and_reorders_are_audited(self, api, owner, prop, room_type):
        from apps.core.models import AuditEvent

        first, second = (
            Photo.objects.create(property=prop, room_type=room_type, image=f"photos/{n}.jpg", sort_order=n)
            for n in (1, 2)
        )
        api.patch(photos_url(room_type, f"{first.pk}/"), {"caption": {"es": "Suite"}})
        api.post(photos_url(room_type, "reorder/"), {"ids": [str(second.pk), str(first.pk)]})
        api.post(photos_url(room_type, "reorder/"), {"ids": [str(second.pk), str(first.pk)]})  # no change

        caption = AuditEvent.objects.get(action="inventory.photo_updated")
        assert (caption.target_id, caption.actor, caption.property) == (str(first.pk), owner, prop)
        assert caption.changes == {"caption": [{}, {"es": "Suite"}]}
        reorder = AuditEvent.objects.get(action="inventory.photos_reordered")  # only the real change
        assert (reorder.target_id, reorder.actor, reorder.property) == (str(room_type.pk), owner, prop)

    def test_photos_of_another_category_are_not_reachable(self, api, prop, room_type):
        other = Photo.objects.create(
            property=prop, room_type=RoomTypeFactory(property=prop), image="photos/x.jpg"
        )
        assert api.delete(photos_url(room_type, f"{other.pk}/")).status_code == 404


def test_housekeeping_can_see_but_not_upload(hk_api, room_type, make_image):
    assert hk_api.get(photos_url(room_type)).status_code == 200
    assert upload(hk_api, photos_url(room_type), make_image()).status_code == 403
