"""Serializers of the bookings API. Read shapes are documented in docs/integration-notes/B2b-bookings.md."""

from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.bookings.models import BookingStatus, GroupBlock, Reservation, ReservationGroup, Stay
from apps.bookings.services.policies import policy_snapshot
from apps.bookings.services.pricing import money_str
from apps.bookings.services.rooms import READY_STATUSES
from apps.bookings.types import BookingError, ReservationRequest, StayRequest
from apps.guests.models import Guest
from apps.guests.types import GuestInput
from apps.inventory.models import Bed, Room, RoomType
from apps.rates.models import RatePlan

ACTIVE_NOT_IN_HOUSE = (BookingStatus.TENTATIVE, BookingStatus.CONFIRMED)


# --- references -----------------------------------------------------------------------------------


class BookingRoomTypeRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomType
        fields = ["id", "code", "name", "kind", "color"]


class BookingRatePlanRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = RatePlan
        fields = ["id", "code", "name", "meal_plan"]


class BookingRoomRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ["id", "number", "floor", "housekeeping_status"]


class BookingRoomNumberSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ["id", "number"]


class BookingBedRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bed
        fields = ["id", "label"]


class BookingGroupRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReservationGroup
        fields = ["id", "name"]


class BookingUserRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    email = serializers.EmailField()


class BookingGuestBriefSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Guest
        fields = ["id", "full_name", "email", "phone", "is_vip", "nationality"]


class BookingGuestSummarySerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    is_foreign_non_resident = serializers.BooleanField(read_only=True)

    class Meta:
        model = Guest
        fields = [
            "id",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "phone",
            "document_type",
            "document_number",
            "nationality",
            "country_of_residence",
            "language",
            "is_vip",
            "is_foreign_non_resident",
        ]


class BookingNightEntrySerializer(serializers.Serializer):
    date = serializers.DateField()
    amount = serializers.CharField()
    net = serializers.CharField(required=False)
    tax = serializers.CharField(required=False)


# --- read shapes ----------------------------------------------------------------------------------


class BookingStayBriefSerializer(serializers.ModelSerializer):
    room_type = BookingRoomTypeRefSerializer()
    room = BookingRoomNumberSerializer(allow_null=True)
    bed = BookingBedRefSerializer(allow_null=True)

    class Meta:
        model = Stay
        fields = ["id", "status", "room_type", "room", "bed"]


class BookingStaySerializer(serializers.ModelSerializer):
    nights = serializers.SerializerMethodField()
    group_block_id = serializers.UUIDField(
        read_only=True, allow_null=True, help_text="Tomada del cupo de un grupo"
    )
    room_type = BookingRoomTypeRefSerializer()
    rate_plan = BookingRatePlanRefSerializer()
    room = BookingRoomRefSerializer(allow_null=True)
    bed = BookingBedRefSerializer(allow_null=True)
    nightly_rates = BookingNightEntrySerializer(many=True)
    occupants = BookingGuestSummarySerializer(many=True)

    class Meta:
        model = Stay
        fields = [
            "id",
            "status",
            "checkin_date",
            "checkout_date",
            "nights",
            "adults",
            "children",
            "children_ages",
            "room_type",
            "rate_plan",
            "room",
            "bed",
            "locked_room",
            "nightly_rates",
            "total_amount",
            "checked_in_at",
            "checked_out_at",
            "occupants",
            "group_block_id",
        ]

    def get_nights(self, obj) -> int:
        return (obj.checkout_date - obj.checkin_date).days


class BookingStayDetailSerializer(BookingStaySerializer):
    reservation_id = serializers.UUIDField(read_only=True)
    code = serializers.CharField(source="reservation.code", read_only=True)

    class Meta(BookingStaySerializer.Meta):
        fields = [*BookingStaySerializer.Meta.fields, "reservation_id", "code"]


class ReservationListSerializer(serializers.ModelSerializer):
    nights = serializers.SerializerMethodField()
    balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    booker = BookingGuestBriefSerializer()
    group = BookingGroupRefSerializer(allow_null=True)
    stays = BookingStayBriefSerializer(many=True)

    class Meta:
        model = Reservation
        fields = [
            "id",
            "code",
            "status",
            "source",
            "channel_code",
            "external_id",
            "checkin_date",
            "checkout_date",
            "nights",
            "adults",
            "children",
            "currency",
            "total_amount",
            "balance",
            "guarantee",
            "hold_expires_at",
            "created_at",
            "booker",
            "group",
            "stays",
        ]

    def get_nights(self, obj) -> int:
        return (obj.checkout_date - obj.checkin_date).days


