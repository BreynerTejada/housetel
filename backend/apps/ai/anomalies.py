"""Anomaly detection (plan C9, automation `ai.anomaly_scan`, hourly) and the daily brief (`ai.daily_brief`).

Each rule looks at a bounded window of the hotel's data and returns findings; every finding becomes an alert
(`core.alerts.raise_alert`) with a stable dedupe key `ai:anomaly:<rule>:<object>`, so a repeated scan updates
the open alert instead of duplicating it. After the scan, open anomaly alerts whose condition is gone are
resolved automatically. An alert the staff resolved by hand is not raised again: never for alerts about one
object (a reservation, a stay, a payment, a cash shift), and not for a day for aggregated ones (rates or
oversold nights of a room type), which can come back with new dates.

Rules: confirmed arrival < 48 h without guarantee or payment · duplicate payment (same folio, amount and
method in < 10 min) · nightly rate outside the revenue price bounds or below 30 % of the default · in-house
nights without a room charge after the night audit · VIP arriving < 2 h from the ETA (or check-in time) to a
room that is not ready · check-in without a registered TRA after 2 h · check-out without an issued invoice
after 1 h (when the hotel issues them automatically) · cash shift closed with a difference above 50 000 ·
nights sold beyond the inventory. The compliance (TRA, invoices) and revenue (price bounds) rules run only
when those apps' models exist.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from django.apps import apps as django_apps
from django.db.models import Q, Sum
from django.utils import timezone

from apps.ai import nlp
from apps.ai.llm import llm_for
from apps.ai.simulated import register_structured
from apps.core.alerts import raise_alert
from apps.core.dates import property_now
from apps.core.models import Alert

logger = logging.getLogger("housetel.ai")

PREFIX = "ai:anomaly:"
ACTIVE = ["tentative", "confirmed", "checked_in"]
GUARANTEE_WINDOW = timedelta(hours=48)
DUPLICATE_PAYMENT_WINDOW = timedelta(minutes=10)
VIP_WINDOW = timedelta(hours=2)
TRA_GRACE = timedelta(hours=2)
INVOICE_GRACE = timedelta(hours=1)
LOOKBACK = timedelta(days=3)
CASH_TOLERANCE = Decimal("50000")
RATE_FLOOR_PERCENT = Decimal("30")
RATE_HORIZON_DAYS = 90
OVERSOLD_HORIZON_DAYS = 365
DISMISSED_FOR = timedelta(days=1)


@dataclass
class Finding:
    rule: str
    key: str  # the object it is about (part of the dedupe key)
    severity: str
    title: str
    message: str
    link: str = ""
    data: dict = field(default_factory=dict)
    per_object: bool = True  # False: aggregated (a manual dismissal lasts a day)

    @property
    def dedupe_key(self) -> str:
        return f"{PREFIX}{self.rule}:{self.key}"


def optional_model(label: str):
    """A model of an app built in parallel (compliance, revenue), or None when it is not available."""
    try:
        return django_apps.get_model(label)
    except (LookupError, ValueError):
        return None


class Scan:
    def __init__(self, prop):
        self.property = prop
        self.now = timezone.now()
        self.local_now = property_now(prop)
        self.today = prop.business_date

    def at_local(self, day, hour) -> datetime:
        """`day` at `hour` in the hotel's time zone."""
        naive = datetime.combine(day, hour)
        return naive.replace(tzinfo=self.local_now.tzinfo)


def _money(value, currency="COP") -> str:
    return nlp.format_money(value, currency)


# ---- rules -------------------------------------------------------------------------------------------------


def unguaranteed_arrival(scan: Scan) -> list[Finding]:
    from apps.bookings.models import Reservation
    from apps.finance.models import Payment

    prop = scan.property
    candidates = Reservation.objects.filter(
        property=prop,
        status="confirmed",
        guarantee="none",
        checkin_date__gte=scan.today,
        checkin_date__lte=scan.today + timedelta(days=2),
    ).select_related("booker")
    paid = set(
        Payment.objects.filter(folio__reservation__in=candidates, status="approved").values_list(
            "folio__reservation_id", flat=True
        )
    )
    findings = []
    for reservation in candidates:
        arrival = scan.at_local(reservation.checkin_date, prop.check_in_time)
        if reservation.pk in paid or arrival - scan.now > GUARANTEE_WINDOW:
            continue
        findings.append(
            Finding(
                rule="unguaranteed_arrival",
                key=str(reservation.pk),
                severity="warning",
                title=f"Llegada sin garantía: {reservation.code}",
                message=(
                    f"{reservation.booker.full_name} llega el {nlp.format_date(reservation.checkin_date)} y "
                    f"la reserva {reservation.code} no tiene garantía ni pagos. Pide un depósito o "
                    "confírmala por teléfono."
                ),
                link=f"/app/reservations/{reservation.pk}",
                data={
                    "reservation_id": str(reservation.pk),
                    "code": reservation.code,
                    "checkin": reservation.checkin_date.isoformat(),
                },
            )
        )
    return findings


