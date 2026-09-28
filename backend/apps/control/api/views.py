"""Control center API (`/api/v1/control/`, header `X-Property-Id`; plan C12).

| Area | Permission |
|---|---|
| integrations (list, detail, PATCH, test) | `control.integrations` |
| automations (list, detail, PATCH, run) and automation-runs | `control.automations` |
| audit (timeline, facets, detail) | `control.audit`; undo also needs `control.audit_undo` |
| alerts (list, count, detail, resolve) | `control.alerts` |

Secrets never appear in any response: integrations only say which secret fields are set; audit changes,
alert data and run details go through `apps.control.services.scrub`.
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response

from apps.control.api import serializers as s
from apps.control.services import alerts as alerts_svc
from apps.control.services import audit as audit_svc
from apps.control.services import automations as automations_svc
from apps.control.services import integrations as integrations_svc
from apps.core.api.pagination import StandardPagination
from apps.core.errors import NotFoundError
from apps.core.models import AutomationRun
from apps.core.permissions import codes_match
from apps.core.tenancy import PropertyScopedAPIView

INTEGRATIONS = "control.integrations"
AUTOMATIONS = "control.automations"
AUDIT = "control.audit"
AUDIT_UNDO = "control.audit_undo"
ALERTS = "control.alerts"


def _param(name: str, description: str, type_=OpenApiTypes.STR) -> OpenApiParameter:
    return OpenApiParameter(name=name, type=type_, location=OpenApiParameter.QUERY, description=description)


def _paginate(view, request, queryset, serialize_page):
    paginator = StandardPagination()
    page = paginator.paginate_queryset(queryset, request, view=view)
    return paginator.get_paginated_response(serialize_page(page))


def _can(request, code: str) -> bool:
    return codes_match(request.membership.role.permissions, code)


# ---- Integrations ----------------------------------------------------------------------------------------


class IntegrationListView(PropertyScopedAPIView):
    """`GET integrations/` → one card per integration kind of the property."""

    required_permissions = {"get": INTEGRATIONS}

    @extend_schema(operation_id="control_integrations_list", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(integrations_svc.list_for(request.property))


class IntegrationDetailView(PropertyScopedAPIView):
    """`GET/PATCH integrations/{kind}/` · PATCH `{mode?, enabled?, config?, secrets?}` (secrets write-only:
    a value sets it, `null` removes it, `""` keeps it)."""

    required_permissions = {"get": INTEGRATIONS, "patch": INTEGRATIONS}

    @extend_schema(operation_id="control_integrations_retrieve", responses=OpenApiTypes.OBJECT)
    def get(self, request, kind):
        return Response(integrations_svc.detail(request.property, kind))

    @extend_schema(
        operation_id="control_integrations_partial_update",
        request=s.IntegrationUpdateSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def patch(self, request, kind):
        body = s.IntegrationUpdateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = dict(body.validated_data)
        # keep explicit nulls in secrets (they remove a stored secret)
        if isinstance(request.data, dict) and isinstance(request.data.get("secrets"), dict):
            data["secrets"] = request.data["secrets"]
        if isinstance(request.data, dict) and isinstance(request.data.get("config"), dict):
            data["config"] = request.data["config"]
        return Response(integrations_svc.update(request.property, kind, data, actor=request.user))


class IntegrationTestView(PropertyScopedAPIView):
    """`POST integrations/{kind}/test/` → runs the provider's `test_connection()` and stores the status."""

    required_permissions = {"post": INTEGRATIONS}

    @extend_schema(operation_id="control_integrations_test", request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, kind):
        return Response(integrations_svc.test(request.property, kind, actor=request.user))


# ---- Automations -----------------------------------------------------------------------------------------


