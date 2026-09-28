"""The uniform shape every report returns (JSON, CSV, XLSX and PDF are all rendered from it).

A report is: KPI tiles (``summary``), zero or more ``charts`` and one or more ``tables``, plus ``notes`` with
the definitions used. Builders fill these with Python values (``Decimal`` money, ``date``, ints); ``to_json``
turns them into the API conventions (money as ``"350000.00"`` strings in tables and KPIs, numbers in charts,
ISO dates) and the exporters format them for each file type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.utils import timezone

from apps.core.money import D

CENTS = Decimal("0.01")
ONE_DECIMAL = Decimal("0.1")

# Column / KPI value types
TEXT, DATE, MONTH, DATETIME, NUMBER, MONEY, PERCENT, STATUS, COUNTRY, CODE, BOOLEAN = (
    "text", "date", "month", "datetime", "number", "money", "percent", "status", "country", "code", "boolean",
)  # fmt: skip


@dataclass
class Column:
    key: str
    label: str
    type: str = TEXT
    status_kind: str | None = None  # reservation | room | payment (StatusBadge in the UI)
    link: str | None = None  # "reservation" → the row's `reservation_id`
    labels: dict[str, str] | None = None  # code → label for status/code columns

    def as_dict(self) -> dict:
        data: dict[str, Any] = {"key": self.key, "label": self.label, "type": self.type}
        if self.status_kind:
            data["status_kind"] = self.status_kind
        if self.link:
            data["link"] = self.link
        if self.labels:
            data["labels"] = self.labels
        return data


@dataclass
class Table:
    key: str
    title: str
    columns: list[Column]
    rows: list[dict]
    totals: dict | None = None

    def column(self, key: str) -> Column | None:
        return next((column for column in self.columns if column.key == key), None)


@dataclass
class Series:
    key: str
    label: str
    role: str = "primary"  # primary | compare | stack


@dataclass
class Chart:
    key: str
    title: str
    type: str  # line | column | hbar | stacked_column | status_bar
    x: str
    x_type: str  # date | text
    value_type: str  # money | percent | number
    series: list[Series]
    data: list[dict]
    marker: dict | None = None  # {"x": "2026-09-27", "label": "Hoy"}: the business date
    forecast_from: str | None = None  # first x (ISO date) whose values are forecast


@dataclass
class Kpi:
    key: str
    label: str
    type: str  # money | percent | number
    value: Any
    previous: Any = None
    intent: str = "higher-is-better"  # higher-is-better | lower-is-better | neutral
    unit: str | None = None  # e.g. "days"

    def as_dict(self, compared: bool) -> dict:
        data: dict[str, Any] = {
            "key": self.key,
            "label": self.label,
            "type": self.type,
            "value": json_value(self.value, self.type),
            "intent": self.intent,
        }
        if self.unit:
            data["unit"] = self.unit
        if compared:
            data["previous"] = json_value(self.previous, self.type)
            change, change_pct = kpi_change(self.value, self.previous, self.type)
            data["change"] = json_value(change, self.type) if change is not None else None
            data["change_pct"] = float(change_pct) if change_pct is not None else None
        return data


@dataclass
class ReportResult:
    summary: list[Kpi] = field(default_factory=list)
    charts: list[Chart] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def kpi_change(value, previous, kind: str) -> tuple[Any, Decimal | None]:
    """(absolute change, relative change %). Percent KPIs change in points; relative change needs a base."""
    if value is None or previous is None:
        return None, None
    current, before = D(value), D(previous)
    change = current - before
    if kind == PERCENT:
        change = change.quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP)
    change_pct = None
    if before:
        change_pct = (change * 100 / abs(before)).quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP)
    return change, change_pct


def json_value(value, kind: str):
    """API form of a typed value: money → "123.00", percent → 72.5, dates → ISO, the rest unchanged."""
    if value is None:
        return None
    if kind == MONEY:
        return f"{D(value).quantize(CENTS, rounding=ROUND_HALF_UP):f}"
    if kind == PERCENT:
        return float(D(value).quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP))
    if kind == NUMBER:
        if isinstance(value, Decimal):
            return float(value) if value != value.to_integral_value() else int(value)
        return value
    if isinstance(value, datetime):
        return timezone.localtime(value).isoformat() if timezone.is_aware(value) else value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _chart_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def table_json(table: Table) -> dict:
    types = {column.key: column.type for column in table.columns}

    def row_json(row: dict) -> dict:
        return {key: json_value(value, types.get(key, "")) for key, value in row.items()}

    return {
        "key": table.key,
        "title": table.title,
        "columns": [column.as_dict() for column in table.columns],
        "rows": [row_json(row) for row in table.rows],
        "totals": row_json(table.totals) if table.totals else None,
    }


def chart_json(chart: Chart) -> dict:
    return {
        "key": chart.key,
        "title": chart.title,
        "type": chart.type,
        "x": chart.x,
        "x_type": chart.x_type,
        "value_type": chart.value_type,
        "series": [{"key": s.key, "label": s.label, "role": s.role} for s in chart.series],
        "data": [{key: _chart_value(value) for key, value in row.items()} for row in chart.data],
        "marker": chart.marker,
        "forecast_from": chart.forecast_from,
    }