def duplicate_payment(scan: Scan) -> list[Finding]:
    from apps.finance.models import Payment

    payments = (
        Payment.objects.filter(
            folio__property=scan.property, status="approved", created_at__gte=scan.now - LOOKBACK
        )
        .select_related("folio__reservation")
        .order_by("folio_id", "method", "amount", "created_at")
    )
    findings, previous = [], None
    for payment in payments:
        same = previous is not None and (previous.folio_id, previous.method, previous.amount) == (
            payment.folio_id,
            payment.method,
            payment.amount,
        )
        if same and payment.created_at - previous.created_at <= DUPLICATE_PAYMENT_WINDOW:
            reservation = payment.folio.reservation
            target = reservation.code if reservation else "un folio de la casa"
            findings.append(
                Finding(
                    rule="duplicate_payment",
                    key=str(payment.pk),
                    severity="warning",
                    title=f"Posible pago duplicado en {target}",
                    message=(
                        f"Se registraron dos pagos de {_money(payment.amount, scan.property.currency)} por "
                        f"el mismo medio ({payment.method}) en {target} con menos de 10 minutos de "
                        "diferencia. Revisa si hay que anular o reembolsar uno."
                    ),
                    link=f"/app/reservations/{reservation.pk}" if reservation else "/app/cashier",
                    data={
                        "payment_id": str(payment.pk),
                        "previous_payment_id": str(previous.pk),
                        "amount": f"{payment.amount:.2f}",
                        "method": payment.method,
                    },
                )
            )
        previous = payment
    return findings


def rate_out_of_bounds(scan: Scan) -> list[Finding]:
    from apps.rates.models import DailyRate, RoomTypeRateDefaults

    PriceBounds = optional_model("revenue.PriceBounds")
    prop = scan.property
    rows = (
        DailyRate.objects.filter(
            room_type__property=prop,
            date__gte=scan.today,
            date__lt=scan.today + timedelta(days=RATE_HORIZON_DAYS),
        )
        .select_related("room_type", "rate_plan")
        .order_by("room_type__sort_order", "room_type__code", "date")
    )
    defaults = {
        (item.room_type_id, item.rate_plan_id): item.price
        for item in RoomTypeRateDefaults.objects.filter(room_type__property=prop)
    }
    bounds = {}
    if PriceBounds is not None:
        bounds = {
            (item.room_type_id, item.rate_plan_id): (item.min_price, item.max_price)
            for item in PriceBounds.objects.filter(room_type__property=prop)
        }
    grouped: dict[tuple, list] = defaultdict(list)
    for row in rows:
        pair = (row.room_type_id, row.rate_plan_id)
        low, high = bounds.get(pair, (None, None))
        floor = defaults.get(pair)
        too_low = (low is not None and row.price < low) or (
            floor is not None and floor > 0 and row.price < floor * RATE_FLOOR_PERCENT / 100
        )
        too_high = high is not None and row.price > high
        if too_low or too_high:
            grouped[pair].append(row)
    findings = []
    for (room_type_id, plan_id), flagged in grouped.items():
        room_type, plan = flagged[0].room_type, flagged[0].rate_plan
        dates = [row.date.isoformat() for row in flagged]
        prices = sorted({row.price for row in flagged})
        findings.append(
            Finding(
                rule="rate_out_of_bounds",
                key=f"{room_type_id}:{plan_id}",
                severity="warning",
                title=f"Tarifa fuera de rango en {room_type.code}",
                message=(
                    f"{len(dates)} noche(s) de {room_type.code} ({plan.code}) tienen un precio fuera de los "
                    "límites o por debajo del 30 % del precio base: "
                    f"{', '.join(_money(p, prop.currency) for p in prices[:4])}. Primera fecha: "
                    f"{nlp.format_date(flagged[0].date)}."
                ),
                link=f"/app/rates?start={dates[0]}",
                data={"room_type": room_type.code, "rate_plan": plan.code, "dates": dates[:31]},
                per_object=False,
            )
        )
    return findings


