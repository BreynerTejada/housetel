"""Inventory staff API (`/api/v1/inventory/`, header `X-Property-Id`): `inventory.view` reads,
`inventory.manage` writes. Business rules live in apps.inventory.services; validation in serializers."""

from django.db.models import Count, Prefetch, Q
from django.db.models.functions import Length
from django.shortcuts import get_object_or_404
from django_filters import rest_framework as filters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.core.api.pagination import StandardPagination
from apps.core.tenancy import PropertyScopedAPIView, PropertyScopedMixin
from apps.inventory import services
from apps.inventory.models import Amenity, Bed, CustomFieldDefinition, Photo, Room, RoomBlock, RoomType
from apps.inventory.serializers import (
    AmenitySerializer,
    BedBulkSerializer,
    BedSerializer,
    CaptionField,
    CustomFieldDefinitionSerializer,
    PhotoSerializer,
    PhotoUploadSerializer,
    PropertyProfileSerializer,
    ReorderSerializer,
    ResetOverrideSerializer,
    RoomBlockCreateSerializer,
    RoomBlockSerializer,
    RoomBulkCreateResultSerializer,
    RoomBulkCreateSerializer,
    RoomBulkUpdateResultSerializer,
    RoomBulkUpdateSerializer,
    RoomSerializer,
    RoomStatusSerializer,
    RoomTypeSerializer,
    amenity_catalog,
    jsonable,
)

VIEW = "inventory.view"
MANAGE = "inventory.manage"


class InventoryMixin(PropertyScopedMixin):
    """Reads need `inventory.view`, everything else `inventory.manage`. Lists are plain arrays (a hotel's
    catalog fits in one response) unless the view sets a paginator."""

    pagination_class = None
    read_actions = ("list", "retrieve")

    def get_required_permission(self):
        action_name = getattr(self, "action", None) or self.request.method.lower()
        return VIEW if action_name in self.read_actions or action_name == "get" else MANAGE

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["property"] = getattr(self.request, "property", None)
        return context

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # OpenAPI generation has no active property
            return self.queryset.model.objects.none()
        return super().get_queryset()


# ---- Amenities -----------------------------------------------------------------------------------------


class AmenityViewSet(InventoryMixin, viewsets.ModelViewSet):
    """Global catalog (read-only) + the organization's own amenities."""

    queryset = Amenity.objects.all()
    serializer_class = AmenitySerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Amenity.objects.none()
        return amenity_catalog(self.request.organization).order_by("category", "code")

    def perform_create(self, serializer):
        services.save_amenity(serializer, organization=self.request.organization, actor=self.request.user)

    def _ensure_own(self, amenity):
        if amenity.organization_id is None:
            raise PermissionDenied(
                {
                    "detail": "Las amenidades del catálogo global no se pueden editar",
                    "code": "global_amenity_read_only",
                }
            )

    def perform_update(self, serializer):
        self._ensure_own(serializer.instance)
        services.save_amenity(serializer, organization=self.request.organization, actor=self.request.user)

    def perform_destroy(self, instance):
        self._ensure_own(instance)
        services.delete_amenity(instance, actor=self.request.user)


# ---- Room types ----------------------------------------------------------------------------------------


