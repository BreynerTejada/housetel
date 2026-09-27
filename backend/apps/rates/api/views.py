"""Staff API of `rates` (`/api/v1/rates/`, header `X-Property-Id`): `rates.view` reads, `rates.manage`
writes. The staff quote tool only needs `rates.view` (it writes nothing)."""

from datetime import date

from django.db.models import Count, Prefetch
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response

from apps.core.errors import ConflictError
from apps.core.tenancy import PropertyScopedAPIView, PropertyScopedViewSet
from apps.inventory.models import RoomType
from apps.rates.api import serializers as s
from apps.rates.models import (
    CancellationPolicy,
    Extra,
    PromoCode,
    RatePlan,
    RoomTypeRateDefaults,
    Season,
    SeasonRate,
    Tax,
)
from apps.rates.services import notify
from apps.rates.services.calendar import holiday_list
from apps.rates.services.grid import build_grid, default_plan
from apps.rates.services.quote import quote
from apps.rates.services.writes import bulk_update_rates

CONFIG_PERMISSIONS = {"list": "rates.view", "retrieve": "rates.view", "*": "rates.manage"}
IN_USE_MESSAGE = "Está en uso: desactívalo en lugar de eliminarlo"
GRID_FIELDS = {"cta": "closed_to_arrival", "ctd": "closed_to_departure"}
LANG_HELP = "Idioma de los nombres de los festivos; por defecto, el del usuario"


def user_language(request, asked: str | None = None) -> str:
    """The language the screen asked for (`?lang=`), else the user's (es by default)."""
    if asked:
        return asked
    return "en" if getattr(request.user, "language", "es") == "en" else "es"


class RatesViewSet(PropertyScopedViewSet):
    required_permissions = CONFIG_PERMISSIONS


class TaxViewSet(RatesViewSet):
    queryset = Tax.objects.all()
    serializer_class = s.TaxSerializer
    filterset_fields = ["applies_to", "is_active"]

    def perform_destroy(self, instance):
        if instance.extras.exists() or instance.charges.exists():
            raise ConflictError(IN_USE_MESSAGE, code="in_use")
        instance.delete()


class CancellationPolicyViewSet(RatesViewSet):
    queryset = CancellationPolicy.objects.annotate(plans_count=Count("rate_plans")).order_by("created_at")
    serializer_class = s.CancellationPolicySerializer

    def perform_destroy(self, instance):
        if instance.rate_plans.exists():
            raise ConflictError(IN_USE_MESSAGE, code="in_use")
        instance.delete()


class RatePlanViewSet(RatesViewSet):
    queryset = RatePlan.objects.select_related("property").prefetch_related("room_types", "children")
    serializer_class = s.RatePlanSerializer
    filterset_fields = ["kind", "is_active", "is_public", "parent"]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        notify.announce_plan(serializer.instance)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        notify.announce_plan(serializer.instance)


class UpsertMixin:
    """`POST` creates the row or, when one exists for `upsert_keys`, updates it (201 / 200)."""

    upsert_keys: tuple[str, ...] = ()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        keys = {key: serializer.validated_data[key] for key in self.upsert_keys}
        instance = self.get_serializer_class().Meta.model.objects.filter(**keys).first()
        if instance is None:
            instance = serializer.save()
            code = status.HTTP_201_CREATED
        else:
            for field, value in serializer.validated_data.items():
                setattr(instance, field, value)
            instance.save()
            code = status.HTTP_200_OK
        self.announce(instance)
        return Response(self.get_serializer(instance).data, status=code)

    def perform_update(self, serializer):
        serializer.save()
        self.announce(serializer.instance)

    def perform_destroy(self, instance):
        self.announce(instance)
        instance.delete()


class RoomTypeRateDefaultsViewSet(UpsertMixin, RatesViewSet):
    queryset = RoomTypeRateDefaults.objects.select_related("rate_plan__property").order_by(
        "rate_plan__sort_order", "rate_plan__code", "room_type__sort_order", "room_type__code"
    )
    serializer_class = s.RoomTypeRateDefaultsSerializer
    property_field = "rate_plan__property"
    filterset_fields = ["rate_plan", "room_type"]
    upsert_keys = ("room_type", "rate_plan")

    def announce(self, instance):
        notify.announce_defaults(instance)


class SeasonViewSet(RatesViewSet):
    queryset = Season.objects.prefetch_related(
        Prefetch("rates", queryset=SeasonRate.objects.order_by("created_at"))
    )
    serializer_class = s.SeasonSerializer

    def perform_update(self, serializer):
        before = (serializer.instance.start_date, serializer.instance.end_date)
        serializer.save()
        notify.announce_season(serializer.instance, also_start=before[0], also_end=before[1])

    def perform_destroy(self, instance):
        notify.announce_season(instance)
        instance.delete()


class SeasonRateViewSet(UpsertMixin, RatesViewSet):
    queryset = SeasonRate.objects.select_related("season__property", "rate_plan").order_by(
        "season__start_date", "room_type__sort_order", "room_type__code"
    )
    serializer_class = s.SeasonRateSerializer
    property_field = "season__property"
    filterset_fields = ["season", "rate_plan", "room_type"]
    upsert_keys = ("season", "room_type", "rate_plan")

    def announce(self, instance):
        notify.announce_season_rate(instance)


