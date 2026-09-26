import logging

import pytest
from django.dispatch import Signal

from apps.core.signals import send_on_commit

pytestmark = pytest.mark.django_db


def test_send_on_commit_only_fires_after_commit(django_capture_on_commit_callbacks):
    signal = Signal()
    received = []
    signal.connect(lambda sender, **kwargs: received.append(kwargs["reservation"]), weak=False)

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        send_on_commit(signal, reservation="R-1")
        assert received == []

    assert len(callbacks) == 1
    callbacks[0]()
    assert received == ["R-1"]


def test_a_failing_receiver_is_logged_and_does_not_break_the_others(
    django_capture_on_commit_callbacks, caplog
):
    signal = Signal()
    calls = []

    def broken(sender, **kwargs):
        raise RuntimeError("receiver exploded")

    def healthy(sender, **kwargs):
        calls.append(kwargs["payment"])

    signal.connect(broken, weak=False)
    signal.connect(healthy, weak=False)

    with caplog.at_level(logging.ERROR, logger="housetel.signals"):
        with django_capture_on_commit_callbacks(execute=True):
            send_on_commit(signal, payment="P-1")

    assert calls == ["P-1"]
    assert "receiver exploded" in caplog.text