class AutomationListView(PropertyScopedAPIView):
    """`GET automations/` → the property's automations with schedule, state, last run and recent runs."""

    required_permissions = {"get": AUTOMATIONS}

    @extend_schema(operation_id="control_automations_list", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(automations_svc.list_for(request.property))


class AutomationDetailView(PropertyScopedAPIView):
    """`GET/PATCH automations/{code}/` · PATCH `{enabled?, params?}`."""

    required_permissions = {"get": AUTOMATIONS, "patch": AUTOMATIONS}

    @extend_schema(operation_id="control_automations_retrieve", responses=OpenApiTypes.OBJECT)
    def get(self, request, code):
        return Response(automations_svc.detail(request.property, code))

    @extend_schema(
        operation_id="control_automations_partial_update",
        request=s.AutomationUpdateSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def patch(self, request, code):
        body = s.AutomationUpdateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = dict(body.validated_data)
        if isinstance(request.data, dict) and "params" in request.data:
            data["params"] = request.data["params"]
        return Response(automations_svc.update(request.property, code, data, actor=request.user))


class AutomationRunNowView(PropertyScopedAPIView):
    """`POST automations/{code}/run/` → 200 `{queued: false, run}` (ran here) or 202 `{queued: true}`
    (queued on Celery because it usually takes ≥ 10 s). 409 `automation_running` if it is running."""

    required_permissions = {"post": AUTOMATIONS}

    @extend_schema(operation_id="control_automations_run", request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, code):
        result = automations_svc.run_now(request.property, code, actor=request.user)
        return Response(result, status=status.HTTP_202_ACCEPTED if result["queued"] else status.HTTP_200_OK)


class AutomationRunListView(PropertyScopedAPIView):
    """`GET automation-runs/?code&status` → paginated history of the property's runs (newest first)."""

    required_permissions = {"get": AUTOMATIONS}

    @extend_schema(
        operation_id="control_automation_runs_list",
        parameters=[
            _param("code", "Código de la automatización"),
            _param("status", "Estado (lista separada por comas)"),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        qs = AutomationRun.objects.filter(property=request.property).select_related("triggered_by")
        if code := request.query_params.get("code"):
            qs = qs.filter(code=code)
        if value := request.query_params.get("status"):
            qs = qs.filter(status__in=[item for item in value.split(",") if item])
        qs = qs.order_by("-started_at", "-id")
        return _paginate(self, request, qs, lambda page: [automations_svc.serialize_run(run) for run in page])


class AutomationRunDetailView(PropertyScopedAPIView):
    required_permissions = {"get": AUTOMATIONS}

    @extend_schema(operation_id="control_automation_runs_retrieve", responses=OpenApiTypes.OBJECT)
    def get(self, request, pk):
        run = (
            AutomationRun.objects.filter(property=request.property, pk=pk)
            .select_related("triggered_by")
            .first()
        )
        if run is None:
            raise NotFoundError("Corrida no encontrada")
        return Response(automations_svc.serialize_run(run))


# ---- Audit -----------------------------------------------------------------------------------------------

AUDIT_FILTERS = [
    _param("action", "Acción exacta (p. ej. bookings.room_assigned)"),
    _param("app", "Módulo: prefijo de la acción (p. ej. bookings)"),
    _param("source", "Origen: user, automation, ai, channel, guest, system, api (lista separada por comas)"),
    _param("actor", "Id del usuario, o `none` para acciones sin usuario"),
    _param("target_type", "Tipo de objeto (app_label.model)"),
    _param("target_id", "Id del objeto"),
    _param("reservation", "Id de la reserva: sus eventos y los de sus estadías, folios, cargos, pagos…"),
    _param("reversible", "1 = solo acciones reversibles"),
    _param("undone", "1 = solo deshechas · 0 = no deshechas"),
    _param("start", "Desde (AAAA-MM-DD, inclusivo, hora del hotel)", OpenApiTypes.DATE),
    _param("end", "Hasta (AAAA-MM-DD, inclusivo, hora del hotel)", OpenApiTypes.DATE),
    _param("q", "Texto en el resumen, el actor o la acción"),
]


class AuditListView(PropertyScopedAPIView):
    """`GET audit/` → paginated timeline (events of the property + organization-level events)."""

    required_permissions = {"get": AUDIT}

    @extend_schema(operation_id="control_audit_list", parameters=AUDIT_FILTERS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        qs = audit_svc.filtered(request.property, request.query_params)
        return _paginate(self, request, qs, audit_svc.serialize_page)


class AuditFacetsView(PropertyScopedAPIView):
    """`GET audit/facets/` → actions, apps, sources and people present in the timeline (for the filters)."""

    required_permissions = {"get": AUDIT}

    @extend_schema(operation_id="control_audit_facets", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(audit_svc.facets(request.property))


class AuditDetailView(PropertyScopedAPIView):
    """`GET audit/{id}/` → the event with its before/after (`diff`, `details`, `row_changes`)."""

    required_permissions = {"get": AUDIT}

    @extend_schema(operation_id="control_audit_retrieve", responses=OpenApiTypes.OBJECT)
    def get(self, request, pk):
        data = audit_svc.detail(request.property, pk)
        data["can_undo"] = data["undoable"] and _can(request, AUDIT_UNDO)
        return Response(data)


class AuditUndoView(PropertyScopedAPIView):
    """`POST audit/{id}/undo/` `{confirm: true}` → `core.audit.undo`. 400 `confirmation_required`; 409
    `undo_conflict` (a newer change of the same object must be undone first), `already_undone`,
    `not_reversible`, `undo_not_supported`, `undo_target_missing` or the handler's own conflict."""

    required_permissions = {"post": AUDIT_UNDO}

    @extend_schema(
        operation_id="control_audit_undo", request=s.AuditUndoSerializer, responses=OpenApiTypes.OBJECT
    )
    def post(self, request, pk):
        body = s.AuditUndoSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = audit_svc.undo(
            request.property, pk, actor=request.user, confirm=body.validated_data["confirm"]
        )
        data["can_undo"] = False
        return Response(data)


# ---- Alerts ----------------------------------------------------------------------------------------------


class AlertListView(PropertyScopedAPIView):
    """`GET alerts/?status=open|resolved|all&severity&kind&q` → paginated (open: most severe first)."""

    required_permissions = {"get": ALERTS}

    @extend_schema(
        operation_id="control_alerts_list",
        parameters=[
            _param("status", "open (por defecto), resolved o all"),
            _param("severity", "critical, warning, info (lista separada por comas)"),
            _param("kind", "Tipo de alerta"),
            _param("q", "Texto en el título o el mensaje"),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        qs = alerts_svc.filtered(request.property, request.query_params)
        return _paginate(self, request, qs, lambda page: [alerts_svc.serialize(alert) for alert in page])


class AlertCountView(PropertyScopedAPIView):
    """`GET alerts/count/` → `{open, by_severity: {critical, warning, info}, latest: [...]}`."""

    required_permissions = {"get": ALERTS}

    @extend_schema(operation_id="control_alerts_count", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(alerts_svc.counts(request.property))


class AlertDetailView(PropertyScopedAPIView):
    required_permissions = {"get": ALERTS}

    @extend_schema(operation_id="control_alerts_retrieve", responses=OpenApiTypes.OBJECT)
    def get(self, request, pk):
        return Response(alerts_svc.serialize(alerts_svc.get(request.property, pk)))


class AlertResolveView(PropertyScopedAPIView):
    """`POST alerts/{id}/resolve/` (idempotent)."""

    required_permissions = {"post": ALERTS}

    @extend_schema(operation_id="control_alerts_resolve", request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        return Response(alerts_svc.resolve(request.property, pk, actor=request.user))


class AlertResolveManyView(PropertyScopedAPIView):
    """`POST alerts/resolve/` `{ids: [...]}` → `{resolved: n}`."""

    required_permissions = {"post": ALERTS}

    @extend_schema(
        operation_id="control_alerts_resolve_many",
        request=s.AlertIdsSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request):
        body = s.AlertIdsSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        ids = [str(item) for item in body.validated_data["ids"]]
        return Response(alerts_svc.resolve_many(request.property, ids, actor=request.user))
