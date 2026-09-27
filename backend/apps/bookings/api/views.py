"""Staff API of bookings (`/api/v1/bookings/…`, plan B2b › API). Every view is scoped to `X-Property-Id` by
`apps.core.tenancy`; the business rules live in `apps.bookings.services`."""

from uuid import UUID

from django.db import transaction
from django.db.models import Count, Prefetch
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.bookings.api.filters import ReservationFilter
from apps.bookings.api.serializers import (
    BookingAssignSerializer,
    BookingAutoAssignSerializer,
    BookingCalendarQuerySerializer,
    BookingCancelSerializer,
    BookingDateRangeQuerySerializer,
    BookingForceSerializer,
    BookingGroupSerializer,
    BookingModifyPreviewSerializer,
    BookingModifySerializer,
    BookingOccupantSerializer,
    BookingOfferRatePlanSerializer,
    BookingOfferRoomTypeSerializer,
    BookingOfferSerializer,
    BookingOffersQuerySerializer,
    BookingRebuildSerializer,
    BookingRoomOptionSerializer,
    BookingStayDetailSerializer,
    ReservationCreateSerializer,
    ReservationDetailSerializer,
    ReservationListSerializer,
    ReservationUpdateSerializer,
    guest_input,
)
from apps.bookings.models import Reservation, ReservationGroup, Stay
from apps.bookings.services import reservations as services
from apps.bookings.services.assignment import room_options
from apps.bookings.services.availability import availability, search_offers
from apps.bookings.services.inventory import available_by_date, inventory_horizon, rebuild_inventory
from apps.bookings.services.policies import cancellation_fee
from apps.bookings.services.pricing import money_str
from apps.bookings.services.queries import with_balance
from apps.bookings.types import BookingError
from apps.core import audit
from apps.core.errors import ConfirmationRequired
from apps.core.permissions import codes_match
from apps.core.tenancy import PropertyScopedAPIView, PropertyScopedMixin, PropertyScopedViewSet
from apps.guests.models import Guest
from apps.inventory.models import Bed, Room, RoomBlock, RoomType
from apps.rates.models import RatePlan

VIEW, MANAGE, CHECKIN = "bookings.view", "bookings.manage", "bookings.checkin"
CALENDAR_MAX_DAYS = 93
CALENDAR_STATUSES = ["tentative", "confirmed", "checked_in", "checked_out"]
REBUILD_MAX_DAYS = 731  # the default horizon is 548 nights


def require_permission(request, code) -> None:
    """Second permission some actions need on top of the view's (waive fee, overbook, forced check-out)."""
    if not codes_match(request.membership.role.permissions, code):
        raise PermissionDenied(
            {"detail": "No tienes permiso para esta acción", "code": "permission_denied", "permission": code}
        )


def detail_queryset(prop):
    stays = Stay.objects.select_related("room_type", "rate_plan", "room", "bed").prefetch_related("occupants")
    return (
        Reservation.objects.filter(property=prop)
        .select_related("property", "booker", "group", "created_by")
        .prefetch_related(Prefetch("stays", queryset=stays.order_by("checkin_date", "created_at")))
    )


def detail_response(request, reservation, status_code=status.HTTP_200_OK) -> Response:
    fresh = detail_queryset(request.property).get(pk=reservation.pk)
    return Response(ReservationDetailSerializer(fresh, context={"request": request}).data, status=status_code)