def unposted_nights(scan: Scan) -> list[Finding]:
    from apps.bookings.models import Stay
    from apps.core.dates import nights
    from apps.finance.models import Charge

    stays = list(
        Stay.objects.filter(
            reservation__property=scan.property, status="checked_in", checkin_date__lt=scan.today
        ).select_related("reservation__booker", "room")
    )
    posted = defaultdict(set)
    for stay_id, night in Charge.objects.filter(
        stay__in=stays, kind="room", voided_at__isnull=True, night_date__lt=scan.today
    ).values_list("stay_id", "night_date"):
        posted[stay_id].add(night)
    findings = []
    for stay in stays:
        missing = [
            night
            for night in nights(stay.checkin_date, min(stay.checkout_date, scan.today))
            if night not in posted[stay.pk]
        ]
        if not missing:
            continue
        reservation = stay.reservation
        room = f"la {stay.room.number}" if stay.room_id else "su habitación"
        findings.append(
            Finding(
                rule="unposted_nights",
                key=str(stay.pk),
                severity="warning",
                title=f"Noches sin cargo: {reservation.code}",
                message=(
                    f"{reservation.booker.full_name} ({room}) tiene {len(missing)} noche(s) sin cargo de "
                    f"alojamiento después de la auditoría nocturna, desde el {nlp.format_date(missing[0])}."
                ),
                link=f"/app/reservations/{reservation.pk}",
                data={
                    "stay_id": str(stay.pk),
                    "code": reservation.code,
                    "nights": [n.isoformat() for n in missing],
                },
            )
        )
    return findings


def vip_room_not_ready(scan: Scan) -> list[Finding]:
    from apps.bookings.models import Stay

    stays = (
        Stay.objects.filter(
            reservation__property=scan.property,
            status="confirmed",
            checkin_date=scan.today,
            reservation__booker__is_vip=True,
            room__isnull=False,
        )
        .exclude(room__housekeeping_status__in=["clean", "inspected"])
        .select_related("reservation__booker", "room")
    )
    findings = []
    for stay in stays:
        reservation = stay.reservation
        eta = reservation.eta or scan.property.check_in_time
        if scan.at_local(scan.today, eta) - scan.now > VIP_WINDOW:
            continue
        findings.append(
            Finding(
                rule="vip_room_not_ready",
                key=str(stay.pk),
                severity="critical",
                title=f"VIP llega pronto y la {stay.room.number} no está lista",
                message=(
                    f"{reservation.booker.full_name} (VIP) llega hacia las {eta:%H:%M} y la habitación "
                    f"{stay.room.number} está {stay.room.get_housekeeping_status_display().lower()}. "
                    "Prioriza su limpieza o cámbiala de habitación."
                ),
                link=f"/app/reservations/{reservation.pk}",
                data={
                    "stay_id": str(stay.pk),
                    "code": reservation.code,
                    "room": stay.room.number,
                    "eta": f"{eta:%H:%M}",
                },
            )
        )
    return findings


def missing_tra(scan: Scan) -> list[Finding]:
    from django.db.models import Exists, F, OuterRef, Subquery

    from apps.bookings.models import Stay

    TraRegistration = optional_model("compliance.TraRegistration")
    if TraRegistration is None:
        return []
    registered = TraRegistration.objects.filter(status="registered").values("stay_id")
    # Only stays with someone to register (like compliance's `lodged_guests`): the occupants of the stay, or
    # the booker in the reservation's first stay. The other beds/rooms of a booking whose companions were
    # never named have no TRA to send (compliance reports that missing data itself).
    first_stay = Stay.objects.filter(reservation_id=OuterRef("reservation_id")).order_by("created_at", "pk")
    has_occupants = Stay.occupants.through.objects.filter(stay_id=OuterRef("pk"))
    stays = (
        Stay.objects.filter(
            reservation__property=scan.property,
            status__in=["checked_in", "checked_out"],
            checked_in_at__gte=scan.now - LOOKBACK,
            checked_in_at__lte=scan.now - TRA_GRACE,
        )
        .exclude(pk__in=registered)
        .annotate(first_pk=Subquery(first_stay.values("pk")[:1]), has_occupants=Exists(has_occupants))
        .filter(Q(has_occupants=True) | Q(pk=F("first_pk")))
        .select_related("reservation__booker", "room")
    )
    return [
        Finding(
            rule="missing_tra",
            key=str(stay.pk),
            severity="warning",
            title=f"Check-in sin TRA: {stay.reservation.code}",
            message=(
                f"{stay.reservation.booker.full_name} hizo check-in hace más de 2 horas y su Tarjeta de "
                "Registro Alojamiento (TRA) no está registrada. Revisa los datos que faltan en Legal."
            ),
            link=f"/app/reservations/{stay.reservation_id}",
            data={"stay_id": str(stay.pk), "code": stay.reservation.code},
        )
        for stay in stays
    ]


