"""Staff API of the reports (`/api/v1/reports/…`, plan C10). Scoped to `X-Property-Id` by `apps.core.tenancy`.

- ``GET /api/v1/reports/`` → the catalog (every report with its category, permission and filters; ``allowed``
  says whether the current user may open it).
- ``GET /api/v1/reports/<id>/?start&end&compare&group_by&days&lang[&format=csv|xlsx|pdf]`` → the report as
JSON
  (or a file). The permission depends on the report's category (``reports.performance``,
  ``reports.operational`` or ``reports.financial``).
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from apps.core.permissions import codes_match
from apps.core.tenancy import PropertyScopedAPIView
from apps.reports.exporters import export_report
from apps.reports.params import parse_params
from apps.reports.registry import REPORTS, get_report
from apps.reports.service import report_payload, run_report


class ReportCatalogView(PropertyScopedAPIView):
    """`GET /api/v1/reports/` → `[{id, category, permission, allowed, range_kind, default_preset, compare,
    group_by, default_group_by, window_param, window_default}]`."""

    required_permissions: dict = {}

    @extend_schema(operation_id="reports_catalog", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        granted = request.membership.role.permissions
        return Response(
            [report.as_dict(codes_match(granted, report.permission)) for report in REPORTS.values()]
        )


class ReportView(PropertyScopedAPIView):
    """`GET /api/v1/reports/<report_id>/` → `{id, title, range, compare, summary, charts, tables, notes, …}`
    or, with `format=csv|xlsx|pdf`, the file."""

    def get_required_permission(self):
        report = get_report(self.kwargs.get("report_id", ""))
        return report.permission if report else None

    def perform_content_negotiation(self, request, force=False):
        # `?format=` selects the export file here, not a DRF renderer: always answer (and fail) in JSON.
        renderer = JSONRenderer()
        return renderer, renderer.media_type

    @extend_schema(
        operation_id="reports_report",
        parameters=[
            OpenApiParameter("start", OpenApiTypes.DATE, description="Primer día (incluido)"),
            OpenApiParameter("end", OpenApiTypes.DATE, description="Último día (incluido)"),
            OpenApiParameter("compare", str, enum=["previous_period", "previous_year"]),
            OpenApiParameter(
                "group_by", str, description="day|week|month · source|channel|room_type|rate_plan"
            ),
            OpenApiParameter("days", int, description="Ventana de pickup (1–90)"),
            OpenApiParameter("lang", str, enum=["es", "en"]),
            OpenApiParameter("format", str, enum=["csv", "xlsx", "pdf"]),
        ],
        responses={200: OpenApiTypes.OBJECT, (200, "text/csv"): OpenApiTypes.BINARY},
    )
    def get(self, request, report_id):
        report = get_report(report_id)
        if report is None:
            raise NotFound("Reporte no encontrado")
        params = parse_params(request, report)
        result = run_report(report, params)
        if params.fmt:
            return export_report(report, params, result, params.fmt)
        return Response(report_payload(report, params, result))
