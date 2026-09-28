"""Query parameters of ``GET /api/v1/reports/<id>/`` (validated once, shared by JSON and exports).

``start``/``end`` (``YYYY-MM-DD``, both inclusive business dates; defaults to the report's preset),
``compare=previous_period|previous_year``, ``group_by`` (per report), ``days`` (pickup window),
``lang=es|en`` (default: the user's language) and ``format=csv|xlsx|pdf`` (default: JSON).
"""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from apps.core.errors import DomainError
from apps.reports.engine import comparison_range

if TYPE_CHECKING:
    from apps.reports.registry import ReportDef

MAX_RANGE_DAYS = 731
FORMATS = ("csv", "xlsx", "pdf")
COMPARE_MODES = ("previous_period", "previous_year")
LANGS = ("es", "en")
PICKUP_WINDOW_MAX = 90


def preset_range(preset: str | None, today: date) -> tuple[date, date] | None:
    """Default ranges relative to the business date (both ends inclusive; weeks start on Monday)."""
    if preset == "today":
        return today, today
    if preset == "yesterday":
        day = today - timedelta(days=1)
        return day, day
    if preset == "this_week":
        monday = today - timedelta(days=today.weekday())
        return monday, monday + timedelta(days=6)
    if preset == "this_month":
        return today.replace(day=1), today.replace(day=monthrange(today.year, today.month)[1])
    if preset == "last_month":
        last = today.replace(day=1) - timedelta(days=1)
        return last.replace(day=1), last
    if preset == "last30":
        return today - timedelta(days=29), today
    for prefix, length in (("next14", 14), ("next30", 30), ("next90", 90)):
        if preset == prefix:
            return today, today + timedelta(days=length - 1)
    return None


@dataclass(frozen=True)
class ReportParams:
    prop: Any
    user: Any
    lang: str
    start: date | None
    end: date | None
    compare: str | None
    compare_start: date | None
    compare_end: date | None
    group_by: str | None
    days: int | None
    fmt: str | None

    @property
    def currency(self) -> str:
        return self.prop.currency or "COP"

    @property
    def business_date(self) -> date:
        return self.prop.business_date

    @property
    def compared(self) -> bool:
        return self.compare_start is not None

    @property
    def range_days(self) -> int:
        if self.start is None or self.end is None:
            return 0
        return (self.end - self.start).days + 1


def _parse_date(raw: str, name: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise DomainError(
            "Fecha inválida: usa el formato AAAA-MM-DD", code="invalid_date", fields={name: ["AAAA-MM-DD"]}
        ) from None


def parse_params(request, report: ReportDef) -> ReportParams:
    """Parameters of an API request (``X-Property-Id`` property, the user's language by default)."""
    return make_params(report, request.property, request.user, request.query_params)


def make_params(report: ReportDef, prop, user=None, query: Mapping | None = None) -> ReportParams:
    """Validates ``query`` (any mapping with ``.get``: DRF query params or a plain dict) for ``report``.

    Also used outside HTTP (the seed smoke check, other apps that need a report's figures), so every caller
    gets exactly the same defaults and validation as the API."""
    query = query or {}
    lang = (query.get("lang") or getattr(user, "language", "") or "es").lower()[:2]
    if lang not in LANGS:
        raise DomainError("Idioma no soportado", code="invalid_lang", fields={"lang": ["es | en"]})

    fmt = (query.get("format") or "").lower() or None
    if fmt in ("json",):
        fmt = None
    if fmt is not None and fmt not in FORMATS:
        raise DomainError("Formato no soportado", code="invalid_format", fields={"format": list(FORMATS)})

    start = end = None
    if report.range_kind != "none":
        raw_start, raw_end = query.get("start"), query.get("end")
        if raw_start or raw_end:
            if not (raw_start and raw_end):
                raise DomainError(
                    "Indica la fecha inicial y la final",
                    code="invalid_range",
                    fields={"start": [], "end": []},
                )
            start, end = _parse_date(raw_start, "start"), _parse_date(raw_end, "end")
        else:
            start, end = preset_range(report.default_preset, prop.business_date) or (
                prop.business_date,
                prop.business_date,
            )
        if end < start:
            raise DomainError("La fecha final es anterior a la inicial", code="invalid_range")
        if (end - start).days + 1 > MAX_RANGE_DAYS:
            raise DomainError(
                f"El rango máximo es de {MAX_RANGE_DAYS} días", code="range_too_long", max_days=MAX_RANGE_DAYS
            )

    compare = (query.get("compare") or "").lower() or None
    if compare in ("none",):
        compare = None
    if compare is not None:
        if compare not in COMPARE_MODES or not report.compare:
            raise DomainError(
                "Comparación no disponible para este reporte",
                code="invalid_compare",
                fields={"compare": list(COMPARE_MODES) if report.compare else []},
            )
    compare_start = compare_end = None
    if compare and start and end:
        compare_start, compare_end = comparison_range(start, end, compare)

    group_by = (query.get("group_by") or "").lower() or None
    if group_by is None:
        group_by = report.default_group_by
    elif group_by not in report.group_by:
        raise DomainError(
            "Agrupación no disponible para este reporte",
            code="invalid_group_by",
            fields={"group_by": list(report.group_by)},
        )

    days = None
    if report.window_param:
        raw_days = query.get("days") or str(report.window_default)
        try:
            days = int(raw_days)
        except ValueError:
            days = 0
        if not 1 <= days <= PICKUP_WINDOW_MAX:
            raise DomainError(
                f"La ventana debe estar entre 1 y {PICKUP_WINDOW_MAX} días",
                code="invalid_days",
                fields={"days": [f"1–{PICKUP_WINDOW_MAX}"]},
            )

    return ReportParams(
        prop=prop,
        user=user,
        lang=lang,
        start=start,
        end=end,
        compare=compare if compare_start else None,
        compare_start=compare_start,
        compare_end=compare_end,
        group_by=group_by,
        days=days,
        fmt=fmt,
    )
