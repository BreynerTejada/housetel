"""Anomaly scan (`ai.anomaly_scan`, hourly): each rule raises its alert with a stable dedupe key, a repeated
scan does not duplicate it, a cleared condition resolves it and an alert the staff dismissed stays dismissed.
Plus the daily brief (`ai.daily_brief`)."""

from datetime import date, time
from decimal import Decimal

import pytest
from django.utils import timezone
from freezegun import freeze_time

from apps.ai.anomalies import scan_anomalies
from apps.bookings.models import Reservation
from apps.bookings.services.reservations import check_in, check_out
from apps.bookings.tests.helpers import book, build_hotel, oct_
from apps.core.models import Alert

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("frozen_morning")]


@pytest.fixture
def frozen_morning():
    with freeze_time("2026-10-01 10:00:00-05:00"):  # the hotel's business date, 10:00 in Bogotá
        yield


@pytest.fixture
def hotel(prop):
    return build_hotel(prop)  # DBL 101/102/201 (320.000 + IVA), STE 301, DORM D1; check-in 15:00


def open_alerts(prop, kind=None):
    alerts = Alert.objects.filter(
        property=prop, resolved_at__isnull=True, dedupe_key__startswith="ai:anomaly:"
    )
    return alerts.filter(kind=kind) if kind else alerts


def scan_at(prop, moment, rule=None):
    with freeze_time(moment):
        result = scan_anomalies(prop)
    return result["by_rule"].get(rule, 0) if rule else result


# ---- rules -------------------------------------------------------------------------------------------------


def test_a_confirmed_arrival_without_guarantee_or_payment_within_48h(hotel):
    soon = book(hotel, oct_(2), oct_(4))  # arrives tomorrow 15:00 → 29 h
    book(hotel, oct_(5), oct_(7))  # too far
    book(hotel, oct_(2), oct_(3), guarantee="card")  # guaranteed

    scan_anomalies(hotel.prop)

    (alert,) = open_alerts(hotel.prop, "unguaranteed_arrival")
    assert alert.dedupe_key == f"ai:anomaly:unguaranteed_arrival:{soon.pk}"
    assert (alert.severity, alert.link) == ("warning", f"/app/reservations/{soon.pk}")
    assert soon.code in alert.message


def test_a_paid_arrival_is_not_flagged(hotel):
    from apps.finance.services import get_or_create_folio, record_payment

    soon = book(hotel, oct_(2), oct_(4))
    record_payment(get_or_create_folio(soon), amount=Decimal("100000"), method="bank_transfer")

    scan_anomalies(hotel.prop)

    assert not open_alerts(hotel.prop, "unguaranteed_arrival").exists()


def test_two_equal_payments_on_the_same_folio_within_ten_minutes(hotel):
    from apps.finance.models import Payment
    from apps.finance.services import get_or_create_folio, record_payment

    reservation = book(hotel, oct_(3), oct_(5))
    folio = get_or_create_folio(reservation)
    record_payment(folio, amount=Decimal("200000"), method="card_terminal")
    second = record_payment(folio, amount=Decimal("200000"), method="card_terminal")
    other = book(hotel, oct_(6), oct_(8))
    record_payment(get_or_create_folio(other), amount=Decimal("50000"), method="card_terminal")
    late = record_payment(get_or_create_folio(other), amount=Decimal("50000"), method="card_terminal")
    Payment.objects.filter(pk=late.pk).update(created_at=timezone.now() + timezone.timedelta(minutes=20))

    scan_anomalies(hotel.prop)

    (alert,) = open_alerts(hotel.prop, "duplicate_payment")
    assert alert.dedupe_key == f"ai:anomaly:duplicate_payment:{second.pk}"
    assert reservation.code in alert.message


def test_a_nightly_rate_below_30_percent_of_the_default(hotel):
    from apps.rates.services.quote import set_daily_rates

    set_daily_rates(
        property=hotel.prop,
        room_type=hotel.dbl,
        rate_plan=hotel.plan,
        start=oct_(10),
        end=oct_(12),
        price=Decimal("50000"),
    )

    scan_anomalies(hotel.prop)

    (alert,) = open_alerts(hotel.prop, "rate_out_of_bounds")
    assert alert.dedupe_key == f"ai:anomaly:rate_out_of_bounds:{hotel.dbl.pk}:{hotel.plan.pk}"
    assert alert.data["dates"] == ["2026-10-10", "2026-10-11"]


def test_a_nightly_rate_outside_the_revenue_price_bounds(hotel):
    from apps.rates.services.quote import set_daily_rates
    from apps.revenue.models import PriceBounds

    PriceBounds.objects.create(
        room_type=hotel.ste, rate_plan=hotel.plan, min_price=Decimal("500000"), max_price=Decimal("800000")
    )
    set_daily_rates(
        property=hotel.prop,
        room_type=hotel.ste,
        rate_plan=hotel.plan,
        start=oct_(15),
        end=oct_(16),
        price=Decimal("950000"),
    )

    scan_anomalies(hotel.prop)

    (alert,) = open_alerts(hotel.prop, "rate_out_of_bounds")
    assert alert.data["dates"] == ["2026-10-15"]
    assert alert.data["room_type"] == hotel.ste.code


