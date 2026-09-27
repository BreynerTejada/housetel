"""Signals of `guests` for the apps of later phases (apps/guests/signals.py): apps that keep their own copy of
a guest's personal data (message threads, legal reports…) react to `guest_anonymized`; apps that reference
guests without a foreign key react to `guests_merged`. Both go out only once the transaction commits."""

import pytest

from apps.guests import signals
from apps.guests.services import anonymize_guest, merge_guests
from apps.guests.tests.factories import GuestFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def listen():
    connected = []

    def _listen(signal):
        calls = []

        def receiver(sender, **kwargs):
            kwargs.pop("signal", None)
            calls.append(kwargs)

        signal.connect(receiver, weak=False)
        connected.append((signal, receiver))
        return calls

    yield _listen
    for signal, receiver in connected:
        signal.disconnect(receiver)


def test_anonymize_announces_the_erased_guest_and_its_merged_records_after_commit(
    organization, owner, listen, django_capture_on_commit_callbacks
):
    guest = GuestFactory(organization=organization)
    old = GuestFactory(organization=organization)
    merge_guests(guest, old, actor=owner)
    calls = listen(signals.guest_anonymized)

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        anonymize_guest(guest, actor=owner)
    assert calls == []  # nothing before the commit
    for callback in callbacks:
        callback()

    assert len(calls) == 1
    assert calls[0]["guest"].pk == guest.pk and calls[0]["guest"].anonymized_at is not None
    assert calls[0]["merged_ids"] == [old.pk]


def test_merge_announces_the_surviving_and_the_merged_guest_after_commit(
    organization, owner, listen, django_capture_on_commit_callbacks
):
    primary = GuestFactory(organization=organization)
    duplicate = GuestFactory(organization=organization)
    calls = listen(signals.guests_merged)

    with django_capture_on_commit_callbacks(execute=True):
        merge_guests(primary, duplicate, actor=owner)

    assert len(calls) == 1
    assert (calls[0]["primary"].pk, calls[0]["duplicate"].pk) == (primary.pk, duplicate.pk)
    assert calls[0]["duplicate"].merged_into_id == primary.pk
