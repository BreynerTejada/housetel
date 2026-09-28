"""Catalog of reports: id → category, permission, filters it accepts and the function that builds it."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from apps.reports.builders import financial, operations, performance

PERFORMANCE, OPERATIONS, FINANCE, TAXES = "performance", "operations", "finance", "taxes"
CATEGORY_PERMISSIONS = {
    PERFORMANCE: "reports.performance",
    OPERATIONS: "reports.operational",
    FINANCE: "reports.financial",
    TAXES: "reports.financial",
}
TIME_GROUPS = ("day", "week", "month")


@dataclass(frozen=True)
class ReportDef:
    id: str
    category: str
    build: Callable
    # past (history) | future (on the books) | date (a day, default today) | any | none (snapshot)
    range_kind: str = "past"
    default_preset: str | None = "this_month"
    compare: bool = False
    group_by: tuple[str, ...] = ()
    default_group_by: str | None = None
    window_param: bool = False  # `days` (pickup window)
    window_default: int = 7

    @property
    def permission(self) -> str:
        return CATEGORY_PERMISSIONS[self.category]

    def as_dict(self, allowed: bool) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "permission": self.permission,
            "allowed": allowed,
            "range_kind": self.range_kind,
            "default_preset": self.default_preset,
            "compare": self.compare,
            "group_by": list(self.group_by),
            "default_group_by": self.default_group_by,
            "window_param": self.window_param,
            "window_default": self.window_default if self.window_param else None,
        }


REPORTS: dict[str, ReportDef] = {
    report.id: report
    for report in [
        # Performance
        ReportDef(
            "performance",
            PERFORMANCE,
            performance.build_performance,
            "any",
            "this_month",
            True,
            TIME_GROUPS,
            "day",
        ),
        ReportDef(
            "revenue-by-segment",
            PERFORMANCE,
            performance.build_revenue_by_segment,
            "any",
            "this_month",
            True,
            performance.SEGMENT_DIMENSIONS,
            "source",
        ),
        ReportDef("pickup", PERFORMANCE, performance.build_pickup, "future", "next30", window_param=True),
        ReportDef(
            "forecast", PERFORMANCE, performance.build_forecast, "future", "next90", False, TIME_GROUPS, "day"
        ),
        ReportDef("cancellations", PERFORMANCE, performance.build_cancellations, "past", "last30", True),
        ReportDef("booking-window", PERFORMANCE, performance.build_booking_window, "any", "last30", True),
        ReportDef(
            "guests-by-nationality", PERFORMANCE, performance.build_guests_by_nationality, "any", "this_month"
        ),
        # Operations
        ReportDef("arrivals", OPERATIONS, operations.build_arrivals, "date", "today"),
        ReportDef("departures", OPERATIONS, operations.build_departures, "date", "today"),
        ReportDef("in-house", OPERATIONS, operations.build_in_house, "date", "today"),
        ReportDef("no-shows", OPERATIONS, operations.build_no_shows, "past", "last30"),
        ReportDef("housekeeping-status", OPERATIONS, operations.build_housekeeping_status, "none", None),
        ReportDef("occupancy-outlook", OPERATIONS, performance.build_occupancy_outlook, "future", "next14"),
        # Finance
        ReportDef(
            "daily-revenue",
            FINANCE,
            financial.build_daily_revenue,
            "past",
            "last30",
            True,
            TIME_GROUPS,
            "day",
        ),
        ReportDef("payments-by-method", FINANCE, financial.build_payments_by_method, "past", "last30", True),
        ReportDef("cash-shifts", FINANCE, financial.build_cash_shifts, "past", "last30"),
        ReportDef("receivables", FINANCE, financial.build_receivables, "none", None),
        # Taxes
        ReportDef("taxes", TAXES, financial.build_taxes, "past", "last_month", True),
    ]
}


def get_report(report_id: str) -> ReportDef | None:
    return REPORTS.get(report_id)
