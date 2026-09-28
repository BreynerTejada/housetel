"""Staff distribution API (`/api/v1/distribution/`, header `X-Property-Id`). Permissions (plan §D):
`distribution.view` for every GET, `distribution.manage` for everything else (including the OTA simulator)."""

from datetime import date, timedelta

from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.api.pagination import StandardPagination
from apps.core.errors import DomainError
from apps.core.tenancy import PropertyScopedAPIView, PropertyScopedMixin
from apps.distribution.api import serializers as s
from apps.distribution.errors import ChannelError
from apps.distribution.models import (
    AriUpdate,
    ChannelConnection,
    ExternalReservationMap,
    RateMapping,
    RoomMapping,
    SimOtaBooking,
    SyncLog,
)
from apps.distribution.providers import CHANNEL_KINDS, suggested_catalog
from apps.distribution.services import connections as services
from apps.distribution.services import simulator
from apps.distribution.services.queue import PUSH_CHANNELS, full_sync, process_queue

UUID_REGEX = "[0-9a-fA-F-]{36}"
VIEW, MANAGE = "distribution.view", "distribution.manage"
MAX_GRID_DAYS = 62
DEFAULT_GRID_DAYS = 14


def _uuid_param(request, name):
    value = request.query_params.get(name)
    if not value:
        return None
    try:
        from uuid import UUID

        return UUID(value)
    except ValueError:
        raise ValidationError({name: ["UUID inválido"]}) from None


def _date_param(request, name, default=None):
    value = request.query_params.get(name)
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError({name: ["Fecha inválida (AAAA-MM-DD)"]}) from None


def _connections(prop):
    return (
        ChannelConnection.objects.filter(property=prop)
        .select_related("property")
        .prefetch_related(
            Prefetch("room_mappings", queryset=RoomMapping.objects.select_related("room_type", "room")),
            Prefetch("rate_mappings", queryset=RateMapping.objects.select_related("rate_plan", "room_type")),
        )
    )


class ConnectionViewSet(PropertyScopedMixin, viewsets.ModelViewSet):
    """Connections of the active property with their mappings (plain list, not paginated)."""

    queryset = ChannelConnection.objects.all()
    serializer_class = s.ChannelConnectionSerializer
    pagination_class = None
    lookup_value_regex = UUID_REGEX
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    required_permissions = {"list": VIEW, "retrieve": VIEW, "*": MANAGE}

    def get_queryset(self):
        return _connections(self.request.property).order_by("name", "created_at")

    def _body(self, connection, **extra):
        connection = _connections(self.request.property).get(pk=connection.pk)
        return {**s.ChannelConnectionSerializer(connection).data, **extra}

    def list(self, request, *args, **kwargs):
        connections = list(self.get_queryset())
        stats = s.connection_stats(connections)
        return Response(s.ChannelConnectionSerializer(connections, many=True, context={"stats": stats}).data)

    @extend_schema(
        request=s.ChannelConnectionWriteSerializer, responses={201: s.ChannelConnectionWriteResultSerializer}
    )
    def create(self, request, *args, **kwargs):
        payload = s.ChannelConnectionWriteSerializer(
            data=request.data, context={"property": request.property}
        )
        payload.is_valid(raise_exception=True)
        if "channel_code" not in payload.validated_data:
            raise ValidationError({"channel_code": ["Indica el canal"]})
        connection, summary = services.create_connection(
            request.property, payload.validated_data, actor=request.user
        )
        return Response(self._body(connection, sync=summary), status=status.HTTP_201_CREATED)

    @extend_schema(
        request=s.ChannelConnectionWriteSerializer, responses=s.ChannelConnectionWriteResultSerializer
    )
    def partial_update(self, request, *args, **kwargs):
        connection = self.get_object()
        payload = s.ChannelConnectionWriteSerializer(
            data=request.data, partial=True, context={"property": request.property, "connection": connection}
        )
        payload.is_valid(raise_exception=True)
        data = {key: value for key, value in payload.validated_data.items() if key != "channel_code"}
        connection, summary = services.update_connection(connection, data, actor=request.user)
        return Response(self._body(connection, sync=summary))

    def destroy(self, request, *args, **kwargs):
        services.delete_connection(self.get_object(), actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=None, responses=s.ChannelTestResultSerializer)
    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        ok, message = services.check_connection(self.get_object())
        return Response({"ok": ok, "message": message})

    @extend_schema(
        request=None,
        responses=inline_serializer(
            "ChannelFullSyncResult",
            {
                "sent": serializers.IntegerField(),
                "retrying": serializers.IntegerField(),
                "failed": serializers.IntegerField(),
                "connections": serializers.IntegerField(),
            },
        ),
    )
    @action(detail=True, methods=["post"], url_path="full-sync")
    def full_sync(self, request, pk=None):
        return Response(full_sync(self.get_object(), actor=request.user))

    @extend_schema(request=None, responses=s.ChannelConnectionSerializer)
    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        connection = services.pause_connection(self.get_object(), actor=request.user)
        return Response(self._body(connection))

    @extend_schema(
        request=None,
        responses=inline_serializer(
            "ChannelResumeResult",
            {"connection": s.ChannelConnectionSerializer(), "sync": serializers.JSONField(allow_null=True)},
        ),
    )
    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        connection, summary = services.resume_connection(self.get_object(), actor=request.user)
        return Response({"connection": self._body(connection), "sync": summary})

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def pull(self, request, pk=None):
        return Response(services.pull_now(self.get_object(), actor=request.user))


