"""Fixtures of the distribution tests.

`hotel` is the small hotel of the bookings tests (`apps/bookings/tests/helpers.py::build_hotel`): business
date 2026-10-01 (Thursday); DBL (rooms 101, 102, 201; 320.000/night), STE (room 301; 650.000/night) and DORM
(room D1, beds A–D; 65.000/bed-night); base plan BAR selling the three; IVA 19 % not included, exempt for
foreign non-residents.
"""

import pytest

from apps.bookings.tests.helpers import build_hotel
from apps.distribution.tests.factories import connect


@pytest.fixture
def hotel(prop):
    return build_hotel(prop)


@pytest.fixture(autouse=True)
def scheduled_pushes(monkeypatch):
    """The debounced Celery push never reaches a broker in tests: each scheduling is recorded instead."""
    from apps.distribution import tasks

    calls = []
    monkeypatch.setattr(
        tasks.push_ari_queue, "apply_async", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    return calls


@pytest.fixture
def booksim(hotel):
    """BookSim mapping DBL (`BS-DBL`) and STE (`BS-STE`) with the base plan BAR (`BS-BAR`), no markup."""
    return connect(hotel, "booksim")