class RoomTypeViewSet(InventoryMixin, viewsets.ModelViewSet):
    queryset = RoomType.objects.all()
    serializer_class = RoomTypeSerializer
    filterset_fields = ["kind", "is_active"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return RoomType.objects.none()
        return (
            RoomType.objects.filter(property=self.request.property)
            .annotate(
                rooms_count=Count("rooms", distinct=True),
                active_rooms_count=Count("rooms", filter=Q(rooms__is_active=True), distinct=True),
                beds_count=Count(
                    "rooms__beds", filter=Q(rooms__is_active=True, rooms__beds__is_active=True), distinct=True
                ),
            )
            .prefetch_related("amenities", "photos")
            .order_by("sort_order", "code")
        )

    def _respond(self, room_type, status_code=status.HTTP_200_OK):
        fresh = self.get_queryset().get(pk=room_type.pk)
        return Response(self.get_serializer(fresh).data, status=status_code)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        room_type = services.save_room_type(
            request.property, data=serializer.validated_data, actor=request.user
        )
        return self._respond(room_type, status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.pop("partial", False))
        serializer.is_valid(raise_exception=True)
        room_type = services.save_room_type(
            request.property, data=serializer.validated_data, room_type=instance, actor=request.user
        )
        return self._respond(room_type)

    def perform_destroy(self, instance):
        services.delete_room_type(instance, actor=self.request.user)

    @extend_schema(
        request=inline_serializer(
            "RoomTypeDuplicate",
            {"code": serializers.CharField(required=False), "name": serializers.JSONField(required=False)},
        ),
        responses={201: RoomTypeSerializer},
    )
    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        source = self.get_object()
        copy = services.duplicate_room_type(
            source, code=request.data.get("code"), name=request.data.get("name"), actor=request.user
        )
        return self._respond(copy, status.HTTP_201_CREATED)


# ---- Photos --------------------------------------------------------------------------------------------


class PhotoViewSet(InventoryMixin, viewsets.GenericViewSet):
    """Photos of a category (`room_type_id` in the URL) or of the property. Public URLs (marketplace)."""

    queryset = Photo.objects.all()
    serializer_class = PhotoSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    lookup_url_kwarg = "photo_id"

    def get_room_type(self):
        room_type_id = self.kwargs.get("room_type_id")
        if room_type_id is None:
            return None
        return get_object_or_404(RoomType, pk=room_type_id, property=self.request.property)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Photo.objects.none()
        return Photo.objects.filter(
            property=self.request.property, room_type=self.get_room_type(), room__isnull=True
        ).order_by("sort_order", "created_at")

    def list(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @extend_schema(request=PhotoUploadSerializer, responses={201: PhotoSerializer})
    def create(self, request, *args, **kwargs):
        room_type = self.get_room_type()
        upload = PhotoUploadSerializer(data=request.data, context=self.get_serializer_context())
        upload.is_valid(raise_exception=True)
        photo = services.add_photo(
            request.property,
            image=upload.validated_data["image"],
            caption=upload.validated_data.get("caption"),
            room_type=room_type,
            actor=request.user,
        )
        return Response(self.get_serializer(photo).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=inline_serializer("PhotoCaption", {"caption": CaptionField()}), responses=PhotoSerializer
    )
    def partial_update(self, request, *args, **kwargs):
        photo = self.get_object()
        serializer = self.get_serializer(photo, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if "caption" in serializer.validated_data:
            services.update_photo_caption(
                photo, caption=serializer.validated_data["caption"], actor=request.user
            )
        return Response(self.get_serializer(photo).data)

    def destroy(self, request, *args, **kwargs):
        services.delete_photo(self.get_object(), actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=ReorderSerializer, responses=PhotoSerializer(many=True))
    def reorder(self, request, *args, **kwargs):
        serializer = ReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ordered = services.reorder_photos(
            list(self.get_queryset()),
            serializer.validated_data["ids"],
            gallery=self.get_room_type() or request.property,
            actor=request.user,
        )
        return Response(self.get_serializer(ordered, many=True).data)


# ---- Rooms ---------------------------------------------------------------------------------------------


class RoomFilter(filters.FilterSet):
    room_type = filters.UUIDFilter(field_name="room_type_id")

    class Meta:
        model = Room
        fields = ["room_type", "floor", "building", "housekeeping_status", "is_active"]


class RoomViewSet(InventoryMixin, viewsets.ModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    filterset_class = RoomFilter
    filter_backends = [filters.DjangoFilterBackend, SearchFilter]
    search_fields = ["number", "name"]
    read_actions = ("list", "retrieve", "effective")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Room.objects.none()
        business_date = self.request.property.business_date
        return (
            Room.objects.filter(property=self.request.property)
            .select_related("room_type", "property")
            .prefetch_related(
                "room_type__amenities",
                "extra_amenities",
                "removed_amenities",
                "connecting_rooms",
                Prefetch(
                    "blocks",
                    queryset=RoomBlock.objects.filter(
                        released_at__isnull=True, end_date__gt=business_date
                    ).order_by("start_date"),
                    to_attr="current_blocks",
                ),
            )
            .annotate(
                beds_count=Count("beds", distinct=True),
                active_beds_count=Count("beds", filter=Q(beds__is_active=True), distinct=True),
            )
            .order_by("room_type__sort_order", "room_type__code", "sort_order", Length("number"), "number")
        )

    def _respond(self, rooms, status_code=status.HTTP_200_OK, *, many=False, wrap=None):
        ids = [room.pk for room in (rooms if many else [rooms])]
        fresh = {room.pk: room for room in self.get_queryset().filter(pk__in=ids)}
        ordered = [fresh[pk] for pk in ids]
        data = self.get_serializer(ordered if many else ordered[0], many=many).data
        return Response(wrap(data) if wrap else data, status=status_code)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        room = services.save_room(request.property, data=serializer.validated_data, actor=request.user)
        return self._respond(room, status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.pop("partial", False))
        serializer.is_valid(raise_exception=True)
        room = services.save_room(
            request.property, data=serializer.validated_data, room=instance, actor=request.user
        )
        return self._respond(room)

    def perform_destroy(self, instance):
        services.delete_room(instance, actor=self.request.user)

    @extend_schema(request=RoomBulkCreateSerializer, responses={201: RoomBulkCreateResultSerializer})
    @action(detail=False, methods=["post"], url_path="bulk-create")
    def bulk_create(self, request):
        serializer = RoomBulkCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        rooms = services.bulk_create_rooms(
            request.property,
            room_type=data["room_type"],
            numbers=data["numbers"],
            floor=data["floor"],
            building=data["building"],
            beds_per_room=data["beds_per_room"],
            actor=request.user,
        )
        return self._respond(
            rooms, status.HTTP_201_CREATED, many=True, wrap=lambda rows: {"count": len(rows), "rooms": rows}
        )

    @extend_schema(request=RoomBulkUpdateSerializer, responses=RoomBulkUpdateResultSerializer)
    @action(detail=False, methods=["post"], url_path="bulk-update")
    def bulk_update(self, request):
        serializer = RoomBulkUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        rooms = services.bulk_update_rooms(
            request.property,
            room_ids=data["ids"],
            values=data["set"],
            reset=data["reset"],
            actor=request.user,
        )
        return self._respond(rooms, many=True, wrap=lambda rows: {"updated": len(rows), "rooms": rows})

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def effective(self, request, pk=None):
        """`effective_attributes(room)` plus `inherited`: the category values of every overridable field,
        its amenities and custom values (to show what an override replaces)."""
        room = self.get_object()
        room_type = room.room_type
        inherited = {field: getattr(room_type, field) for field in services.ROOM_OVERRIDABLE_FIELDS}
        inherited["amenities"] = sorted(amenity.code for amenity in room_type.amenities.all())
        inherited["custom_values"] = dict(room_type.custom_values or {})
        payload = services.effective_attributes(room)
        payload["inherited"] = inherited
        return Response(jsonable(payload))

    @extend_schema(request=ResetOverrideSerializer, responses=RoomSerializer)
    @action(detail=True, methods=["post"], url_path="reset-override")
    def reset_override(self, request, pk=None):
        room = self.get_object()
        serializer = ResetOverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reset_override(room, serializer.validated_data["field"], actor=request.user)
        return self._respond(room)

    @extend_schema(request=RoomStatusSerializer, responses=RoomSerializer)
    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        room = self.get_object()
        serializer = RoomStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_housekeeping_status(
            room, serializer.validated_data["housekeeping_status"], actor=request.user, source="user"
        )
        return self._respond(room)


# ---- Beds ----------------------------------------------------------------------------------------------


class BedViewSet(InventoryMixin, viewsets.ModelViewSet):
    """Sellable beds of a dorm room (`room_id` in the URL)."""

    queryset = Bed.objects.all()
    serializer_class = BedSerializer
    property_field = "room__property"

    def get_room(self):
        if not hasattr(self, "_room"):
            self._room = get_object_or_404(
                Room.objects.select_related("room_type", "property"),
                pk=self.kwargs["room_id"],
                property=self.request.property,
            )
        return self._room

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False) and "room_id" in self.kwargs:
            context["room"] = self.get_room()
        return context

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Bed.objects.none()
        return Bed.objects.filter(room=self.get_room()).order_by(Length("label"), "label")

    def perform_create(self, serializer):
        serializer.instance = services.save_bed(
            self.get_room(), data=serializer.validated_data, actor=self.request.user
        )

    def perform_update(self, serializer):
        serializer.instance = services.save_bed(
            self.get_room(), data=serializer.validated_data, bed=serializer.instance, actor=self.request.user
        )

    def perform_destroy(self, instance):
        services.delete_bed(instance, actor=self.request.user)

    @extend_schema(request=BedBulkSerializer, responses={201: BedSerializer(many=True)})
    @action(detail=False, methods=["post"])
    def bulk(self, request, room_id=None):
        serializer = BedBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        beds = services.create_beds(self.get_room(), actor=request.user, **serializer.validated_data)
        return Response(BedSerializer(beds, many=True).data, status=status.HTTP_201_CREATED)


# ---- Custom fields -------------------------------------------------------------------------------------


class CustomFieldViewSet(InventoryMixin, viewsets.ModelViewSet):
    """Definitions of the organization (every property) and of the active property."""

    queryset = CustomFieldDefinition.objects.all()
    serializer_class = CustomFieldDefinitionSerializer
    filterset_fields = ["applies_to"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CustomFieldDefinition.objects.none()
        return CustomFieldDefinition.objects.filter(
            Q(property__isnull=True) | Q(property=self.request.property),
            organization=self.request.organization,
        ).order_by("applies_to", "sort_order", "key")

    def perform_create(self, serializer):
        scope = serializer.validated_data.pop("scope", "organization")
        services.create_custom_field(
            serializer,
            organization=self.request.organization,
            property=self.request.property if scope == "property" else None,
            actor=self.request.user,
        )

    def perform_update(self, serializer):
        services.update_custom_field(serializer, actor=self.request.user)

    def perform_destroy(self, instance):
        services.delete_custom_field(instance, actor=self.request.user)


# ---- Blocks --------------------------------------------------------------------------------------------


@extend_schema(
    parameters=[
        OpenApiParameter("active", OpenApiTypes.BOOL, description="Solo no liberados"),
        OpenApiParameter(
            "current", OpenApiTypes.BOOL, description="No liberados y vigentes desde la fecha de negocio"
        ),
        OpenApiParameter("room", OpenApiTypes.UUID),
        OpenApiParameter("bed", OpenApiTypes.UUID),
        OpenApiParameter("kind", OpenApiTypes.STR),
        OpenApiParameter("start", OpenApiTypes.DATE, description="Se cruza con [start, end)"),
        OpenApiParameter("end", OpenApiTypes.DATE),
    ]
)
class RoomBlockViewSet(
    InventoryMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = RoomBlock.objects.all()
    serializer_class = RoomBlockSerializer
    pagination_class = StandardPagination
    property_field = "room__property"
    filter_backends: list = []

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return RoomBlock.objects.none()
        params = self.request.query_params
        blocks = RoomBlock.objects.filter(room__property=self.request.property).select_related(
            "room", "bed", "created_by"
        )
        if params.get("active") in ("true", "1"):
            blocks = blocks.filter(released_at__isnull=True)
        elif params.get("active") in ("false", "0"):
            blocks = blocks.filter(released_at__isnull=False)
        if params.get("current") in ("true", "1"):
            blocks = blocks.filter(released_at__isnull=True, end_date__gt=self.request.property.business_date)
        for field in ("room", "bed", "kind"):
            if params.get(field):
                blocks = blocks.filter(**{f"{field}_id" if field != "kind" else field: params[field]})
        start, end = _date_param(params, "start"), _date_param(params, "end")
        if start:
            blocks = blocks.filter(end_date__gt=start)
        if end:
            blocks = blocks.filter(start_date__lt=end)
        return blocks.order_by("start_date", "created_at")

    @extend_schema(request=RoomBlockCreateSerializer, responses={201: RoomBlockSerializer})
    def create(self, request, *args, **kwargs):
        serializer = RoomBlockCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not data["force"]:
            _ensure_no_reservations(data["room"], data["bed"], data["start_date"], data["end_date"])
        block = services.block_room(
            data["room"], start=data["start_date"], end=data["end_date"], kind=data["kind"],
            reason=data["reason"], actor=request.user, bed=data["bed"],
        )  # fmt: skip
        return Response(RoomBlockSerializer(block).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=RoomBlockSerializer)
    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        block = services.release_block(self.get_object(), actor=request.user)
        return Response(RoomBlockSerializer(block).data)


def _date_param(params, name):
    from datetime import date

    from rest_framework.exceptions import ValidationError

    raw = params.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ValidationError({name: ["Fecha inválida (AAAA-MM-DD)"]}) from None


def _ensure_no_reservations(room, bed, start, end):
    """Blocking a room (or bed) that active stays occupy in the period needs `force` (409 otherwise)."""
    from apps.bookings.models import ACTIVE_STAY_STATUSES, Stay
    from apps.core.errors import ConflictError

    stays = Stay.objects.filter(
        room=room, status__in=ACTIVE_STAY_STATUSES, checkin_date__lt=end, checkout_date__gt=start
    ).select_related("reservation")
    if bed is not None:
        stays = stays.filter(Q(bed=bed) | Q(bed__isnull=True))
    codes = sorted({stay.reservation.code for stay in stays})
    if codes:
        raise ConflictError(
            f"La habitación tiene reservas en esas fechas ({', '.join(codes)}); usa force para bloquearla",
            code="room_has_reservations",
            reservations=codes,
        )


# ---- Property profile, logo, summary -------------------------------------------------------------------


class PropertyProfileView(PropertyScopedAPIView):
    """`GET/PATCH property/`: profile of the active property (never another one, whatever the body says)."""

    required_permissions = {"get": VIEW, "patch": MANAGE}

    @extend_schema(responses=PropertyProfileSerializer)
    def get(self, request):
        return Response(PropertyProfileSerializer(request.property).data)

    @extend_schema(request=PropertyProfileSerializer, responses=PropertyProfileSerializer)
    def patch(self, request):
        serializer = PropertyProfileSerializer(request.property, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        prop = services.update_property_profile(request.property, serializer, actor=request.user)
        return Response(PropertyProfileSerializer(prop).data)


class PropertyLogoView(PropertyScopedAPIView):
    """`POST property/logo/` (multipart `image`: JPG/PNG/WEBP ≤ 10 MB) · `DELETE property/logo/`."""

    required_permissions = {"post": MANAGE, "delete": MANAGE}
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(request=PhotoUploadSerializer, responses=PropertyProfileSerializer)
    def post(self, request):
        upload = PhotoUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        prop = services.set_property_logo(
            request.property, image=upload.validated_data["image"], actor=request.user
        )
        return Response(PropertyProfileSerializer(prop).data)

    @extend_schema(request=None, responses=PropertyProfileSerializer)
    def delete(self, request):
        prop = services.remove_property_logo(request.property, actor=request.user)
        return Response(PropertyProfileSerializer(prop).data)


class SummaryView(PropertyScopedAPIView):
    """`GET summary/`: units per category, totals, housekeeping counts, warnings, missing profile fields."""

    required_permissions = {"get": VIEW}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(services.inventory_summary(request.property))