class ExtraViewSet(RatesViewSet):
    queryset = Extra.objects.all()
    serializer_class = s.ExtraSerializer
    filterset_fields = ["charge_type", "is_active", "sellable_online"]

    def perform_destroy(self, instance):
        if instance.charges.exists():
            raise ConflictError(IN_USE_MESSAGE, code="in_use")
        instance.delete()


class PromoCodeViewSet(RatesViewSet):
    queryset = PromoCode.objects.prefetch_related("rate_plans")
    serializer_class = s.PromoCodeSerializer
    filterset_fields = ["is_active", "discount_type"]


class RoomTypesView(PropertyScopedAPIView):
    """`GET room-types/` → categories of the property (lookup for plan, defaults and season editors)."""

    required_permissions = {"get": "rates.view"}

    @extend_schema(responses=s.RoomTypeLookupSerializer(many=True))
    def get(self, request):
        room_types = RoomType.objects.filter(property=request.property).order_by("sort_order", "code")
        return Response(s.RoomTypeLookupSerializer(room_types, many=True).data)


class GridView(PropertyScopedAPIView):
    """`GET grid/?start&end&rate_plan` → categories × nights of one plan (`end` exclusive, ≤ 186 nights)."""

    required_permissions = {"get": "rates.view"}

    @extend_schema(
        parameters=[
            OpenApiParameter("start", OpenApiTypes.DATE, required=True),
            OpenApiParameter("end", OpenApiTypes.DATE, required=True, description="Exclusivo"),
            OpenApiParameter("rate_plan", OpenApiTypes.UUID, description="Por defecto, el primer plan base"),
            OpenApiParameter("lang", OpenApiTypes.STR, enum=["es", "en"], description=LANG_HELP),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        query = s.GridQuerySerializer(data=request.query_params, context={"request": request})
        query.is_valid(raise_exception=True)
        plan = query.validated_data.get("rate_plan") or default_plan(request.property)
        return Response(
            build_grid(
                request.property,
                rate_plan=plan,
                start=query.validated_data["start"],
                end=query.validated_data["end"],
                lang=user_language(request, query.validated_data.get("lang")),
            )
        )


class GridBulkView(PropertyScopedAPIView):
    """`POST grid/bulk/` → writes the grid of a base plan (one reversible audit event per call)."""

    required_permissions = {"post": "rates.manage"}

    @extend_schema(request=s.GridBulkSerializer, responses=s.GridBulkResultSerializer)
    def post(self, request):
        body = s.GridBulkSerializer(data=request.data, context={"request": request})
        body.is_valid(raise_exception=True)
        data = body.validated_data
        changes = dict(data["set"])
        price = changes.pop("price", None)
        restrictions = {GRID_FIELDS.get(key, key): value for key, value in changes.items()}
        result = bulk_update_rates(
            property=request.property,
            room_types=data["room_type_ids"],
            rate_plan=data["rate_plan_id"],
            start=data["start"],
            end=data["end"],
            price=price,
            restrictions=restrictions,
            dow=data.get("weekdays") or None,
            source=data["source"],
            actor=request.user,
        )
        return Response(
            {"updated": result.updated, "audit_event_id": str(result.event.pk) if result.event else None}
        )


class QuoteView(PropertyScopedAPIView):
    """`POST quote/` → `Quote.to_dict()` (staff tool to test prices; writes nothing)."""

    required_permissions = {"post": "rates.view"}

    @extend_schema(request=s.QuoteRequestSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        body = s.QuoteRequestSerializer(data=request.data, context={"request": request})
        body.is_valid(raise_exception=True)
        data = body.validated_data
        result = quote(
            property=request.property,
            room_type=data["room_type_id"],
            rate_plan=data["rate_plan_id"],
            checkin=data["checkin"],
            checkout=data["checkout"],
            adults=data["adults"],
            children=data["children"],
            children_ages=data["children_ages"],
            promo_code=data["promo_code"] or None,
            guest_is_foreign_non_resident=data["guest_is_foreign_non_resident"],
        )
        return Response(result.to_dict())


class HolidaysView(PropertyScopedAPIView):
    """`GET holidays/?year=` or `?start&end` (end exclusive) → Colombian holidays in the user's language."""

    required_permissions = {"get": "rates.view"}

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "year", OpenApiTypes.INT, description="Por defecto, el año de la fecha de negocio"
            ),
            OpenApiParameter("start", OpenApiTypes.DATE),
            OpenApiParameter("end", OpenApiTypes.DATE, description="Exclusivo"),
            OpenApiParameter("lang", OpenApiTypes.STR, enum=["es", "en"], description=LANG_HELP),
        ],
        responses=s.HolidaySerializer(many=True),
    )
    def get(self, request):
        query = s.HolidaysQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        if "start" in data:
            start, end = data["start"], data["end"]
        else:
            year = data.get("year") or request.property.business_date.year
            start, end = date(year, 1, 1), date(year + 1, 1, 1)
        return Response(holiday_list(start, end, user_language(request, data.get("lang"))))