class ReservationFlagsSerializer(serializers.Serializer):
    ready_for_checkin = serializers.BooleanField()
    arrives_today = serializers.BooleanField()
    departs_today = serializers.BooleanField()
    in_house = serializers.BooleanField()
    unassigned = serializers.BooleanField()
    balance_due = serializers.BooleanField()


class ReservationDetailSerializer(ReservationListSerializer):
    """`balance` = `finance.reservation_balance` (cached per request in the serializer context), `folio_id`
    = the reservation's guest folio, `portal_url` = `core.tokens.portal_url`, `flags` = front-desk hints."""

    balance = serializers.SerializerMethodField()
    booker = BookingGuestSummarySerializer()
    stays = BookingStaySerializer(many=True)
    created_by = serializers.SerializerMethodField()
    folio_id = serializers.SerializerMethodField()
    portal_url = serializers.SerializerMethodField()
    flags = serializers.SerializerMethodField()

    class Meta(ReservationListSerializer.Meta):
        fields = [
            *ReservationListSerializer.Meta.fields,
            "language",
            "eta",
            "special_requests",
            "notes",
            "promo_code",
            "cancellation_policy_snapshot",
            "cancelled_at",
            "cancellation_reason",
            "cancellation_fee",
            "custom_values",
            "tags",
            "external_payload",
            "created_by",
            "updated_at",
            "folio_id",
            "portal_url",
            "flags",
        ]

    @extend_schema_field(OpenApiTypes.DECIMAL)
    def get_balance(self, obj) -> str:
        return money_str(self._balance(obj))

    @extend_schema_field(BookingUserRefSerializer(allow_null=True))
    def get_created_by(self, obj):
        user = obj.created_by
        return (
            None if user is None else {"id": str(user.pk), "full_name": user.full_name, "email": user.email}
        )

    @extend_schema_field(OpenApiTypes.UUID)
    def get_folio_id(self, obj):
        from apps.finance.models import Folio

        folio = (
            Folio.objects.filter(reservation=obj, stay__isnull=True, folio_type="guest")
            .order_by("created_at")
            .values_list("pk", flat=True)
            .first()
        )
        return str(folio) if folio else None

    def get_portal_url(self, obj) -> str:
        from apps.core.tokens import portal_url

        return portal_url(obj) if settings.FRONTEND_URL else ""

    @extend_schema_field(ReservationFlagsSerializer)
    def get_flags(self, obj):
        today = obj.property.business_date
        stays = list(obj.stays.all())
        waiting = [stay for stay in stays if stay.status in ACTIVE_NOT_IN_HOUSE]
        return {
            "ready_for_checkin": (
                obj.status == BookingStatus.CONFIRMED
                and obj.checkin_date <= today < obj.checkout_date
                and bool(waiting)
                and all(
                    stay.room is not None and stay.room.housekeeping_status in READY_STATUSES
                    for stay in waiting
                )
            ),
            "arrives_today": obj.checkin_date == today and obj.status in ACTIVE_NOT_IN_HOUSE,
            "departs_today": obj.checkout_date == today and obj.status == BookingStatus.CHECKED_IN,
            "in_house": obj.status == BookingStatus.CHECKED_IN,
            "unassigned": any(stay.room_id is None for stay in waiting),
            "balance_due": self._balance(obj) > 0,
        }

    def _balance(self, obj):
        from apps.finance.services import reservation_balance

        cache = self.context.setdefault("_balances", {})
        if obj.pk not in cache:
            cache[obj.pk] = reservation_balance(obj)
        return cache[obj.pk]


class BookingOfferRoomTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomType
        fields = ["id", "code", "name", "kind", "color", "max_adults", "max_children", "max_occupancy"]


class BookingOfferRatePlanSerializer(serializers.ModelSerializer):
    cancellation_policy = serializers.SerializerMethodField()

    class Meta:
        model = RatePlan
        fields = ["id", "code", "name", "meal_plan", "is_public", "deposit_percent", "cancellation_policy"]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_cancellation_policy(self, obj):
        return policy_snapshot(obj) or None


