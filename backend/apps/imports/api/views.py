"""Importer API (`/api/v1/imports/`, header `X-Property-Id`, permission `imports.run`; pilot plan P5).

| Method and path | What |
|---|---|
| `GET catalog/` | kinds, fields of each kind, presets, options and limits |
| `GET jobs/` · `POST jobs/` (multipart) | history · upload a CSV/XLSX → job with the suggested mapping |
| `GET/PATCH/DELETE jobs/{id}/` | detail · save mapping/values/options and validate · discard (not run) |
| `GET jobs/{id}/rows/` | rows with issues and results (filters `status`, `outcome`, `dry_outcome`, `q`) |
| `POST jobs/{id}/dry-run/` · `run/` · `revert/` | queue the simulation, the import or the rollback |
| `GET jobs/{id}/revert-preview/` | what a rollback would cancel |
| `GET jobs/{id}/report/` | CSV report (`lang=es|en`, `only=issues`) |
| `GET templates/{kind}/` | template or example file (`lang`, `format=csv|xlsx`, `example=1`, `preset`) |
"""

from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from apps.core.api.pagination import StandardPagination
from apps.core.errors import DomainError, NotFoundError
from apps.core.tenancy import PropertyScopedAPIView
from apps.imports import reports, samples, services
from apps.imports.api import serializers as s
from apps.imports.catalog import catalog
from apps.imports.models import ImportJob

PERMISSION = "imports.run"


def _param(name: str, description: str, type_=OpenApiTypes.STR) -> OpenApiParameter:
    return OpenApiParameter(name=name, type=type_, location=OpenApiParameter.QUERY, description=description)


def _job(request, pk) -> ImportJob:
    job = (
        ImportJob.objects.select_related(
            "property", "property__organization", "created_by", "run_by", "reverted_by"
        )
        .filter(pk=pk, property=request.property)
        .first()
    )
    if job is None:
        raise NotFoundError("La importación no existe")
    return job