def missing_invoice(scan: Scan) -> list[Finding]:
    from django.db.models import Max

    from apps.bookings.models import Reservation

    Invoice = optional_model("compliance.Invoice")
    if Invoice is None:
        return []
    ComplianceSettings = optional_model("compliance.ComplianceSettings")
    if ComplianceSettings is not None:
        settings_row = ComplianceSettings.objects.filter(property=scan.property).first()
        if settings_row is not None and not settings_row.auto_issue_invoices:
            return []
    issued = Invoice.objects.filter(kind="invoice", status__in=["issued", "accepted"]).values(
        "reservation_id"
    )
    reservations = (
        Reservation.objects.filter(property=scan.property, status="checked_out")
        .annotate(last_out=Max("stays__checked_out_at"))
        .filter(last_out__gte=scan.now - LOOKBACK, last_out__lte=scan.now - INVOICE_GRACE)
        .exclude(pk__in=issued)
        .select_related("booker")
    )
    return [
        Finding(
            rule="missing_invoice",
            key=str(reservation.pk),
            severity="warning",
            title=f"Salida sin factura: {reservation.code}",
            message=(
                f"{reservation.booker.full_name} hizo check-out hace más de una hora y la factura "
                f"electrónica de {reservation.code} no se ha emitido."
            ),
            link=f"/app/reservations/{reservation.pk}",
            data={"reservation_id": str(reservation.pk), "code": reservation.code},
        )
        for reservation in reservations
    ]


def cash_difference(scan: Scan) -> list[Finding]:
    from apps.finance.models import CashShift

    shifts = (
        CashShift.objects.filter(property=scan.property, closed_at__gte=scan.now - LOOKBACK)
        .filter(Q(difference__gt=CASH_TOLERANCE) | Q(difference__lt=-CASH_TOLERANCE))
        .select_related("user")
    )
    findings = []
    for shift in shifts:
        word = "faltante" if shift.difference < 0 else "sobrante"
        findings.append(
            Finding(
                rule="cash_difference",
                key=str(shift.pk),
                severity="warning",
                title=f"Diferencia de caja de {_money(abs(shift.difference), scan.property.currency)}",
                message=(
                    f"El turno de caja de {shift.user.full_name or shift.user.email} cerró con un {word} de "
                    f"{_money(abs(shift.difference), scan.property.currency)} (esperado "
                    f"{_money(shift.expected_cash, scan.property.currency)}, contado "
                    f"{_money(shift.counted_cash, scan.property.currency)})."
                ),
                link="/app/cashier",
                data={"cash_shift_id": str(shift.pk), "difference": f"{shift.difference:.2f}"},
            )
        )
    return findings


def oversold(scan: Scan) -> list[Finding]:
    from django.db.models import F

    from apps.bookings.models import InventoryDay

    rows = (
        InventoryDay.objects.filter(
            property=scan.property,
            date__gte=scan.today,
            date__lt=scan.today + timedelta(days=OVERSOLD_HORIZON_DAYS),
            sold_units__gt=F("total_units"),
        )
        .select_related("room_type")
        .order_by("room_type__sort_order", "room_type__code", "date")
    )
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.room_type_id].append(row)
    findings = []
    for room_type_id, flagged in grouped.items():
        room_type = flagged[0].room_type
        worst = max(row.sold_units - row.total_units for row in flagged)
        findings.append(
            Finding(
                rule="oversold",
                key=str(room_type_id),
                severity="critical",
                title=f"Sobreventa en {room_type.code}",
                message=(
                    f"{room_type.code} tiene más noches vendidas que unidades en {len(flagged)} fecha(s) "
                    f"(hasta {worst} de más), desde el {nlp.format_date(flagged[0].date)}. Reubica o "
                    "contacta a los huéspedes."
                ),
                link=f"/app/calendar?start={flagged[0].date.isoformat()}",
                data={"room_type": room_type.code, "dates": [row.date.isoformat() for row in flagged][:31]},
                per_object=False,
            )
        )
    return findings