class BookingOfferSerializer(serializers.Serializer):
    room_type_id = serializers.UUIDField()
    rate_plan_id = serializers.UUIDField()
    room_type = BookingOfferRoomTypeSerializer()
    rate_plan = BookingOfferRatePlanSerializer()
    available_units = serializers.IntegerField()
    units_needed = serializers.IntegerField()
    quote = serializers.JSONField(help_text="Quote.to_dict() (rates contract), per unit")
    total = serializers.DecimalField(max_digits=14, decimal_places=2)


class BookingGroupFiguresSerializer(serializers.Serializer):
    """`services.groups.group_figures` (documentation only)."""

    start = serializers.DateField(allow_null=True)
    end = serializers.DateField(allow_null=True)
    reservations = serializers.IntegerField()
    rooms = serializers.IntegerField()
    blocks = serializers.IntegerField()
    blocked_units = serializers.IntegerField()
    picked_rooms = serializers.IntegerField()
    room_nights = serializers.IntegerField()
    picked_room_nights = serializers.IntegerField()
    pickup_pct = serializers.FloatField(allow_null=True)
    balance = serializers.DecimalField(max_digits=14, decimal_places=2)
    state = serializers.ChoiceField(choices=["upcoming", "in_house", "past", "empty"])


class BookingGroupSerializer(serializers.ModelSerializer):
    contact_guest_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    contact_guest = BookingGuestBriefSerializer(read_only=True, allow_null=True)
    reservations_count = serializers.SerializerMethodField()
    figures = serializers.SerializerMethodField()

    class Meta:
        model = ReservationGroup
        fields = [
            "id",
            "name",
            "notes",
            "contact_guest_id",
            "contact_guest",
            "reservations_count",
            "figures",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_reservations_count(self, obj) -> int:
        annotated = getattr(obj, "reservations_count", None)  # list/retrieve annotate it
        return annotated if annotated is not None else obj.reservations.count()

    @extend_schema_field(BookingGroupFiguresSerializer(allow_null=True))
    def get_figures(self, obj):
        """Dates, rooms, pickup and balance (list and detail; computed per page in bulk by the view)."""
        return (self.context.get("figures") or {}).get(obj.pk)

    def validate_contact_guest_id(self, value):
        if value is None:
            return None
        organization = self.context["request"].organization
        guest = Guest.objects.filter(pk=value, organization=organization, merged_into__isnull=True).first()
        if guest is None:
            raise serializers.ValidationError("El huésped no existe en esta organización")
        return guest

    def create(self, validated_data):
        validated_data["contact_guest"] = validated_data.pop("contact_guest_id", None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "contact_guest_id" in validated_data:
            validated_data["contact_guest"] = validated_data.pop("contact_guest_id")
        return super().update(instance, validated_data)


# --- write shapes ---------------------------------------------------------------------------------


class BookingGuestInputSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    document_type = serializers.ChoiceField(
        choices=[("", "—"), *Guest.DocumentType.choices], required=False, allow_blank=True, default=""
    )
    document_number = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    nationality = serializers.CharField(max_length=2, required=False, allow_blank=True, default="")
    country_of_residence = serializers.CharField(max_length=2, required=False, allow_blank=True, default="")
    city_of_residence = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    birth_date = serializers.DateField(required=False, allow_null=True, default=None)
    language = serializers.CharField(max_length=5, required=False, default="es")
    marketing_consent = serializers.BooleanField(required=False, default=False)
    data_processing_consent = serializers.BooleanField(required=False, default=False)


def guest_input(data: dict) -> GuestInput:
    return GuestInput(**data)


class BookingNightlyRateInputSerializer(serializers.Serializer):
    date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)


class BookingStayRequestSerializer(serializers.Serializer):
    room_type_id = serializers.UUIDField()
    rate_plan_id = serializers.UUIDField()
    checkin = serializers.DateField()
    checkout = serializers.DateField()
    adults = serializers.IntegerField(min_value=0, max_value=50)
    children = serializers.IntegerField(min_value=0, max_value=50, required=False, default=0)
    children_ages = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=17), required=False, default=list
    )
    room_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    bed_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    locked_room = serializers.BooleanField(required=False, default=False)
    occupants = BookingGuestInputSerializer(many=True, required=False, default=list)
    occupant_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    nightly_rates = BookingNightlyRateInputSerializer(
        many=True, required=False, allow_null=True, default=None
    )
    group_block_id = serializers.UUIDField(
        required=False, allow_null=True, default=None, help_text="Tomada del cupo (allotment) de un grupo"
    )


