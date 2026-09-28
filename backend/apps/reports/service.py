"""Runs a report and shapes its JSON payload (used by the API, the exports and the seed smoke check)."""

from __future__ import annotations

from django.utils import timezone

from apps.reports.labels import report_title
from apps.reports.output import ReportResult, chart_json, table_json
from apps.reports.params import ReportParams
from apps.reports.registry import ReportDef


def run_report(report: ReportDef, params: ReportParams) -> ReportResult:
    return report.build(params)


def report_payload(report: ReportDef, p: ReportParams, result: ReportResult) -> dict:
    prop = p.prop
    return {
        "id": report.id,
        "category": report.category,
        "title": report_title(report.id, p.lang),
        "lang": p.lang,
        "currency": p.currency,
        "property": {"id": str(prop.pk), "name": prop.name, "slug": prop.slug},
        "business_date": p.business_date.isoformat(),
        "range": (
            {"start": p.start.isoformat(), "end": p.end.isoformat(), "days": p.range_days}
            if p.start is not None
            else None
        ),
        "compare": (
            {
                "mode": p.compare,
                "start": p.compare_start.isoformat(),
                "end": p.compare_end.isoformat(),
                "days": (p.compare_end - p.compare_start).days + 1,
            }
            if p.compared
            else None
        ),
        "group_by": p.group_by,
        "params": {"days": p.days} if p.days else {},
        "summary": [kpi.as_dict(p.compared) for kpi in result.summary],
        "charts": [chart_json(chart) for chart in result.charts],
        "tables": [table_json(table) for table in result.tables],
        "notes": result.notes,
        "meta": result.meta,
        "generated_at": timezone.localtime().isoformat(),
    }
