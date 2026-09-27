"""Fixtures of the bookings tests: a small Colombian hotel priced by a base plan.

- DBL (private, base occupancy 2, max 2 adults + 1 child, max 3): rooms 101 (floor 1), 102 (floor 1),
  201 (floor 2); 320.000/night.
- STE (private): room 301 (floor 3); 650.000/night.
- DORM (dorm, one person per bed): room D1 with beds A–D; 65.000/bed-night.
- Base plan BAR for the three categories; IVA 19 % not included, exempt for foreign non-residents.
- Business date 2026-10-01 (Thursday).
"""

import pytest

from apps.bookings.tests.helpers import build_hotel
from apps.core import signals

DOMAIN_SIGNALS = [
    "reservation_created",
    "reservation_updated",
    "reservation_cancelled",
    "reservation_no_show",
    "stay_checked_in",
    "stay_checked_out",
    "room_assigned",
    "room_status_changed",
    "inventory_changed",
    "rates_changed",
    "payment_received",
    "folio_closed",
    "guest_checked_in_online",
]


class SignalLog(list):
    """[(signal name, kwargs)] in emission order."""

    def of(self, name: str) -> list[dict]:
        return [kwargs for signal_name, kwargs in self if signal_name == name]


@pytest.fixture
def signal_log():
    """Records every domain signal actually sent (i.e. after commit when executed by
    `django_capture_on_commit_callbacks(execute=True)`)."""
    log = SignalLog()

    def recorder(name):
        def handler(sender, **kwargs):
            kwargs.pop("signal", None)
            log.append((name, kwargs))

        return handler

    for name in DOMAIN_SIGNALS:
        getattr(signals, name).connect(recorder(name), weak=False, dispatch_uid=f"test-signal-log-{name}")
    yield log
    for name in DOMAIN_SIGNALS:
        getattr(signals, name).disconnect(dispatch_uid=f"test-signal-log-{name}")


@pytest.fixture
def hotel(prop):
    return build_hotel(prop)
