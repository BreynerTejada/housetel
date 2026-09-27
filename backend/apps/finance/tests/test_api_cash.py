"""Staff API: cash shifts (current, open, close, history, export) and the daily payments summary."""

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.bookings.tests.factories import ReservationFactory
from apps.finance.cash import open_cash_shift
from apps.finance.models import CashShift
from apps.finance.services import get_or_create_folio, post_charge, record_payment, refund_payment

pytestmark = pytest.mark.django_db

URL = "/api/v1/finance/"


@pytest.fixture
def folio(prop):
    return get_or_create_folio(ReservationFactory(property=prop, code="HT-CASH01"))


def test_no_current_shift(api):
    assert api.get(f"{URL}cash-shifts/current/").json() == {"shift": None}


def test_open_shift_with_live_totals_and_movements(api, folio, owner):
    opened = api.post(f"{URL}cash-shifts/open/", {"opening_float": "200000", "notes": "Mañana"})
    assert opened.status_code == 201, opened.json()
    api.post(f"{URL}folios/{folio.pk}/payments/", {"amount": "100000", "method": "cash"})
    api.post(f"{URL}folios/{folio.pk}/payments/", {"amount": "50000", "method": "card_terminal"})

    shift = api.get(f"{URL}cash-shifts/current/").json()["shift"]

    assert (shift["id"], shift["is_open"], shift["opening_float"], shift["user"]["id"]) == (
        opened.json()["id"],
        True,
        "200000.00",
        str(owner.pk),
    )
    assert shift["totals"]["expected_cash"] == "300000.00"
    assert shift["totals"]["by_method"] == [
        {"method": "card_terminal", "count": 1, "total": "50000.00"},
        {"method": "cash", "count": 1, "total": "100000.00"},
    ]
    assert {(m["kind"], m["method"], m["amount"], m["reservation_code"]) for m in shift["movements"]} == {
        ("payment", "cash", "100000.00", "HT-CASH01"),
        ("payment", "card_terminal", "50000.00", "HT-CASH01"),
    }


def test_only_one_open_shift(api):
    api.post(f"{URL}cash-shifts/open/", {"opening_float": "0"})
    response = api.post(f"{URL}cash-shifts/open/", {"opening_float": "0"})
    assert (response.status_code, response.json()["code"]) == (409, "cash_shift_open")


def test_close_by_denomination(api, prop, owner, folio):
    shift = open_cash_shift(prop, owner, opening_float=Decimal("200000"))
    record_payment(folio, amount=Decimal("100000"), method="cash", actor=owner)

    response = api.post(f"{URL}cash-shifts/{shift.pk}/close/", {"denominations": {"100000": 2, "50000": 2}})

    assert response.status_code == 200, response.json()
    body = response.json()
    assert (body["is_open"], body["expected_cash"], body["counted_cash"], body["difference"]) == (
        False,
        "300000.00",
        "300000.00",
        "0.00",
    )
    assert body["closed_by"]["id"] == str(owner.pk)


def test_close_needs_a_count(api, prop, owner):
    shift = open_cash_shift(prop, owner, opening_float=Decimal("0"))
    response = api.post(f"{URL}cash-shifts/{shift.pk}/close/", {"notes": "x"})
    assert (response.status_code, response.json()["code"]) == (400, "counted_cash_required")


def test_history_and_detail(api, prop, owner, folio, make_member):
    closed = open_cash_shift(prop, owner, opening_float=Decimal("100000"))
    cash = record_payment(folio, amount=Decimal("40000"), method="cash", actor=owner)
    refund_payment(cash, amount=Decimal("10000"), reason="Vuelto", actor=owner, confirm=True)
    closed.refresh_from_db()
    from apps.finance.cash import close_cash_shift

    close_cash_shift(closed, counted_cash=Decimal("125000"), actor=owner)
    other = open_cash_shift(prop, make_member("front_desk"), opening_float=Decimal("50000"))

    listing = api.get(f"{URL}cash-shifts/").json()
    assert {row["id"]: row["difference"] for row in listing["results"]} == {
        str(closed.pk): "-5000.00",
        str(other.pk): None,
    }
    detail = api.get(f"{URL}cash-shifts/{closed.pk}/").json()
    assert [(m["kind"], m["amount"]) for m in detail["movements"]] == [
        ("payment", "40000.00"),
        ("refund", "10000.00"),
    ]
    assert detail["totals"]["cash_refunds"] == "10000.00"


