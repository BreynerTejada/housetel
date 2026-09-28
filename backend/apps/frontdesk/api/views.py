"""Staff API of the front desk (`/api/v1/frontdesk/…`, plan C1). Scoped to `X-Property-Id` by
`apps.core.tenancy`; the rules live in `apps.frontdesk.services`."""

from django.db.models import Prefetch
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from apps.bookings.api.filters import ReservationFilter
from apps.bookings.models import Reservation, ReservationGroup, Stay
from apps.bookings.services.groups import rooming_list
from apps.bookings.services.queries import with_balance
from apps.core.tenancy import PropertyScopedAPIView, PropertyScopedMixin
from apps.frontdesk.api.serializers import NightAuditReportSerializer, NightAuditRunSerializer
from apps.frontdesk.models import NightAuditReport
from apps.frontdesk.services.export import reservations_csv, rooming_csv
from apps.frontdesk.services.night_audit import preview_night_audit, run_manual
from apps.frontdesk.services.today import last_report, online_checkin_state, today_board

VIEW = "frontdesk.view"
NIGHT_AUDIT = "frontdesk.night_audit"
BOOKINGS_VIEW = "bookings.view"
EXPORT_ORDERING = {"checkin_date", "checkout_date", "created_at", "code", "total_amount", "balance"}


class TodayView(PropertyScopedAPIView):
    """`GET today/` → KPIs and the arrivals, departures and in-house lists of the business date."""

    required_permissions = {"get": VIEW}

    @extend_schema(operation_id="frontdesk_today", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(today_board(request.property))


class NightAuditPreviewView(PropertyScopedAPIView):
    """`GET night-audit/preview/` → what closing the current business date would do (nothing is saved)."""

    required_permissions = {"get": NIGHT_AUDIT}

    @extend_schema(operation_id="frontdesk_night_audit_preview", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        preview = preview_night_audit(request.property)
        return Response({**preview, "last_report": last_report(request.property)})


class NightAuditRunView(PropertyScopedAPIView):
    """`POST night-audit/run/` `{business_date}` → closes that date if it is still the current one (201); the
    report of a date already closed comes back with 200. 409 `business_date_changed` / `audit_ahead`."""

    required_permissions = {"post": NIGHT_AUDIT}

    @extend_schema(
        operation_id="frontdesk_night_audit_run",
        request=NightAuditRunSerializer,
        responses={201: NightAuditReportSerializer, 200: NightAuditReportSerializer},
    )
    def post(self, request):
        serializer = NightAuditRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report, closed = run_manual(
            request.property, business_date=serializer.validated_data["business_date"], actor=request.user
        )
        report = NightAuditReport.objects.select_related("triggered_by").get(pk=report.pk)
        return Response(
            NightAuditReportSerializer(report).data,
            status=status.HTTP_201_CREATED if closed else status.HTTP_200_OK,
        )


class NightAuditReportViewSet(
    PropertyScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """`GET night-audit/reports/` (newest first) and `GET night-audit/reports/{id}/`."""

    queryset = NightAuditReport.objects.select_related("triggered_by")
    serializer_class = NightAuditReportSerializer
    required_permissions = {"*": VIEW}
    ordering_fields = ["business_date"]
    ordering = ["-business_date"]


class ReservationExportView(PropertyScopedAPIView):
    """`GET reservations/export/?<filters of GET /api/v1/bookings/reservations/>&ordering=&lang=es|en` → CSV
    of every matching reservation of the active property (not only one page; at most 10.000 rows)."""

    required_permissions = {"get": BOOKINGS_VIEW}

    @extend_schema(
        operation_id="frontdesk_reservations_export",
        parameters=[
            OpenApiParameter("lang", str, enum=["es", "en"]),
            OpenApiParameter("ordering", str, description="checkin_date, checkout_date, created_at, code…"),
        ],
        responses={(200, "text/csv"): OpenApiTypes.STR},
    )
    def get(self, request):
        stays = Stay.objects.select_related("room", "bed", "room_type").order_by("checkin_date", "created_at")
        queryset = (
            with_balance(Reservation.objects.filter(property=request.property))
            .select_related("booker", "group")
            .prefetch_related(Prefetch("stays", queryset=stays))
        )
        filterset = ReservationFilter(request.query_params, queryset=queryset, request=request)
        if not filterset.is_valid():
            raise ValidationError(filterset.errors)
        ordering = request.query_params.get("ordering", "")
        order = [ordering] if ordering.lstrip("-") in EXPORT_ORDERING else ["-checkin_date", "-created_at"]
        return reservations_csv(
            filterset.qs.order_by(*order, "code"),
            lang=request.query_params.get("lang", "es"),
            business_date=request.property.business_date,
        )


class GroupRoomingExportView(PropertyScopedAPIView):
    """`GET groups/{id}/rooming-list/?lang=es|en` → the group's rooming list as CSV (one row per room: who
    holds it, where, when, the guest in it and whether it came from the allotment)."""

    required_permissions = {"get": BOOKINGS_VIEW}

    @extend_schema(
        operation_id="frontdesk_group_rooming_export",
        parameters=[OpenApiParameter("lang", str, enum=["es", "en"])],
        responses={(200, "text/csv"): OpenApiTypes.STR},
    )
    def get(self, request, group_id):
        group = ReservationGroup.objects.filter(pk=group_id, property=request.property).first()
        if group is None:
            raise NotFound("Grupo no encontrado")
        return rooming_csv(group, rooming_list(group), lang=request.query_params.get("lang", "es"))


class OnlineCheckinView(PropertyScopedAPIView):
    """`GET reservations/{id}/online-checkin/` → `{reservation_id, status, completed_at}` of the guest portal
    check-in (status null when never started)."""

    required_permissions = {"get": BOOKINGS_VIEW}

    @extend_schema(operation_id="frontdesk_reservation_online_checkin", responses=OpenApiTypes.OBJECT)
    def get(self, request, reservation_id):
        reservation = Reservation.objects.filter(pk=reservation_id, property=request.property).first()
        if reservation is None:
            raise NotFound("Reserva no encontrada")
        return Response(online_checkin_state(reservation))
