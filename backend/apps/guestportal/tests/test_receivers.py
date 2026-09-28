"""What the portal keeps about a guest follows the CRM: anonymization erases it, merges re-key it."""

from pathlib import Path

import pytest
from django.core.files.base import ContentFile

from apps.guestportal.models import OnlineCheckin
from apps.guestportal.tests.conftest import png_bytes
from apps.guests.services import anonymize_guest, merge_guests
from apps.guests.tests.factories import GuestFactory

pytestmark = pytest.mark.django_db

TRIP = {"travel_reason": "leisure", "origin": "Cali", "destination": "Cali"}


@pytest.fixture
def signed(reservation):
    companion = GuestFactory(organization=reservation.property.organization)
    reservation.stays.get().occupants.add(companion)
    checkin = OnlineCheckin.objects.create(
        reservation=reservation,
        status="completed",
        data={"travel": {str(reservation.booker_id): TRIP, str(companion.pk): TRIP}},
        ip="181.1.2.3",
        user_agent="Mozilla/5.0",
    )
    checkin.signature.save("signature.png", ContentFile(png_bytes()), save=True)
    return checkin, companion


def test_anonymizing_the_booker_erases_the_trip_data_and_the_signature(
    reservation, signed, owner, django_capture_on_commit_callbacks
):
    checkin, companion = signed
    signature_path = Path(checkin.signature.path)

    with django_capture_on_commit_callbacks(execute=True):
        anonymize_guest(reservation.booker, actor=owner)

    checkin.refresh_from_db()
    assert list(checkin.data["travel"]) == [str(companion.pk)]
    assert not checkin.signature
    assert not signature_path.exists()
    assert (checkin.ip, checkin.user_agent) == (None, "")


def test_anonymizing_a_companion_keeps_the_booker_signature(reservation, signed, owner,
                                                            django_capture_on_commit_callbacks):  # fmt: skip
    checkin, companion = signed

    with django_capture_on_commit_callbacks(execute=True):
        anonymize_guest(companion, actor=owner)

    checkin.refresh_from_db()
    assert list(checkin.data["travel"]) == [str(reservation.booker_id)]
    assert checkin.signature


def test_a_merge_moves_the_trip_data_to_the_surviving_profile(
    reservation, signed, owner, django_capture_on_commit_callbacks
):
    checkin, companion = signed
    primary = GuestFactory(organization=reservation.property.organization)

    with django_capture_on_commit_callbacks(execute=True):
        merge_guests(primary, companion, actor=owner)

    checkin.refresh_from_db()
    assert checkin.data["travel"][str(primary.pk)] == TRIP
    assert str(companion.pk) not in checkin.data["travel"]