def test_in_house_nights_without_room_charge_after_the_audit(hotel, owner):
    from apps.bookings.services.charges import post_room_charges

    staying = book(hotel, oct_(1), oct_(4), stay_kwargs={"room_id": hotel.rooms["101"].pk})
    stay = check_in(staying.stays.get(), actor=owner)
    hotel.prop.business_date = oct_(3)  # two audits ran without posting the nights
    hotel.prop.save(update_fields=["business_date"])

    scan_anomalies(hotel.prop)

    (alert,) = open_alerts(hotel.prop, "unposted_nights")
    assert alert.data["nights"] == ["2026-10-01", "2026-10-02"]
    post_room_charges(stay, until_date=oct_(3))
    scan_anomalies(hotel.prop)
    assert not open_alerts(hotel.prop, "unposted_nights").exists()


def test_a_vip_arriving_soon_to_a_room_that_is_not_ready(hotel):
    from apps.guests.models import Guest
    from apps.inventory.services import set_housekeeping_status

    vip = book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["101"].pk})
    Guest.objects.filter(pk=vip.booker_id).update(is_vip=True)
    later = book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["102"].pk}, eta=time(20, 0))
    Guest.objects.filter(pk=later.booker_id).update(is_vip=True)
    for number in ("101", "102"):
        set_housekeeping_status(hotel.rooms[number], "dirty")

    assert not scan_at(
        hotel.prop, "2026-10-01 10:00:00-05:00", "vip_room_not_ready"
    )  # check-in (15:00) in 5 h
    scan_at(hotel.prop, "2026-10-01 13:30:00-05:00")

    (alert,) = open_alerts(hotel.prop, "vip_room_not_ready")
    assert (alert.severity, alert.link) == ("critical", f"/app/reservations/{vip.pk}")
    assert "101" in alert.message


def test_a_check_in_without_a_registered_tra_after_two_hours(hotel, owner):
    from apps.compliance.models import TraRegistration

    missing = book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["101"].pk})
    check_in(missing.stays.get(), actor=owner)
    done = book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["102"].pk})
    done_stay = check_in(done.stays.get(), actor=owner)
    TraRegistration.objects.create(
        property=hotel.prop,
        reservation=done,
        stay=done_stay,
        guest=done.booker,
        is_main=True,
        status="registered",
        tra_number="TRA-1",
    )

    assert not scan_at(hotel.prop, "2026-10-01 11:00:00-05:00", "missing_tra")  # only 1 h since check-in
    scan_at(hotel.prop, "2026-10-01 12:30:00-05:00")

    (alert,) = open_alerts(hotel.prop, "missing_tra")
    assert alert.dedupe_key.endswith(str(missing.stays.get().pk))


def _checked_out(hotel, owner, room):
    reservation = book(hotel, oct_(1), oct_(2), stay_kwargs={"room_id": hotel.rooms[room].pk})
    stay = check_in(reservation.stays.get(), actor=owner)
    return reservation, stay


def test_a_check_out_without_an_invoice_after_one_hour(hotel, owner):
    from apps.compliance.models import Invoice
    from apps.finance.services import get_or_create_folio

    missing, missing_stay = _checked_out(hotel, owner, "101")
    invoiced, invoiced_stay = _checked_out(hotel, owner, "102")
    hotel.prop.business_date = oct_(2)
    hotel.prop.save(update_fields=["business_date"])
    for stay in (missing_stay, invoiced_stay):
        check_out(stay, actor=owner, force=True)
    Invoice.objects.create(
        property=hotel.prop,
        reservation=invoiced,
        folio=get_or_create_folio(invoiced),
        status="accepted",
        issue_date=oct_(2),
    )

    assert not scan_at(hotel.prop, "2026-10-01 10:30:00-05:00", "missing_invoice")
    scan_at(hotel.prop, "2026-10-01 11:30:00-05:00")

    (alert,) = open_alerts(hotel.prop, "missing_invoice")
    assert alert.dedupe_key == f"ai:anomaly:missing_invoice:{missing.pk}"


def test_no_invoice_alert_when_the_hotel_does_not_issue_them_automatically(hotel, owner):
    from apps.compliance.models import ComplianceSettings

    ComplianceSettings.objects.update_or_create(property=hotel.prop, defaults={"auto_issue_invoices": False})
    _, stay = _checked_out(hotel, owner, "101")
    hotel.prop.business_date = oct_(2)
    hotel.prop.save(update_fields=["business_date"])
    check_out(stay, actor=owner, force=True)

    scan_at(hotel.prop, "2026-10-01 12:00:00-05:00")

    assert not open_alerts(hotel.prop, "missing_invoice").exists()


