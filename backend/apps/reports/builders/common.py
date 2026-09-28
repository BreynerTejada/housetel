"""Helpers shared by the report builders: language picks, readable dates, range notes and small queries."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.bookings.models import Reservation
from apps.bookings.services.queries import with_balance
from apps.core.i18n import t
from apps.reports.engine import inclusive_days
from apps.reports.labels import tr
from apps.reports.output import DATE, MONTH, Column

ZERO = Decimal("0")
MONTHS = {
    "es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}


def L(lang: str, es: str, en: str) -> str:
    return en if lang == "en" else es


def day_text(day: date, lang: str) -> str:
    """ "1 sep 2026" / "Sep 1, 2026"."""
    month = MONTHS["en" if lang == "en" else "es"][day.month - 1]
    return f"{month} {day.day}, {day.year}" if lang == "en" else f"{day.day} {month} {day.year}"


def month_text(day: date, lang: str) -> str:
    """ "sep 2026" / "Sep 2026"."""
    return f"{MONTHS['en' if lang == 'en' else 'es'][day.month - 1]} {day.year}"


def range_note(p) -> str:
    """Spells out the inclusive range the figures cover (the first note of every dated report)."""
    if p.start is None:
        return L(
            p.lang,
            f"Foto del momento a la fecha de negocio {day_text(p.business_date, 'es')}.",
            f"Snapshot as of business date {day_text(p.business_date, 'en')}.",
        )
    nights = p.range_days
    return L(
        p.lang,
        f"Rango: del {day_text(p.start, 'es')} al {day_text(p.end, 'es')}, ambos días incluidos "
        f"({nights} {'día' if nights == 1 else 'días'} de fecha de negocio). "
        f"Fecha de negocio actual: {day_text(p.business_date, 'es')}.",
        f"Range: {day_text(p.start, 'en')} to {day_text(p.end, 'en')}, both days included "
        f"({nights} business {'day' if nights == 1 else 'days'}). "
        f"Current business date: {day_text(p.business_date, 'en')}.",
    )


def compare_note(p) -> str | None:
    if not p.compared:
        return None
    mode = (
        L(p.lang, "periodo anterior", "previous period")
        if p.compare == "previous_period"
        else L(p.lang, "mismo periodo del año anterior", "same period last year")
    )
    return L(
        p.lang,
        f"Comparación ({mode}): del {day_text(p.compare_start, 'es')} al {day_text(p.compare_end, 'es')}.",
        f"Comparison ({mode}): {day_text(p.compare_start, 'en')} to {day_text(p.compare_end, 'en')}.",
    )


def prev_label(p) -> str:
    """ "periodo anterior" / "año anterior" (suffix of comparison columns and series)."""
    return tr("vs_previous_year" if p.compare == "previous_year" else "vs_previous_period", p.lang)


def prev_title(p) -> str:
    label = prev_label(p)
    return label[:1].upper() + label[1:]


def base_notes(p, *definitions: str) -> list[str]:
    notes = [range_note(p)]
    comparison = compare_note(p)
    if comparison:
        notes.append(comparison)
    notes.extend(definition for definition in definitions if definition)
    return notes


def today_marker(p) -> dict | None:
    """The business date as a chart marker when it falls inside the range."""
    if p.start is None or not (p.start <= p.business_date <= p.end):
        return None
    return {"x": p.business_date.isoformat(), "label": tr("today", p.lang)}


def period_column(p, key: str = "date") -> Column:
    """First column of a time table: day, week (its Monday) or month."""
    group = p.group_by or "day"
    if group == "month":
        return Column(key, tr("month", p.lang), MONTH)
    if group == "week":
        return Column(key, L(p.lang, "Semana (desde el lunes)", "Week (from Monday)"), DATE)
    return Column(key, tr("date", p.lang), DATE)


def period_table_title(p) -> str:
    return tr({"week": "t_weekly", "month": "t_monthly"}.get(p.group_by or "day", "t_daily"), p.lang)


def all_days(p) -> list[date]:
    return inclusive_days(p.start, p.end)


def balances(reservation_ids) -> dict:
    """``{reservation_id: balance}`` (same rule as ``finance.reservation_balance``, in one query)."""
    ids = list({rid for rid in reservation_ids if rid})
    if not ids:
        return {}
    return dict(with_balance(Reservation.objects.filter(pk__in=ids)).values_list("id", "balance"))


def guest_name(guest) -> str:
    if guest is None:
        return ""
    full = getattr(guest, "full_name", None)
    if full:
        return full
    return f"{guest.first_name} {guest.last_name}".strip()


def i18n_name(value, lang: str) -> str:
    return t(value, lang) if value else ""


def room_label(stay) -> str:
    """ "101", or "D1 · A" for a dorm bed; empty when unassigned."""
    if stay.room_id is None:
        return ""
    number = stay.room.number
    return f"{number} · {stay.bed.label}" if stay.bed_id else number