RULES = [
    unguaranteed_arrival,
    duplicate_payment,
    rate_out_of_bounds,
    unposted_nights,
    vip_room_not_ready,
    missing_tra,
    missing_invoice,
    cash_difference,
    oversold,
]


# ---- the scan ----------------------------------------------------------------------------------------------


def _dismissed(prop, findings, now) -> set[str]:
    keys = [finding.dedupe_key for finding in findings]
    dismissed = set()
    aggregated = {finding.dedupe_key for finding in findings if not finding.per_object}
    for key, resolved_at in Alert.objects.filter(
        property=prop, dedupe_key__in=keys, resolved_by__isnull=False
    ).values_list("dedupe_key", "resolved_at"):
        if key not in aggregated or (resolved_at and now - resolved_at < DISMISSED_FOR):
            dismissed.add(key)
    return dismissed


def scan_anomalies(prop) -> dict:
    """Run every rule for the hotel; returns `{"raised", "resolved", "by_rule", "skipped"}`."""
    scan = Scan(prop)
    findings, failed = [], []
    for rule in RULES:
        try:
            findings.extend(rule(scan))
        except Exception:  # one broken rule must not hide the others
            logger.exception("Anomaly rule %s failed for %s", rule.__name__, prop.pk)
            failed.append(rule.__name__)
    dismissed = _dismissed(prop, findings, scan.now)
    current = []
    for finding in findings:
        if finding.dedupe_key in dismissed:
            continue
        raise_alert(
            property=prop,
            kind=finding.rule,
            severity=finding.severity,
            title=finding.title,
            message=finding.message,
            link=finding.link,
            dedupe_key=finding.dedupe_key,
            data={"rule": finding.rule, **finding.data},
            source="ai",
        )
        current.append(finding)
    stale = Alert.objects.filter(
        property=prop, resolved_at__isnull=True, dedupe_key__startswith=PREFIX
    ).exclude(dedupe_key__in=[finding.dedupe_key for finding in current])
    if failed:  # a rule that failed cannot say its alerts are gone
        stale = stale.exclude(kind__in=failed)
    resolved = stale.update(resolved_at=scan.now, updated_at=scan.now)
    return {
        "raised": len(current),
        "resolved": resolved,
        "by_rule": dict(Counter(finding.rule for finding in current)),
        "skipped": len(findings) - len(current),
        "failed_rules": failed,
    }


# ---- daily brief -------------------------------------------------------------------------------------------

BRIEF_SCHEMA = {
    "title": "daily_brief",
    "type": "object",
    "properties": {"text": {"type": "string", "description": "Resumen en viñetas Markdown (máximo 6)"}},
    "required": ["text"],
}
BRIEF_SYSTEM = (
    "Eres el copiloto de un hotel. Con los datos del día (JSON) escribe un resumen para el equipo de la "
    "mañana: máximo 6 viñetas Markdown cortas, en español, con cifras concretas; primero lo urgente (alertas "
    "críticas, llegadas VIP, habitaciones sin asignar, saldos por cobrar en salidas) y al final la "
    "ocupación. No inventes datos que no estén en el JSON."
)