def test_shift_export_is_a_csv_for_excel(api, prop, owner, folio):
    shift = open_cash_shift(prop, owner, opening_float=Decimal("100000"))
    record_payment(folio, amount=Decimal("40000"), method="cash", actor=owner)

    response = api.get(f"{URL}cash-shifts/{shift.pk}/export/")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert f"caja-{timezone.localtime(shift.opened_at):%Y%m%d}" in response["Content-Disposition"]
    text = response.content.decode("utf-8")
    assert text.startswith("\ufeff")
    lines = text.lstrip("\ufeff").splitlines()
    assert lines[0].split(";")[:3] == ["Fecha", "Tipo", "Medio"]
    assert any("HT-CASH01" in line and "40000.00" in line for line in lines)


def test_history_export(api, prop, owner):
    shift = open_cash_shift(prop, owner, opening_float=Decimal("100000"))
    today = prop.business_date.isoformat()
    response = api.get(f"{URL}cash-shifts/export/", {"start": today, "end": today})
    assert response.status_code == 200
    lines = response.content.decode("utf-8").lstrip("\ufeff").splitlines()
    assert len(lines) == 2 and owner.email in lines[1]
    assert str(shift.pk)[:8] in lines[1]


def test_history_export_totals_every_shift_without_a_query_per_shift(api, prop, folio, make_member):
    def export():
        with CaptureQueriesContext(connection) as queries:
            response = api.get(f"{URL}cash-shifts/export/")
        assert response.status_code == 200
        return response, len(queries.captured_queries)

    def shift_with_cash(cash_in, cash_back=None):
        user = make_member("front_desk")
        shift = open_cash_shift(prop, user, opening_float=Decimal("100000"))
        payment = record_payment(folio, amount=cash_in, method="cash", actor=user)
        if cash_back:
            refund_payment(payment, amount=cash_back, reason="Vuelto", actor=user, confirm=True)
        return shift

    first = shift_with_cash(Decimal("40000"), Decimal("10000"))
    _, with_one_shift = export()
    for _ in range(3):
        shift_with_cash(Decimal("5000"))

    response, with_four_shifts = export()

    assert with_four_shifts == with_one_shift
    rows = [line.split(";") for line in response.content.decode("utf-8").lstrip("﻿").splitlines()[1:]]
    assert len(rows) == 4
    (row,) = [row for row in rows if row[0] == str(first.pk)[:8]]
    # opening float, cash received, cash given back, expected (still open: computed live)
    assert row[4:8] == ["100000.00", "40000.00", "10000.00", "130000.00"]


def test_daily_summary(api, prop, owner, folio):
    open_cash_shift(prop, owner, opening_float=Decimal("0"))
    cash = record_payment(folio, amount=Decimal("100000"), method="cash", actor=owner)
    record_payment(folio, amount=Decimal("60000"), method="card_terminal", actor=owner)
    record_payment(folio, amount=Decimal("5000"), method="card_terminal", actor=owner, status="declined")
    refund_payment(cash, amount=Decimal("20000"), reason="Vuelto", actor=owner, confirm=True)
    post_charge(folio, kind="extra", amount=Decimal("30000"), description="Tour")

    body = api.get(f"{URL}summary/").json()

    assert body["date"] == prop.business_date.isoformat() and body["currency"] == "COP"
    assert body["payments"] == {"count": 2, "total": "160000.00"}
    assert body["refunds"] == {"count": 1, "total": "20000.00"}
    assert body["net_total"] == "140000.00"
    assert body["by_method"] == [
        {"method": "card_terminal", "count": 1, "total": "60000.00"},
        {"method": "cash", "count": 1, "total": "100000.00"},
    ]
    assert body["charges"] == {"net": "30000.00", "tax": "0.00", "total": "30000.00"}
    assert CashShift.objects.count() == 1