class SyncLogViewSet(PropertyScopedMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """What went in and out of the property's connections, newest first."""

    queryset = SyncLog.objects.select_related("connection", "reservation")
    serializer_class = s.SyncLogSerializer
    property_field = "connection__property"
    required_permissions = {"*": VIEW}

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if connection_id := _uuid_param(self.request, "connection"):
            queryset = queryset.filter(connection_id=connection_id)
        if direction := params.get("direction"):
            queryset = queryset.filter(direction=direction)
        if statuses := params.getlist("status"):
            queryset = queryset.filter(status__in=statuses)
        if kind := params.get("kind"):
            queryset = queryset.filter(kind=kind)
        if reservation_id := _uuid_param(self.request, "reservation"):
            queryset = queryset.filter(reservation_id=reservation_id)
        if date_from := _date_param(self.request, "date_from"):
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to := _date_param(self.request, "date_to"):
            queryset = queryset.filter(created_at__date__lte=date_to)
        if q := params.get("q", "").strip():
            queryset = queryset.filter(Q(message__icontains=q) | Q(external_id__icontains=q))
        return queryset.order_by("-created_at", "-pk")

    @extend_schema(
        parameters=[
            OpenApiParameter("connection", OpenApiTypes.UUID),
            OpenApiParameter("direction", OpenApiTypes.STR, enum=["in", "out"]),
            OpenApiParameter(
                "status", OpenApiTypes.STR, many=True, description="success|warning|error|skipped"
            ),
            OpenApiParameter("kind", OpenApiTypes.STR, description="ari, booking_new, ical_import, test…"),
            OpenApiParameter("reservation", OpenApiTypes.UUID),
            OpenApiParameter("date_from", OpenApiTypes.DATE),
            OpenApiParameter("date_to", OpenApiTypes.DATE),
            OpenApiParameter("q", OpenApiTypes.STR, description="Texto del mensaje o código externo"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class AriQueueViewSet(PropertyScopedMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """The ARI queue of the property's connections, newest first."""

    queryset = AriUpdate.objects.select_related("connection", "room_type")
    serializer_class = s.AriUpdateSerializer
    required_permissions = {"list": VIEW, "*": MANAGE}

    def get_queryset(self):
        queryset = super().get_queryset()
        if connection_id := _uuid_param(self.request, "connection"):
            queryset = queryset.filter(connection_id=connection_id)
        if statuses := self.request.query_params.getlist("status"):
            queryset = queryset.filter(status__in=statuses)
        return queryset.order_by("-created_at", "-pk")

    @extend_schema(
        parameters=[
            OpenApiParameter("connection", OpenApiTypes.UUID),
            OpenApiParameter(
                "status", OpenApiTypes.STR, many=True, description="pending|sending|sent|failed"
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=s.AriQueueRetrySerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def retry(self, request):
        """Failed updates back to pending, sent now (ignoring the backoff)."""
        payload = s.AriQueueRetrySerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        connection = None
        if payload.validated_data.get("connection"):
            connection = get_object_or_404(
                ChannelConnection, pk=payload.validated_data["connection"], property=request.property
            )
        failed = AriUpdate.objects.filter(property=request.property, status=AriUpdate.Status.FAILED)
        if connection is not None:
            failed = failed.filter(connection=connection)
        retried = failed.update(
            status=AriUpdate.Status.PENDING, attempts=0, next_attempt_at=None, last_error=""
        )
        summary = process_queue(request.property, connection=connection, force=True)
        return Response({"retried": retried, **summary})


class OptionsView(PropertyScopedAPIView):
    """Everything the connection wizard needs: channels, categories, rate plans and integrations."""

    required_permissions = {"get": VIEW}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        prop = request.property
        from apps.core.i18n import t  # noqa: F401 - names stay i18n dicts; the UI translates them
        from apps.inventory.models import RoomType
        from apps.rates.models import RatePlan

        existing = set(ChannelConnection.objects.filter(property=prop).values_list("channel_code", flat=True))
        channels = []
        for code, label in ChannelConnection.Channel.choices:
            kind = CHANNEL_KINDS.get(code)
            channels.append(
                {
                    "code": code,
                    "label": label,
                    "delivery": services.delivery(code),
                    "pushes_ari": code in PUSH_CHANNELS,
                    "modes": ["real", "simulated"] if kind else ["simulated"],
                    "multiple": code == services.ICAL,
                    "connected": code in existing,
                    "integration": kind,
                }
            )
        room_types = [
            {
                "id": str(rt.pk),
                "code": rt.code,
                "name": rt.name,
                "kind": rt.kind,
                "color": rt.color,
                "is_active": rt.is_active,
                "rooms": [
                    {"id": str(room.pk), "number": room.number} for room in rt.rooms.all() if room.is_active
                ],
            }
            for rt in RoomType.objects.filter(property=prop)
            .prefetch_related("rooms")
            .order_by("sort_order", "code")
        ]
        plans = []
        for plan in (
            RatePlan.objects.filter(property=prop)
            .prefetch_related("room_types")
            .order_by("kind", "sort_order", "code")
        ):
            types = sorted(plan.room_types.all(), key=lambda rt: (rt.sort_order, rt.code))
            plans.append(
                {
                    "id": str(plan.pk),
                    "code": plan.code,
                    "name": plan.name,
                    "kind": plan.kind,
                    "room_types": [str(rt.pk) for rt in types],
                    "is_public": plan.is_public,
                    "is_active": plan.is_active,
                    "channels": list(plan.channels or []),
                    **_sample_prices(prop, plan, [rt for rt in types if rt.is_active]),
                }
            )
        integrations_info = {
            kind: {**services.integration_info(prop, kind), "fields": services.config_fields(kind)}
            for kind in sorted(set(CHANNEL_KINDS.values()))
        }
        return Response(
            {
                "channels": channels,
                "room_types": room_types,
                "rate_plans": plans,
                "integrations": integrations_info,
                "currency": prop.currency or "COP",
                "business_date": prop.business_date.isoformat(),
            }
        )


def _sample_prices(prop, plan, room_types) -> dict:
    """The plan's price tonight (business date) per active category, rounded like a quote; the wizard
    previews the channel price from it (`channelPrice` = this × markup). `sample` = the first category's
    (kept for older clients), `samples` = every category with a price."""
    from apps.core.money import quantize
    from apps.rates.services.quote import resolve_daily

    if not room_types or not plan.is_active:
        return {"sample": None, "samples": []}
    night = prop.business_date
    samples = []
    for room_type in room_types:
        (day,) = resolve_daily(room_type, plan, night, night + timedelta(days=1))
        if day.source == "none":
            continue
        price = quantize(day.price, prop.currency or "COP")
        samples.append(
            {
                "room_type": str(room_type.pk),
                "room_type_code": room_type.code,
                "date": night.isoformat(),
                "price": f"{price:.2f}",
            }
        )
    first = samples[0] if samples and samples[0]["room_type"] == str(room_types[0].pk) else None
    return {"sample": first, "samples": samples}


class CatalogView(PropertyScopedAPIView):
    """Rooms and rates the channel offers for the mapping step (`?channel=`): suggestions for the simulated
    channels, the real list for Channex in real mode."""

    required_permissions = {"get": VIEW}

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "channel", OpenApiTypes.STR, required=True, enum=["booksim", "airsim", "channex"]
            )
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        channel = request.query_params.get("channel", "")
        prop = request.property
        if channel in (ChannelConnection.Channel.BOOKSIM, ChannelConnection.Channel.AIRSIM):
            return Response(suggested_catalog(prop, channel))
        if channel != ChannelConnection.Channel.CHANNEX:
            raise DomainError("Este canal no tiene catálogo de habitaciones", code="not_supported")
        from apps.core import integrations

        try:
            return Response(integrations.get_provider(prop, "channel_channex").remote_catalog())
        except ChannelError as exc:
            error = DomainError(exc.message, code=exc.code)
            error.status_code = 502 if exc.retryable else 400
            raise error from exc


# --- simulator ----------------------------------------------------------------------------------------------


class SimulatorView(PropertyScopedAPIView):
    required_permissions = {"get": VIEW, "*": MANAGE}

    def get_required_permission(self):
        return VIEW if self.request.method.lower() == "get" else MANAGE

    def connection(self, connection_id) -> ChannelConnection:
        return get_object_or_404(
            ChannelConnection.objects.select_related("property"),
            pk=connection_id,
            property=self.request.property,
        )


def _booking_body(booking, reservations=None):
    context = {"reservations": reservations} if reservations is not None else {}
    return s.OtaSimBookingSerializer(booking, context=context).data


class SimulatorInventoryView(SimulatorView):
    @extend_schema(
        parameters=[OpenApiParameter("start", OpenApiTypes.DATE), OpenApiParameter("end", OpenApiTypes.DATE)],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request, connection_id):
        """What the OTA holds for `[start, end)` (default: 14 nights from the business date; max 62)."""
        connection = self.connection(connection_id)
        start = _date_param(request, "start", request.property.business_date)
        end = _date_param(request, "end", start + timedelta(days=DEFAULT_GRID_DAYS))
        if end <= start or (end - start).days > MAX_GRID_DAYS:
            raise ValidationError({"end": [f"El rango debe tener entre 1 y {MAX_GRID_DAYS} noches"]})
        return Response(simulator.ota_inventory(connection, start, end))


class SimulatorBookingsView(SimulatorView):
    @extend_schema(responses=s.OtaSimBookingSerializer(many=True))
    def get(self, request, connection_id):
        """Bookings made in the OTA, newest first (paginated)."""
        connection = self.connection(connection_id)
        simulator.ensure_simulated(connection)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(
            SimOtaBooking.objects.filter(connection=connection).order_by("-created_at", "-pk"),
            request,
            view=self,
        )
        maps = ExternalReservationMap.objects.filter(
            connection=connection, external_id__in=[booking.external_id for booking in page]
        ).select_related("reservation")
        reservations = {item.external_id: item.reservation for item in maps}
        return paginator.get_paginated_response([_booking_body(booking, reservations) for booking in page])

    @extend_schema(
        request=s.OtaSimBookingCreateSerializer,
        responses={
            201: s.OtaSimBookingSerializer,
            409: OpenApiResponse(description="ota_not_sellable (+reasons)"),
        },
    )
    def post(self, request, connection_id):
        """A guest books in the OTA (BookSim/AirSim deliver it to the PMS at once)."""
        connection = self.connection(connection_id)
        payload = s.OtaSimBookingCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        booking = simulator.create_booking(
            connection,
            external_room_id=data["external_room_id"],
            external_rate_id=data["external_rate_id"],
            checkin=data["checkin"],
            checkout=data["checkout"],
            adults=data["adults"],
            children=data.get("children", 0),
            guest=data.get("guest"),
            notes=data.get("notes", ""),
            force=data.get("force", False),
            actor=request.user,
        )
        booking.refresh_from_db()
        return Response(_booking_body(booking), status=status.HTTP_201_CREATED)


class SimulatorBookingActionView(SimulatorView):
    action_name = ""

    @extend_schema(request=s.OtaSimBookingModifySerializer, responses=s.OtaSimBookingSerializer)
    def post(self, request, connection_id, external_id):
        connection = self.connection(connection_id)
        if self.action_name == "modify":
            payload = s.OtaSimBookingModifySerializer(data=request.data)
            payload.is_valid(raise_exception=True)
            booking = simulator.modify_booking(
                connection, external_id, actor=request.user, **payload.validated_data
            )
        elif self.action_name == "cancel":
            booking = simulator.cancel_booking(connection, external_id, actor=request.user)
        else:
            simulator.ensure_simulated(connection)
            booking = get_object_or_404(SimOtaBooking, connection=connection, external_id=external_id)
            simulator.deliver(connection, booking, actor=request.user)
        booking.refresh_from_db()
        return Response(_booking_body(booking))