def test_a_cash_shift_that_closed_with_a_big_difference(hotel, make_member):
    from apps.finance.cash import close_cash_shift, open_cash_shift

    front, other = make_member("front_desk"), make_member("front_desk")
    short = open_cash_shift(hotel.prop, front, opening_float=Decimal("100000"))
    close_cash_shift(short, actor=front, counted_cash=Decimal("40000"))  # 60.000 missing
    fine = open_cash_shift(hotel.prop, other, opening_float=Decimal("100000"))
    close_cash_shift(fine, actor=other, counted_cash=Decimal("90000"))  # 10.000: tolerated

    scan_anomalies(hotel.prop)

    (alert,) = open_alerts(hotel.prop, "cash_difference")
    assert alert.dedupe_key == f"ai:anomaly:cash_difference:{short.pk}"
    assert alert.link == "/app/cashier"


def test_nights_sold_beyond_the_inventory(hotel):
    for _ in range(3):
        book(hotel, oct_(5), oct_(6))
    book(hotel, oct_(5), oct_(6), allow_overbooking=True)  # a 4th DBL on a 3-room category

    scan_anomalies(hotel.prop)

    (alert,) = open_alerts(hotel.prop, "oversold")
    assert (alert.severity, alert.dedupe_key) == ("critical", f"ai:anomaly:oversold:{hotel.dbl.pk}")
    assert alert.data["dates"] == ["2026-10-05"]


# ---- lifecycle ---------------------------------------------------------------------------------------------


def test_a_repeated_scan_does_not_duplicate_and_a_cleared_condition_resolves_itself(hotel):
    soon = book(hotel, oct_(2), oct_(4))

    scan_anomalies(hotel.prop)
    result = scan_anomalies(hotel.prop)

    assert open_alerts(hotel.prop).count() == 1
    assert result["raised"] == 1
    Reservation.objects.filter(pk=soon.pk).update(guarantee="card")
    result = scan_anomalies(hotel.prop)
    assert result["resolved"] == 1
    alert = Alert.objects.get(kind="unguaranteed_arrival")
    assert alert.resolved_at is not None and alert.resolved_by is None


def test_an_alert_the_staff_dismissed_is_not_raised_again(hotel, owner):
    from apps.core.alerts import resolve_alert

    soon = book(hotel, oct_(2), oct_(4))
    scan_anomalies(hotel.prop)
    resolve_alert(hotel.prop, f"ai:anomaly:unguaranteed_arrival:{soon.pk}", actor=owner)

    scan_anomalies(hotel.prop)

    assert not open_alerts(hotel.prop).exists()


def test_the_scan_only_sees_its_own_hotel(hotel, organization):
    from apps.core.tests.factories import PropertyFactory

    other = build_hotel(PropertyFactory(organization=organization))
    book(other, oct_(2), oct_(4))

    scan_anomalies(hotel.prop)

    assert not open_alerts(hotel.prop).exists()


# ---- automations -------------------------------------------------------------------------------------------


def test_the_hourly_scan_is_a_registered_automation(hotel):
    from apps.core import automation

    book(hotel, oct_(2), oct_(4))
    item = automation.get("ai.anomaly_scan")

    run = automation.run("ai.anomaly_scan", hotel.prop)

    assert (item.app, item.default_enabled) == ("ai", True)
    assert item.schedule.minute == {0}  # every hour, on the hour
    assert run.status == "success"
    assert run.details["by_rule"]["unguaranteed_arrival"] == 1


def test_the_daily_brief_summarizes_the_day_as_an_info_alert(hotel, llm_mode):
    from apps.core import automation

    llm_mode("simulated")
    book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["101"].pk})
    item = automation.get("ai.daily_brief")

    run = automation.run("ai.daily_brief", hotel.prop)

    assert (item.schedule.hour, item.schedule.minute) == ({7}, {30})
    assert run.status == "success"
    alert = Alert.objects.get(property=hotel.prop, kind="daily_brief")
    assert (alert.severity, alert.dedupe_key) == ("info", "ai:daily_brief:2026-10-01")
    assert "1" in alert.message and alert.message.strip()


def test_the_daily_brief_uses_the_model_with_the_days_facts(hotel, monkeypatch):
    import json

    from apps.ai.anomalies import daily_brief
    from apps.ai.tests.fakes import ScriptedLLM, real_data

    book(hotel, oct_(1), oct_(3))
    llm = ScriptedLLM([real_data({"text": "- Hoy llega 1 reserva.\n- Ocupación baja."})])
    monkeypatch.setattr("apps.ai.anomalies.llm_for", lambda prop, feature, **kwargs: llm)

    alert = daily_brief(hotel.prop)

    facts = json.loads(llm.calls[0]["messages"][-1]["content"])
    assert (facts["date"], facts["arrivals"]) == ("2026-10-01", 1)
    assert alert.message == "- Hoy llega 1 reserva.\n- Ocupación baja."


def test_the_scan_of_one_hotel_can_run_while_other_apps_are_missing(hotel, monkeypatch):
    """The compliance and revenue rules are skipped when those apps are not installed."""
    import apps.ai.anomalies as anomalies

    monkeypatch.setattr(anomalies, "optional_model", lambda label: None)
    book(hotel, oct_(2), oct_(4))

    result = scan_anomalies(hotel.prop)

    assert result["raised"] == 1
    assert date(2026, 10, 1) == hotel.prop.business_date