class CatalogView(PropertyScopedAPIView):
    required_permissions = {"get": PERMISSION}

    @extend_schema(operation_id="imports_catalog", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(catalog())


class JobListView(PropertyScopedAPIView):
    """`GET jobs/` history (newest first; `kind`, `status`) · `POST jobs/` multipart `{kind, preset, file,
    source_label?, sheet?}` → 201 detail."""

    required_permissions = {"get": PERMISSION, "post": PERMISSION}
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(
        operation_id="imports_jobs_list",
        parameters=[_param("kind", "guests | reservations | room_types | rooms"), _param("status", "Estado")],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        jobs = ImportJob.objects.filter(property=request.property).select_related("created_by")
        kind = request.query_params.get("kind")
        if kind in ImportJob.Kind.values:
            jobs = jobs.filter(kind=kind)
        wanted = [
            value for value in request.query_params.getlist("status") if value in ImportJob.Status.values
        ]
        if wanted:
            jobs = jobs.filter(status__in=wanted)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(jobs.order_by("-created_at"), request, view=self)
        return paginator.get_paginated_response([services.job_summary(job) for job in page])

    @extend_schema(
        operation_id="imports_jobs_create", request=s.ImportUploadSerializer, responses=OpenApiTypes.OBJECT
    )
    def post(self, request):
        body = s.ImportUploadSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        job = services.create_job(
            request.property,
            user=request.user,
            kind=data["kind"],
            preset=data["preset"],
            upload=data["file"],
            source_label=data.get("source_label", ""),
            sheet=data.get("sheet", ""),
        )
        return Response(services.job_detail(job), status=status.HTTP_201_CREATED)


class JobDetailView(PropertyScopedAPIView):
    """`GET jobs/{id}/` · `PATCH jobs/{id}/` `{mapping?, value_map?, options?, source_label?}` → validates
    every row and answers the detail (400 `mapping_incomplete` + `missing` when required columns are
    unassigned) · `DELETE jobs/{id}/` (only jobs that never ran)."""

    required_permissions = {"get": PERMISSION, "patch": PERMISSION, "delete": PERMISSION}

    @extend_schema(operation_id="imports_jobs_retrieve", responses=OpenApiTypes.OBJECT)
    def get(self, request, pk):
        return Response(services.job_detail(_job(request, pk)))

    @extend_schema(
        operation_id="imports_jobs_partial_update",
        request=s.ImportConfigureSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def patch(self, request, pk):
        job = _job(request, pk)
        body = s.ImportConfigureSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = dict(body.validated_data)
        try:
            job = services.configure(job, data)
        except DomainError as exc:
            if exc.code != "mapping_incomplete":
                raise
            # the mapping was saved: answer the detail too, so the UI shows what is missing
            payload = {"detail": exc.message, "code": exc.code, **exc.extra, "job": services.job_detail(job)}
            return Response(payload, status=status.HTTP_400_BAD_REQUEST)
        return Response(services.job_detail(job))

    @extend_schema(operation_id="imports_jobs_destroy", responses={204: None})
    def delete(self, request, pk):
        services.delete_job(_job(request, pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class JobRowsView(PropertyScopedAPIView):
    required_permissions = {"get": PERMISSION}

    @extend_schema(
        operation_id="imports_jobs_rows",
        parameters=[
            _param("status", "valid | warning | error | skip (repetible)"),
            _param("outcome", "created | updated | skipped | failed | reverted (repetible)"),
            _param("dry_outcome", "create | update | skip | fail (repetible)"),
            _param("issues", "1 = solo filas con observaciones"),
            _param("q", "número de fila, id o lo creado"),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request, pk):
        job = _job(request, pk)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(
            services.rows_queryset(job, request.query_params), request, view=self
        )
        return paginator.get_paginated_response([services.row_json(row) for row in page])


class _StartView(PropertyScopedAPIView):
    required_permissions = {"post": PERMISSION}
    mode = ""

    def post(self, request, pk):
        job = _job(request, pk)
        body = s.ImportConfirmSerializer(data=request.data or {})
        body.is_valid(raise_exception=True)
        job = services.start(job, self.mode, actor=request.user, confirm=body.validated_data["confirm"])
        job.refresh_from_db()
        return Response(services.job_detail(job), status=status.HTTP_202_ACCEPTED)


class JobDryRunView(_StartView):
    mode = ImportJob.Phase.DRY_RUN

    @extend_schema(operation_id="imports_jobs_dry_run", request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        return super().post(request, pk)


class JobRunView(_StartView):
    mode = ImportJob.Phase.RUN

    @extend_schema(
        operation_id="imports_jobs_run", request=s.ImportConfirmSerializer, responses=OpenApiTypes.OBJECT
    )
    def post(self, request, pk):
        return super().post(request, pk)


class JobRevertView(_StartView):
    mode = ImportJob.Phase.REVERT

    @extend_schema(
        operation_id="imports_jobs_revert", request=s.ImportConfirmSerializer, responses=OpenApiTypes.OBJECT
    )
    def post(self, request, pk):
        return super().post(request, pk)


class JobRevertPreviewView(PropertyScopedAPIView):
    required_permissions = {"get": PERMISSION}

    @extend_schema(operation_id="imports_jobs_revert_preview", responses=OpenApiTypes.OBJECT)
    def get(self, request, pk):
        return Response(services.revert_preview(_job(request, pk)))


class JobReportView(PropertyScopedAPIView):
    required_permissions = {"get": PERMISSION}

    @extend_schema(
        operation_id="imports_jobs_report",
        parameters=[
            _param("lang", "es | en"),
            _param("only", "issues = solo filas con errores o advertencias"),
        ],
        responses={(200, "text/csv"): OpenApiTypes.BINARY},
    )
    def get(self, request, pk):
        job = _job(request, pk)
        content, filename = reports.job_report(
            job, lang=request.query_params.get("lang", "es"), only=request.query_params.get("only", "")
        )
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Cache-Control"] = "no-store"
        return response


class TemplateView(PropertyScopedAPIView):
    required_permissions = {"get": PERMISSION}

    def perform_content_negotiation(self, request, force=False):
        # `?format=` picks the file (csv | xlsx), not a DRF renderer (else DRF answers 404 for "xlsx"): errors
        # are always JSON.
        renderer = JSONRenderer()
        return renderer, renderer.media_type

    @extend_schema(
        operation_id="imports_templates",
        parameters=[
            _param("lang", "es | en"),
            _param("format", "csv | xlsx"),
            _param("example", "1 = con filas de ejemplo de esta propiedad"),
            _param("preset", "generic | cloudbeds"),
        ],
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def get(self, request, kind):
        if kind not in ImportJob.Kind.values:
            raise NotFoundError("Tipo de importación desconocido")
        params = request.query_params
        lang = "en" if params.get("lang") == "en" else "es"
        fmt = "xlsx" if params.get("format") == "xlsx" else "csv"
        preset = params.get("preset") if params.get("preset") in ImportJob.Preset.values else "generic"
        content, content_type, filename = samples.build(
            kind,
            lang,
            fmt,
            prop=request.property,
            example=params.get("example") in ("1", "true"),
            preset=preset,
        )
        return samples.response(content, content_type, filename)