def build_stay(prop, item: dict) -> tuple[StayRequest, GroupBlock | None]:
    """A validated `BookingStayRequestSerializer` item → (StayRequest, block it is picked up from)."""
    item = dict(item)
    block_id = item.pop("group_block_id", None)
    occupants = [guest_input(value) for value in item.pop("occupants", [])]
    occupants += [_guest_by_id(prop, value) for value in item.pop("occupant_ids", [])]
    rates = item.pop("nightly_rates", None)
    stay = StayRequest(
        **item,
        occupants=occupants,
        nightly_rates=[dict(rate) for rate in rates] if rates is not None else None,
    )
    return stay, (block_by_id(prop, block_id) if block_id else None)


def block_by_id(prop, block_id) -> GroupBlock:
    block = (
        GroupBlock.objects.select_related("group", "room_type")
        .filter(pk=block_id, group__property=prop)
        .first()
    )
    if block is None:
        raise BookingError("El cupo no existe en esta propiedad", code="invalid_block")
    return block


class ReservationCreateSerializer(serializers.Serializer):
    """Body of `POST reservations/` = ReservationRequest in JSON (booker as GuestInput or `booker_id`).

    Pilot plan P3: `group_name` creates a new `ReservationGroup` for it (the booker becomes its contact) and
    `stays[].group_block_id` picks that room up from a group allotment."""

    booker = BookingGuestInputSerializer(required=False)
    booker_id = serializers.UUIDField(required=False)
    stays = BookingStayRequestSerializer(many=True, allow_empty=False)
    source = serializers.ChoiceField(choices=Reservation.Source.choices, required=False, default="front_desk")
    channel_code = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    external_id = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    external_payload = serializers.DictField(required=False, default=dict)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    special_requests = serializers.CharField(required=False, allow_blank=True, default="")
    promo_code = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    language = serializers.CharField(max_length=5, required=False, default="es")
    eta = serializers.TimeField(required=False, allow_null=True, default=None)
    status = serializers.ChoiceField(choices=["confirmed", "tentative"], required=False, default="confirmed")
    allow_overbooking = serializers.BooleanField(required=False, default=False)
    enforce_restrictions = serializers.BooleanField(required=False, default=True)
    hold_minutes = serializers.IntegerField(min_value=0, max_value=60 * 24 * 30, required=False, default=20)
    guarantee = serializers.ChoiceField(choices=Reservation.Guarantee.choices, required=False, default="none")
    group_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    group_name = serializers.CharField(
        max_length=200,
        required=False,
        allow_blank=True,
        default="",
        help_text="Crea un grupo nuevo con este nombre",
    )
    custom_values = serializers.DictField(required=False, default=dict)

    def validate(self, attrs):
        if not attrs.get("booker") and not attrs.get("booker_id"):
            raise serializers.ValidationError({"booker": ["Indica el huésped (booker o booker_id)"]})
        if attrs.get("group_name", "").strip() and attrs.get("group_id"):
            raise serializers.ValidationError(
                {"group_name": ["Elige un grupo existente o uno nuevo, no ambos"]}
            )
        return attrs

    def build(self, prop) -> ReservationRequest:
        return self.build_all(prop)[0]

    def build_all(self, prop) -> tuple[ReservationRequest, dict, str]:
        """(ReservationRequest, {stay index: GroupBlock}, name of a new group or "")."""
        data = dict(self.validated_data)
        group_name = data.pop("group_name", "").strip()
        booker = (
            _guest_by_id(prop, data.pop("booker_id"))
            if data.get("booker_id")
            else guest_input(data["booker"])
        )
        data.pop("booker", None)
        stays, blocks = [], {}
        for index, item in enumerate(data.pop("stays")):
            stay, block = build_stay(prop, item)
            stays.append(stay)
            if block is not None:
                blocks[index] = block
        return ReservationRequest(property=prop, booker=booker, stays=stays, **data), blocks, group_name


def _guest_by_id(prop, guest_id) -> Guest:
    guest = Guest.objects.filter(pk=guest_id).first()
    if guest is None or guest.organization_id != prop.organization_id:
        raise BookingError("El huésped no existe en esta organización", code="invalid_guest")
    return guest


class ReservationUpdateSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True)
    special_requests = serializers.CharField(required=False, allow_blank=True)
    eta = serializers.TimeField(required=False, allow_null=True)
    language = serializers.CharField(max_length=5, required=False)
    guarantee = serializers.ChoiceField(choices=Reservation.Guarantee.choices, required=False)
    custom_values = serializers.DictField(required=False)
    tags = serializers.ListField(child=serializers.CharField(max_length=40), required=False)
    group_id = serializers.UUIDField(required=False, allow_null=True)
    booker_id = serializers.UUIDField(required=False)


class BookingCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    waive_fee = serializers.BooleanField(required=False, default=False)
    confirm = serializers.BooleanField(required=False, default=False)


class BookingForceSerializer(serializers.Serializer):
    force = serializers.BooleanField(required=False, default=False)


class BookingModifySerializer(serializers.Serializer):
    checkin = serializers.DateField(required=False)
    checkout = serializers.DateField(required=False)
    room_type_id = serializers.UUIDField(required=False)
    rate_plan_id = serializers.UUIDField(required=False)
    adults = serializers.IntegerField(min_value=0, max_value=50, required=False)
    children = serializers.IntegerField(min_value=0, max_value=50, required=False)
    reprice = serializers.BooleanField(required=False, default=True)


class BookingPreviewStaySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    checkin_date = serializers.DateField()
    checkout_date = serializers.DateField()
    nights = serializers.IntegerField()
    room_type_id = serializers.UUIDField()
    rate_plan_id = serializers.UUIDField()
    room_id = serializers.UUIDField(allow_null=True)
    bed_id = serializers.UUIDField(allow_null=True)
    adults = serializers.IntegerField()
    children = serializers.IntegerField()
    nightly_rates = BookingNightEntrySerializer(many=True)
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class BookingModifyPreviewSerializer(serializers.Serializer):
    """Response of `POST stays/{id}/modify-preview/` (documentation only)."""

    stay = BookingPreviewStaySerializer()
    room_kept = serializers.BooleanField(allow_null=True, help_text="null: the stay has no room yet")
    current_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    difference = serializers.DecimalField(max_digits=14, decimal_places=2)
    reservation_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    balance = serializers.DecimalField(max_digits=14, decimal_places=2)


class BookingRoomOptionSerializer(serializers.Serializer):
    """An item of `GET stays/{id}/room-options/` (documentation only)."""

    room_id = serializers.UUIDField()
    room_number = serializers.CharField()
    floor = serializers.CharField()
    room_type_id = serializers.UUIDField()
    room_type_code = serializers.CharField()
    bed_id = serializers.UUIDField(allow_null=True)
    bed_label = serializers.CharField(allow_null=True)
    housekeeping_status = serializers.CharField()
    ready = serializers.BooleanField(help_text="clean or inspected")
    same_category = serializers.BooleanField(help_text="false: another category (assign with force)")


class BookingAssignSerializer(serializers.Serializer):
    room_id = serializers.UUIDField()
    bed_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    force = serializers.BooleanField(required=False, default=False)


class BookingOccupantSerializer(serializers.Serializer):
    guest_id = serializers.UUIDField(required=False)
    guest = BookingGuestInputSerializer(required=False)

    def validate(self, attrs):
        if not attrs.get("guest_id") and not attrs.get("guest"):
            raise serializers.ValidationError({"guest_id": ["Indica guest_id o guest"]})
        return attrs


class BookingDateRangeQuerySerializer(serializers.Serializer):
    checkin = serializers.DateField()
    checkout = serializers.DateField()

    def validate(self, attrs):
        if attrs["checkout"] <= attrs["checkin"]:
            raise serializers.ValidationError({"checkout": ["La salida debe ser posterior a la llegada"]})
        return attrs


class BookingOffersQuerySerializer(BookingDateRangeQuerySerializer):
    adults = serializers.IntegerField(min_value=1, max_value=50, required=False, default=2)
    children = serializers.IntegerField(min_value=0, max_value=50, required=False, default=0)
    children_ages = serializers.CharField(required=False, allow_blank=True, default="")
    channel = serializers.CharField(max_length=40, required=False, default="direct")
    promo_code = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    foreign = serializers.BooleanField(required=False, default=False)

    def validate_children_ages(self, value):
        try:
            return [int(item) for item in value.replace(";", ",").split(",") if item.strip()]
        except ValueError:
            raise serializers.ValidationError("Edades inválidas (ej. 4,7)") from None