def daily_facts(prop) -> dict:
    from apps.bookings.models import InventoryDay, Stay
    from apps.bookings.services.availability import availability
    from apps.bookings.services.queries import with_balance

    day = prop.business_date
    stays = Stay.objects.filter(reservation__property=prop)
    arriving = stays.filter(checkin_date=day, status__in=["tentative", "confirmed", "checked_in"])
    departing = stays.filter(checkout_date=day, status__in=["checked_in", "checked_out"])
    availability(property=prop, checkin=day, checkout=day + timedelta(days=1))  # materializes the day
    inventory = InventoryDay.objects.filter(property=prop, date=day, room_type__is_active=True).aggregate(
        sold=Sum("sold_units"), total=Sum("total_units"), blocked=Sum("blocked_units")
    )
    sellable = (inventory["total"] or 0) - (inventory["blocked"] or 0)
    from apps.bookings.models import Reservation

    departing_reservations = with_balance(
        Reservation.objects.filter(pk__in=departing.values("reservation_id"))
    )
    alerts = Alert.objects.filter(property=prop, resolved_at__isnull=True).exclude(kind="daily_brief")
    top = sorted(
        alerts.order_by("-created_at")[:20],
        key=lambda alert: {"critical": 0, "warning": 1}.get(alert.severity, 2),
    )[:3]
    return {
        "date": day.isoformat(),
        "hotel": prop.name,
        "currency": prop.currency,
        "arrivals": arriving.values("reservation_id").distinct().count(),
        "arrivals_vip": arriving.filter(reservation__booker__is_vip=True)
        .values("reservation_id")
        .distinct()
        .count(),
        "arrivals_unassigned": arriving.filter(
            room__isnull=True, status__in=["tentative", "confirmed"]
        ).count(),
        "departures": departing.values("reservation_id").distinct().count(),
        "departures_with_balance": sum(1 for item in departing_reservations if (item.balance or 0) > 0),
        "in_house": stays.filter(status="checked_in").count(),
        "occupancy_pct": round((inventory["sold"] or 0) * 100 / sellable, 1) if sellable else 0,
        "units_sold": inventory["sold"] or 0,
        "units_total": sellable,
        "open_alerts": {
            "critical": alerts.filter(severity="critical").count(),
            "warning": alerts.filter(severity="warning").count(),
            "info": alerts.filter(severity="info").count(),
            "top": [alert.title for alert in top],
        },
    }


def compose_brief(facts: dict) -> str:
    lines = [
        f"- **{facts['arrivals']} llegadas** hoy"
        + (f" ({facts['arrivals_vip']} VIP)" if facts.get("arrivals_vip") else "")
        + (
            f", {facts['arrivals_unassigned']} sin habitación asignada"
            if facts.get("arrivals_unassigned")
            else ""
        )
        + ".",
        f"- **{facts['departures']} salidas**"
        + (
            f", {facts['departures_with_balance']} con saldo por cobrar"
            if facts.get("departures_with_balance")
            else ""
        )
        + ".",
        f"- {facts['in_house']} huéspedes en casa; ocupación del {facts['occupancy_pct']} % "
        f"({facts['units_sold']}/{facts['units_total']}).",
    ]
    alerts = facts.get("open_alerts") or {}
    if alerts.get("critical") or alerts.get("warning"):
        lines.append(
            f"- Alertas abiertas: {alerts.get('critical', 0)} críticas y {alerts.get('warning', 0)} por "
            "revisar" + (f" (p. ej. «{alerts['top'][0]}»)." if alerts.get("top") else ".")
        )
    return "\n".join(lines)


@register_structured("daily_brief")
def _simulated_brief(prompt: str, system: str | None) -> dict | None:
    try:
        facts = json.loads(prompt)
    except ValueError:
        return None
    return {"text": compose_brief(facts)}


def daily_brief(prop) -> Alert:
    facts = daily_facts(prop)
    result = llm_for(prop, "daily_brief").generate(
        [{"role": "user", "content": json.dumps(facts, ensure_ascii=False)}],
        system=BRIEF_SYSTEM,
        response_schema=BRIEF_SCHEMA,
        temperature=0.3,
    )
    text = ""
    if isinstance(result.data, dict):
        text = str(result.data.get("text") or "").strip()
    text = text or compose_brief(facts)
    Alert.objects.filter(
        property=prop, kind="daily_brief", resolved_at__isnull=True, dedupe_key__startswith="ai:daily_brief:"
    ).exclude(dedupe_key=f"ai:daily_brief:{facts['date']}").update(
        resolved_at=timezone.now(), updated_at=timezone.now()
    )
    return raise_alert(
        property=prop,
        kind="daily_brief",
        severity="info",
        title=f"Resumen del día · {nlp.format_date(prop.business_date)}",
        message=text[:4000],
        link="/app",
        dedupe_key=f"ai:daily_brief:{facts['date']}",
        data={"facts": facts, "simulated": bool(result.simulated)},
        source="ai",
    )
