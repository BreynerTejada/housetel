"""Fixtures of the front desk tests.

`hotel` is the small hotel of the bookings tests (apps/bookings/tests/helpers.py::build_hotel):
- DBL (private): rooms 101 (floor 1), 102 (floor 1), 201 (floor 2); 320.000/night + IVA 19 % (not included).
- STE (private): room 301; 650.000/night.
- DORM (dorm): room D1 with beds A–D; 65.000/bed-night.
- Base plan BAR without cancellation policy. Business date 2026-10-01 (Thursday).
"""

import pytest

from apps.bookings.tests.helpers import build_hotel


@pytest.fixture
def hotel(prop):
    return build_hotel(prop)


@pytest.fixture
def front_desk(make_member):
    return make_member("front_desk")


@pytest.fixture
def manager(make_member):
    return make_member("manager")