class ReservationViewSet(
    PropertyScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Reservations of the active property. Writes go through the booking services."""

    queryset = Reservation.objects.all()
    filterset_class = ReservationFilter
    ordering_fields = ["checkin_date", "checkout_date", "created_at", "code", "total_amount", "balance"]
    ordering = ["-checkin_date", "-created_at"]
    http_method_names = ["get", "post", "patch", "head", "options"]
    required_permissions = {
        "list": VIEW,
        "retrieve": VIEW,
        "create": MANAGE,
        "partial_update": MANAGE,
        "cancel": "bookings.cancel",
        "cancel_preview": VIEW,
        "confirm": MANAGE,
        "no_show": MANAGE,
    }

    def get_queryset(self):
        if self.action == "list":
            stays = Stay.objects.select_related("room_type", "room", "bed").order_by(
                "checkin_date", "created_at"
            )
            return with_balance(
                super()
                .get_queryset()
                .select_related("booker", "group")
                .prefetch_related(Prefetch("stays", queryset=stays))
            )
        return detail_queryset(self.request.property)

    def get_serializer_class(self):
        return ReservationListSerializer if self.action == "list" else ReservationDetailSerializer

    @extend_schema(request=ReservationCreateSerializer, responses={201: ReservationDetailSerializer})
    def create(self, request):
        serializer = ReservationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("allow_overbooking"):
            require_permission(request, "bookings.overbook")
        reservation = services.create_reservation(
            serializer.build(request.property), actor=request.user, source_label="user"
        )
        return detail_response(request, reservation, status.HTTP_201_CREATED)

    @extend_schema(request=ReservationUpdateSerializer, responses=ReservationDetailSerializer)
    def partial_update(self, request, pk=None):
        reservation = self.get_object()
        serializer = ReservationUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_reservation(reservation, dict(serializer.validated_data), actor=request.user)
        return detail_response(request, reservation)

    @extend_schema(request=BookingCancelSerializer, responses=ReservationDetailSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """`{reason, waive_fee, confirm: true}`; waiving the fee also needs `bookings.waive_fee`."""
        reservation = self.get_object()
        serializer = BookingCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["confirm"] is not True:
            raise ConfirmationRequired("Confirma la cancelación enviando confirm: true")
        if data["waive_fee"]:
            require_permission(request, "bookings.waive_fee")
        services.cancel_reservation(
            reservation, reason=data["reason"], waive_fee=data["waive_fee"], actor=request.user, source="user"
        )
        return detail_response(request, reservation)

    @extend_schema(
        responses=inline_serializer(
            "BookingCancellationPreview",
            {
                "fee": serializers.DecimalField(max_digits=14, decimal_places=2),
                "currency": serializers.CharField(),
                "reason": serializers.CharField(),
                "free_until": serializers.DateTimeField(allow_null=True),
                "non_refundable": serializers.BooleanField(),
                "policy": serializers.JSONField(),
            },
        )
    )
    @action(detail=True, methods=["get"], url_path="cancel-preview")
    def cancel_preview(self, request, pk=None):
        reservation = self.get_object()
        return Response(cancellation_fee(reservation).as_dict(reservation.currency))

    @extend_schema(request=None, responses=ReservationDetailSerializer)
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        reservation = self.get_object()
        services.confirm_reservation(reservation, actor=request.user)
        return detail_response(request, reservation)

    @extend_schema(request=None, responses=ReservationDetailSerializer)
    @action(detail=True, methods=["post"], url_path="no-show")
    def no_show(self, request, pk=None):
        reservation = self.get_object()
        services.mark_no_show(reservation, actor=request.user, source="user")
        return detail_response(request, reservation)


class StayViewSet(PropertyScopedMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Actions on one stay; each answers with the updated reservation detail."""

    queryset = Stay.objects.select_related("reservation", "room_type", "rate_plan", "room", "bed")
    serializer_class = BookingStayDetailSerializer
    property_field = "reservation__property"
    required_permissions = {
        "retrieve": VIEW,
        "modify": MANAGE,
        "modify_preview": MANAGE,
        "room_options": VIEW,
        "assign": MANAGE,
        "unassign": MANAGE,
        "check_in": CHECKIN,
        "check_out": CHECKIN,
        "occupants": MANAGE,
    }

    @extend_schema(request=BookingModifySerializer, responses=ReservationDetailSerializer)
    @action(detail=True, methods=["post"])
    def modify(self, request, pk=None):
        stay = self.get_object()
        services.modify_stay(stay, actor=request.user, **self._modify_arguments(request))
        return detail_response(request, stay.reservation)

    @extend_schema(request=BookingModifySerializer, responses=BookingModifyPreviewSerializer)
    @action(detail=True, methods=["post"], url_path="modify-preview")
    def modify_preview(self, request, pk=None):
        """Same body as `modify/`: what the change would do (new nights, prices, totals, room kept or
        released) without saving anything; the same 409/400 errors."""
        stay = self.get_object()
        return Response(
            services.preview_modify_stay(stay, actor=request.user, **self._modify_arguments(request))
        )

    def _modify_arguments(self, request) -> dict:
        serializer = BookingModifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        prop = request.property
        if "room_type_id" in data:
            data["room_type"] = _in_property(RoomType, data.pop("room_type_id"), prop, "invalid_room_type")
        if "rate_plan_id" in data:
            data["rate_plan"] = _in_property(RatePlan, data.pop("rate_plan_id"), prop, "invalid_rate_plan")
        return data

    @extend_schema(responses=BookingRoomOptionSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="room-options")
    def room_options(self, request, pk=None):
        """Where the stay can go, best first: its category's free rooms/beds (ready first), then other
        categories of the same kind with a unit left (`assign` with `force`)."""
        return Response(room_options(self.get_object()))

    @extend_schema(request=BookingAssignSerializer, responses=ReservationDetailSerializer)
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """`{room_id, bed_id?, force?}` — `force` accepts a room of another category."""
        stay = self.get_object()
        serializer = BookingAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        room = _in_property(Room, data["room_id"], request.property, "invalid_room")
        bed = None
        if data["bed_id"]:
            bed = Bed.objects.filter(pk=data["bed_id"], room__property=request.property).first()
            if bed is None:
                raise BookingError("La cama no existe en esta propiedad", code="invalid_bed")
        services.assign_room(stay, room, bed=bed, actor=request.user, force=data["force"])
        return detail_response(request, stay.reservation)

    @extend_schema(request=None, responses=ReservationDetailSerializer)
    @action(detail=True, methods=["post"])
    def unassign(self, request, pk=None):
        stay = self.get_object()
        services.unassign_room(stay, actor=request.user)
        return detail_response(request, stay.reservation)

    @extend_schema(request=BookingForceSerializer, responses=ReservationDetailSerializer)
    @action(detail=True, methods=["post"], url_path="check-in")
    def check_in(self, request, pk=None):
        stay = self.get_object()
        serializer = BookingForceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.check_in(stay, actor=request.user, force=serializer.validated_data["force"])
        return detail_response(request, stay.reservation)

    @extend_schema(request=BookingForceSerializer, responses=ReservationDetailSerializer)
    @action(detail=True, methods=["post"], url_path="check-out")
    def check_out(self, request, pk=None):
        """`force` (check out with a balance due) also needs `bookings.checkout_with_balance`."""
        stay = self.get_object()
        serializer = BookingForceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["force"]:
            require_permission(request, "bookings.checkout_with_balance")
        services.check_out(stay, actor=request.user, force=serializer.validated_data["force"])
        return detail_response(request, stay.reservation)

    @extend_schema(
        request=BookingOccupantSerializer,
        responses=ReservationDetailSerializer,
        parameters=[OpenApiParameter("guest_id", OpenApiTypes.UUID, description="DELETE: huésped a quitar")],
    )
    @action(detail=True, methods=["post", "delete"])
    def occupants(self, request, pk=None):
        """POST `{guest_id}` or `{guest: GuestInput}` adds an occupant; DELETE `?guest_id=` removes one."""
        stay = self.get_object()
        if request.method == "DELETE":
            guest_id = request.query_params.get("guest_id") or request.data.get("guest_id")
            services.remove_occupant(stay, _organization_guest(request, guest_id), actor=request.user)
        else:
            serializer = BookingOccupantSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            if data.get("guest_id"):
                guest = _organization_guest(request, data["guest_id"])
            else:
                guest = guest_input(data["guest"])
            services.add_occupant(stay, guest, actor=request.user)
        return detail_response(request, stay.reservation)


def _organization_guest(request, guest_id) -> Guest:
    """A guest of the active organization; another tenant's guest answers like a missing one (no id
    probing)."""
    guest = Guest.objects.filter(pk=guest_id, organization=request.organization).first() if guest_id else None
    if guest is None:
        raise BookingError("El huésped no existe en esta organización", code="invalid_guest")
    return guest


def _in_property(model, pk, prop, code):
    item = model.objects.filter(pk=pk, property=prop).first()
    if item is None:
        raise BookingError("No existe en esta propiedad", code=code)
    return item


class AvailabilityView(PropertyScopedAPIView):
    """`GET availability/?checkin&checkout[&room_type=<id>…]` → `{room_type_id: units}` (minimum over the
    nights; negative when overbooked)."""

    required_permissions = {"get": VIEW}

    @extend_schema(
        parameters=[
            BookingDateRangeQuerySerializer,
            OpenApiParameter("room_type", OpenApiTypes.UUID, many=True),
        ],
        responses=inline_serializer("BookingAvailability", {"<room_type_id>": serializers.IntegerField()}),
    )
    def get(self, request):
        query = BookingDateRangeQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        room_types = request.query_params.getlist("room_type") or None
        result = availability(
            property=request.property,
            checkin=query.validated_data["checkin"],
            checkout=query.validated_data["checkout"],
            room_type_ids=room_types,
        )
        return Response({str(type_id): units for type_id, units in result.items()})


class OffersView(PropertyScopedAPIView):
    """`GET offers/?checkin&checkout&adults&children&children_ages=4,7&channel&promo_code&foreign=1` →
    sellable offers, cheapest first."""

    required_permissions = {"get": VIEW}

    @extend_schema(parameters=[BookingOffersQuerySerializer], responses=BookingOfferSerializer(many=True))
    def get(self, request):
        query = BookingOffersQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        offers = search_offers(
            property=request.property,
            checkin=data["checkin"],
            checkout=data["checkout"],
            adults=data["adults"],
            children=data["children"],
            children_ages=data["children_ages"] or None,
            channel=data["channel"],
            promo_code=data["promo_code"] or None,
            guest_is_foreign_non_resident=data["foreign"],
        )
        room_types = RoomType.objects.in_bulk({offer.room_type_id for offer in offers})
        plans = RatePlan.objects.select_related("cancellation_policy", "parent__cancellation_policy").in_bulk(
            {offer.rate_plan_id for offer in offers}
        )
        return Response(
            [
                {
                    "room_type_id": str(offer.room_type_id),
                    "rate_plan_id": str(offer.rate_plan_id),
                    "room_type": BookingOfferRoomTypeSerializer(room_types[offer.room_type_id]).data,
                    "rate_plan": BookingOfferRatePlanSerializer(plans[offer.rate_plan_id]).data,
                    "available_units": offer.available_units,
                    "units_needed": offer.units_needed,
                    "quote": offer.quote.to_dict(),
                    "total": money_str(offer.total),
                }
                for offer in offers
            ]
        )


class CalendarView(PropertyScopedAPIView):
    """`GET calendar/?start&end` (half-open `[start, end)`, at most 93 days): rooms by category, stays, blocks
    and availability per night — the grid of C1/C13."""

    required_permissions = {"get": VIEW}

    @extend_schema(parameters=[BookingCalendarQuerySerializer], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        query = BookingCalendarQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        start, end = query.validated_data["start"], query.validated_data["end"]
        if (end - start).days > CALENDAR_MAX_DAYS:
            raise BookingError(f"El rango máximo es de {CALENDAR_MAX_DAYS} días", code="range_too_long")
        prop = request.property
        room_types = list(
            RoomType.objects.filter(property=prop, is_active=True)
            .prefetch_related(
                Prefetch(
                    "rooms",
                    queryset=Room.objects.filter(is_active=True)
                    .order_by("sort_order", "number")
                    .prefetch_related(
                        Prefetch("beds", queryset=Bed.objects.filter(is_active=True).order_by("label"))
                    ),
                )
            )
            .order_by("sort_order", "code")
        )
        stays = (
            Stay.objects.filter(
                reservation__property=prop,
                status__in=CALENDAR_STATUSES,
                checkin_date__lt=end,
                checkout_date__gt=start,
            )
            .select_related("reservation__booker")
            .order_by("checkin_date", "created_at")
        )
        stays = list(stays)
        balances = dict(
            with_balance(
                Reservation.objects.filter(pk__in={stay.reservation_id for stay in stays})
            ).values_list("pk", "balance")
        )
        blocks = RoomBlock.objects.filter(
            room__property=prop, released_at__isnull=True, start_date__lt=end, end_date__gt=start
        ).order_by("start_date", "created_at")
        by_date = available_by_date(prop, [room_type.pk for room_type in room_types], start, end)
        return Response(
            {
                "room_types": [
                    {
                        "id": str(room_type.pk),
                        "code": room_type.code,
                        "name": room_type.name,
                        "color": room_type.color,
                        "kind": room_type.kind,
                        "rooms": [
                            {
                                "id": str(room.pk),
                                "number": room.number,
                                "floor": room.floor,
                                "housekeeping_status": room.housekeeping_status,
                                "beds": [{"id": str(bed.pk), "label": bed.label} for bed in room.beds.all()],
                            }
                            for room in room_type.rooms.all()
                        ],
                    }
                    for room_type in room_types
                ],
                "stays": [
                    {
                        "id": str(stay.pk),
                        "reservation_id": str(stay.reservation_id),
                        "code": stay.reservation.code,
                        "status": stay.status,
                        "source": stay.reservation.source,
                        "channel_code": stay.reservation.channel_code,
                        "guest_name": stay.reservation.booker.full_name,
                        "room_id": str(stay.room_id) if stay.room_id else None,
                        "bed_id": str(stay.bed_id) if stay.bed_id else None,
                        "room_type_id": str(stay.room_type_id),
                        "checkin": stay.checkin_date.isoformat(),
                        "checkout": stay.checkout_date.isoformat(),
                        "adults": stay.adults,
                        "children": stay.children,
                        "balance_due": balances.get(stay.reservation_id, 0) > 0,
                        "is_vip": stay.reservation.booker.is_vip,
                    }
                    for stay in stays
                ],
                "blocks": [
                    {
                        "id": str(block.pk),
                        "room_id": str(block.room_id),
                        "bed_id": str(block.bed_id) if block.bed_id else None,
                        "start": block.start_date.isoformat(),
                        "end": block.end_date.isoformat(),
                        "kind": block.kind,
                        "reason": block.reason,
                    }
                    for block in blocks
                ],
                "availability": {
                    str(type_id): {day.isoformat(): units for day, units in sorted(days.items())}
                    for type_id, days in by_date.items()
                },
            }
        )


class AutoAssignView(PropertyScopedAPIView):
    """`POST auto-assign/` `{date_from, date_to}` (both inclusive) → the assignment report."""

    required_permissions = {"post": MANAGE}

    @extend_schema(request=BookingAutoAssignSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = BookingAutoAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = services.auto_assign_rooms(
            property=request.property,
            date_from=serializer.validated_data["date_from"],
            date_to=serializer.validated_data["date_to"],
            actor=request.user,
        )
        stay_ids = [stay_id for stay_id, _unit in report.assigned] + report.unassigned
        stays = Stay.objects.select_related("reservation", "room", "bed").in_bulk(stay_ids)

        def ref(stay_id):
            stay = stays[UUID(stay_id)]
            return {
                "stay_id": stay_id,
                "reservation_id": str(stay.reservation_id),
                "code": stay.reservation.code,
            }

        assigned = []
        for stay_id, _unit_id in report.assigned:
            stay = stays[UUID(stay_id)]
            assigned.append(
                {
                    **ref(stay_id),
                    "room_id": str(stay.room_id),
                    "room_number": stay.room.number,
                    "bed_id": str(stay.bed_id) if stay.bed_id else None,
                    "bed_label": stay.bed.label if stay.bed_id else None,
                }
            )
        return Response(
            {
                "assigned": assigned,
                "unassigned": [ref(stay_id) for stay_id in report.unassigned],
                "messages": report.messages,
            }
        )


class InventoryRebuildView(PropertyScopedAPIView):
    """`POST inventory/rebuild/` `{start?, end?, room_type_ids?}` → `{created, updated, drift}`. A missing
    bound comes from the default horizon; the range must be non-empty and at most `REBUILD_MAX_DAYS` long."""

    required_permissions = {"post": MANAGE}

    @extend_schema(request=BookingRebuildSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = BookingRebuildSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        default_start, default_end = inventory_horizon(request.property)
        start, end = data.get("start") or default_start, data.get("end") or default_end
        if end <= start:
            raise serializers.ValidationError({"end": ["El fin debe ser posterior al inicio"]})
        if (end - start).days > REBUILD_MAX_DAYS:
            raise serializers.ValidationError({"end": [f"El rango máximo es de {REBUILD_MAX_DAYS} días"]})
        room_type_ids = data["room_type_ids"] or None
        with transaction.atomic():  # the recalculation and its audit are kept together or not at all
            result = rebuild_inventory(request.property, start, end, room_type_ids=room_type_ids)
            changes = result.as_dict() if result.updated else {"created": result.created, "updated": 0}
            audit.record(
                action="bookings.inventory_rebuilt",
                summary=(
                    f"Recalculó el inventario: {result.created} noches creadas, {result.updated} corregidas"
                ),
                actor=request.user,
                property=request.property,
                changes=changes,
            )
        return Response(result.as_dict())


class GroupViewSet(PropertyScopedViewSet):
    """Reservation groups of the active property."""

    queryset = ReservationGroup.objects.select_related("contact_guest")
    serializer_class = BookingGroupSerializer
    required_permissions = {"list": VIEW, "retrieve": VIEW, "*": MANAGE}

    def get_queryset(self):
        return (
            super().get_queryset().annotate(reservations_count=Count("reservations")).order_by("-created_at")
        )
