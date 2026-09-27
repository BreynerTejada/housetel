"""Permission codes per endpoint (plan §D roles) and multi-tenant isolation of the finance API."""

from decimal import Decimal

import pytest

from apps.accounts.services import add_member, ensure_system_roles
from apps.accounts.tests.factories import UserFactory
from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core.tests.factories import OrganizationFactory, PropertyFactory
from apps.finance.cash import open_cash_shift
from apps.finance.services import (
    create_payment_intent,
    get_or_create_folio,
    post_charge,
    record_payment,
    refund_payment,
)

pytestmark = pytest.mark.django_db

URL = "/api/v1/finance/"


@pytest.fixture
def world(prop, owner):
    reservation = ReservationFactory(property=prop)
    StayFactory(reservation=reservation, total_amount=Decimal("500000"))
    folio = get_or_create_folio(reservation)
    charge = post_charge(folio, kind="extra", amount=Decimal("10000"), description="Agua")
    payment = record_payment(folio, amount=Decimal("100000"), method="bank_transfer", actor=owner)
    ota = record_payment(folio, amount=Decimal("50000"), method="ota_collect")
    pending_refund = refund_payment(ota, amount=Decimal("50000"), reason="OTA", actor=owner, confirm=True)
    shift = open_cash_shift(prop, owner, opening_float=Decimal("0"))
    intent = create_payment_intent(folio, amount=Decimal("1000"), return_url="")
    return {
        "folio": folio,
        "charge": charge,
        "payment": payment,
        "pending_refund": pending_refund,
        "shift": shift,
        "intent": intent,
        "reservation": reservation,
    }


def endpoints(w):
    return {
        "list_folios": ("get", f"{URL}folios/", None),
        "folio_detail": ("get", f"{URL}folios/{w['folio'].pk}/", None),
        "charge_options": ("get", f"{URL}folios/{w['folio'].pk}/charge-options/", None),
        "post_charge": (
            "post",
            f"{URL}folios/{w['folio'].pk}/charges/",
            {"kind": "fee", "description": "x", "amount": "1000"},
        ),
        "void_charge": ("post", f"{URL}charges/{w['charge'].pk}/void/", {"reason": "x", "confirm": True}),
        "record_payment": (
            "post",
            f"{URL}folios/{w['folio'].pk}/payments/",
            {"amount": "1000", "method": "bank_transfer"},
        ),
        "refund": (
            "post",
            f"{URL}payments/{w['payment'].pk}/refund/",
            {"amount": "1000", "reason": "x", "confirm": True},
        ),
        "void_payment": ("post", f"{URL}payments/{w['payment'].pk}/void/", {"reason": "x", "confirm": True}),
        "complete_refund": (
            "post",
            f"{URL}refunds/{w['pending_refund'].pk}/complete/",
            {"confirm": True, "outcome": "approved"},
        ),
        "payment_link": ("post", f"{URL}folios/{w['folio'].pk}/payment-link/", {"amount": "1000"}),
        "intents": ("get", f"{URL}intents/", None),
        "intent_detail": ("get", f"{URL}intents/{w['intent'].pk}/", None),
        "sync_intent": ("post", f"{URL}intents/{w['intent'].pk}/sync/", {}),
        "current_shift": ("get", f"{URL}cash-shifts/current/", None),
        "shift_history": ("get", f"{URL}cash-shifts/", None),
        "shift_detail": ("get", f"{URL}cash-shifts/{w['shift'].pk}/", None),
        "open_shift": ("post", f"{URL}cash-shifts/open/", {"opening_float": "0"}),
        "close_shift": ("post", f"{URL}cash-shifts/{w['shift'].pk}/close/", {"counted_cash": "0"}),
        "export_shift": ("get", f"{URL}cash-shifts/{w['shift'].pk}/export/", None),
        "export_history": ("get", f"{URL}cash-shifts/export/", None),
        "summary": ("get", f"{URL}summary/", None),
    }


EXPECTED = {
    # front desk: finance.view, finance.collect, finance.cashier — no void / refund
    "front_desk": {
        "list_folios": 200,
        "folio_detail": 200,
        "charge_options": 200,
        "post_charge": 201,
        "void_charge": 403,
        "record_payment": 201,
        "refund": 403,
        "void_payment": 403,
        "complete_refund": 403,
        "payment_link": 201,
        "intents": 200,
        "intent_detail": 200,
        "sync_intent": 200,
        "current_shift": 200,
        "shift_history": 200,
        "shift_detail": 200,
        "open_shift": 201,
        "close_shift": 200,
        "export_shift": 200,
        "export_history": 200,
        "summary": 200,
    },
    # accountant: finance.*
    "accountant": {
        "void_charge": 200,
        "refund": 201,
        "void_payment": 200,
        "complete_refund": 200,
        "shift_history": 200,
        "close_shift": 200,
    },
    # housekeeping: nothing of finance
    "housekeeping": {
        "list_folios": 403,
        "folio_detail": 403,
        "post_charge": 403,
        "void_payment": 403,
        "complete_refund": 403,
        "intent_detail": 403,
        "sync_intent": 403,
        "current_shift": 403,
        "close_shift": 403,
        "export_shift": 403,
        "export_history": 403,
        "summary": 403,
    },
}


@pytest.mark.parametrize(
    ("role", "name", "status"),
    [(role, name, status) for role, cases in EXPECTED.items() for name, status in cases.items()],
)
def test_role_permissions(api_for, make_member, prop, world, role, name, status):
    method, url, payload = endpoints(world)[name]
    client = api_for(make_member(role), prop)
    response = getattr(client, method)(url, payload) if payload is not None else getattr(client, method)(url)
    assert response.status_code == status, (name, response.json() if response.content else None)
    if status == 403:
        assert response.json()["code"] == "permission_denied"


def test_another_organization_sees_nothing(api_for, world):
    stranger_org = OrganizationFactory()
    ensure_system_roles(stranger_org)
    stranger_prop = PropertyFactory(organization=stranger_org)
    stranger = UserFactory()
    add_member(stranger_org, stranger, "owner")
    client = api_for(stranger, stranger_prop)

    assert client.get(f"{URL}folios/").json()["count"] == 0
    assert client.get(f"{URL}intents/").json()["count"] == 0
    assert client.get(f"{URL}cash-shifts/").json()["count"] == 0
    assert client.get(f"{URL}summary/").json()["payments"]["count"] == 0
    history = client.get(f"{URL}cash-shifts/export/").content.decode("utf-8").lstrip("﻿").splitlines()
    assert len(history) == 1  # only the header row
    lists = {
        "list_folios",
        "intents",
        "current_shift",
        "shift_history",
        "open_shift",
        "summary",
        "export_history",
    }
    for name, (method, url, payload) in endpoints(world).items():
        if name in lists:
            continue
        response = (
            getattr(client, method)(url, payload) if payload is not None else getattr(client, method)(url)
        )
        assert response.status_code == 404, name


def test_the_folio_filter_does_not_leak_other_hotels(api_for, world, prop):
    sibling = PropertyFactory(organization=prop.organization)
    user = UserFactory()
    add_member(prop.organization, user, "owner")
    client = api_for(user, sibling)
    body = client.get(f"{URL}folios/", {"reservation": str(world["reservation"].pk)}).json()
    assert body["count"] == 0
