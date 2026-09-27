"""Permission catalog grouped by module, and the escalation rule: nobody grants what they do not have."""

import pytest

from apps.accounts.catalog import covers, permission_catalog, unknown_permissions
from apps.core.permissions import catalog


def test_catalog_groups_every_registered_code_once_by_module():
    modules = permission_catalog()

    codes = [p["code"] for module in modules for p in module["permissions"]]
    assert sorted(codes) == sorted(catalog())
    assert modules[0]["code"] == "accounts"
    bookings = next(m for m in modules if m["code"] == "bookings")
    assert (bookings["label_es"], bookings["label_en"]) == ("Reservas", "Reservations")
    assert {"code": "bookings.view", "label_es": "Ver reservas", "label_en": "View reservations"} in bookings[
        "permissions"
    ]


@pytest.mark.parametrize(
    ("granted", "requested", "expected"),
    [
        (["*"], ["*"], True),
        (["*"], ["finance.refund", "bookings.*"], True),
        (["bookings.*"], ["bookings.view", "bookings.manage"], True),
        (["bookings.*"], ["bookings.*"], True),
        (["bookings.view"], ["bookings.*"], False),  # a pattern grants every code it matches
        (["bookings.view"], ["bookings.view", "finance.refund"], False),
        ([c for c in catalog() if c != "saas.billing_manage"], ["*"], False),
        # every current code listed one by one is still not `*`, which also grants future permissions
        (list(catalog()), ["*"], False),
        (list(catalog()), ["bookings.*", "finance.refund"], True),
        (["guests.view"], [], True),
    ],
)
def test_covers(granted, requested, expected):
    assert covers(granted, requested) is expected


def test_unknown_permissions_are_reported():
    assert unknown_permissions(["bookings.view", "bookings.*", "*", "nope.view", "bookings.fly"]) == [
        "nope.view",
        "bookings.fly",
    ]