class BookingCalendarQuerySerializer(serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField()

    def validate(self, attrs):
        if attrs["end"] <= attrs["start"]:
            raise serializers.ValidationError({"end": ["El fin debe ser posterior al inicio"]})
        return attrs


class BookingAutoAssignSerializer(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()


class BookingRebuildSerializer(serializers.Serializer):
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)
    room_type_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)


# --- multi-room, groups and allotments (pilot plan P3) --------------------------------------------------


class BookingQuoteSerializer(serializers.Serializer):
    """Body of `POST reservations/quote/`: the stays to price (same shape as in `POST reservations/`)."""

    stays = BookingStayRequestSerializer(many=True, allow_empty=False)
    promo_code = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    foreign = serializers.BooleanField(
        required=False, default=False, help_text="Titular extranjero no residente"
    )


class BookingQuoteLineSerializer(serializers.Serializer):
    index = serializers.IntegerField()
    room_type_id = serializers.UUIDField()
    rate_plan_id = serializers.UUIDField()
    checkin = serializers.DateField()
    checkout = serializers.DateField()
    nights = serializers.IntegerField()
    adults = serializers.IntegerField()
    children = serializers.IntegerField()
    units = serializers.IntegerField(help_text="Unidades (camas de dormitorio: una por huésped)")
    total = serializers.DecimalField(max_digits=14, decimal_places=2)
    per_night = serializers.DecimalField(max_digits=14, decimal_places=2)
    restrictions_ok = serializers.BooleanField()
    violations = serializers.ListField(child=serializers.CharField())


class BookingQuoteResultSerializer(serializers.Serializer):
    """Response of `POST reservations/quote/` (documentation only)."""

    currency = serializers.CharField()
    total = serializers.DecimalField(max_digits=14, decimal_places=2)
    stays = BookingQuoteLineSerializer(many=True)


class BookingAddStaySerializer(BookingStayRequestSerializer):
    """Body of `POST reservations/{id}/stays/`: the offer of the new room (dates: the reservation's by
    default)."""

    checkin = serializers.DateField(required=False)
    checkout = serializers.DateField(required=False)
    allow_overbooking = serializers.BooleanField(required=False, default=False)
    enforce_restrictions = serializers.BooleanField(required=False, default=False)


class BookingStayCancelPreviewSerializer(serializers.Serializer):
    """Response of `GET stays/{id}/cancel-preview/` (documentation only)."""

    fee = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField()
    reason = serializers.CharField()
    free_until = serializers.DateTimeField(allow_null=True)
    non_refundable = serializers.BooleanField()
    policy = serializers.JSONField()
    stay_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    cancels_reservation = serializers.BooleanField(
        help_text="Última habitación activa: se cancela la reserva"
    )
    ends_reservation = serializers.BooleanField(
        help_text="Las demás ya salieron: la reserva queda finalizada"
    )


class BookingRoomingSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


class BookingBlockSerializer(serializers.ModelSerializer):
    """An allotment with its pickup (`services.blocks.pickup_summary`)."""

    group_id = serializers.UUIDField(read_only=True)
    room_type = BookingRoomTypeRefSerializer(read_only=True)
    pickup = serializers.SerializerMethodField()

    class Meta:
        model = GroupBlock
        fields = [
            "id",
            "group_id",
            "room_type",
            "start",
            "end",
            "units",
            "release_date",
            "released_at",
            "pickup",
            "created_at",
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_pickup(self, obj):
        from apps.bookings.services.blocks import pickup_summary

        return pickup_summary(obj)


class BookingBlockCreateSerializer(serializers.Serializer):
    room_type_id = serializers.UUIDField()
    start = serializers.DateField()
    end = serializers.DateField()
    units = serializers.IntegerField(min_value=1, max_value=500)
    release_date = serializers.DateField()
    allow_overbooking = serializers.BooleanField(required=False, default=False)


class BookingBlockUpdateSerializer(serializers.Serializer):
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)
    units = serializers.IntegerField(min_value=1, max_value=500, required=False)
    release_date = serializers.DateField(required=False)
    allow_overbooking = serializers.BooleanField(required=False, default=False)


class BookingRoomOffersQuerySerializer(BookingDateRangeQuerySerializer):
    promo_code = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    foreign = serializers.BooleanField(required=False, default=False)
    block = serializers.UUIDField(required=False, allow_null=True, default=None)
