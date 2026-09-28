"""Serializers of the staff distribution API. Choice-like fields are plain strings (documented in `help_text`)
so the OpenAPI schema gets no enum whose name collides with other apps (`status`, `mode`…)."""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core import integrations
from apps.distribution.errors import ChannelError
from apps.distribution.models import AriUpdate, ChannelConnection, SimOtaBooking, SyncLog
from apps.distribution.providers import (
    CHANNEL_KINDS,
    SIM_CHANNELS,
    check_public_url,
    connection_mode,
    normalize_calendar_url,
)
from apps.distribution.services.connections import (
    ICAL,
    SETTINGS_SCHEMA,
    channel_label,
    config_fields,
    delivery,
    integration_info,
)
from apps.inventory.models import Room, RoomType
from apps.rates.models import RatePlan

MARKUP_MIN, MARKUP_MAX = Decimal("-90"), Decimal("300")
CHANNEL_CODES = [choice for choice, _label in ChannelConnection.Channel.choices]
MODES = ["real", "simulated"]


# --- read ---------------------------------------------------------------------------------------------------


class ChannelRoomMappingSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    room_type = serializers.UUIDField(source="room_type_id")
    room_type_code = serializers.CharField(source="room_type.code")
    room_type_name = serializers.JSONField(source="room_type.name")
    room = serializers.UUIDField(source="room_id", allow_null=True)
    room_number = serializers.SerializerMethodField()
    external_room_id = serializers.CharField()
    ical_import_url = serializers.CharField()
    ical_export_url = serializers.SerializerMethodField()
    ical_last_sync_at = serializers.DateTimeField(allow_null=True)
    ical_last_error = serializers.CharField()

    def get_room_number(self, mapping) -> str | None:
        return mapping.room.number if mapping.room_id else None

    def get_ical_export_url(self, mapping) -> str | None:
        from apps.distribution.services.ical import export_url

        return export_url(mapping) if mapping.connection.channel_code == ICAL else None


class ChannelRateMappingSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    rate_plan = serializers.UUIDField(source="rate_plan_id", allow_null=True)
    rate_plan_code = serializers.SerializerMethodField()
    rate_plan_name = serializers.SerializerMethodField()
    room_type = serializers.UUIDField(source="room_type_id", allow_null=True)
    room_type_code = serializers.SerializerMethodField()
    external_rate_id = serializers.CharField()
    markup_percent = serializers.DecimalField(max_digits=6, decimal_places=2)

    def get_rate_plan_code(self, mapping) -> str | None:
        return mapping.rate_plan.code if mapping.rate_plan_id else None

    @extend_schema_field(serializers.JSONField(allow_null=True))
    def get_rate_plan_name(self, mapping):
        return mapping.rate_plan.name if mapping.rate_plan_id else None

    def get_room_type_code(self, mapping) -> str | None:
        return mapping.room_type.code if mapping.room_type_id else None


class ChannelConnectionStatsSerializer(serializers.Serializer):
    pending_updates = serializers.IntegerField()
    failed_updates = serializers.IntegerField()
    reservations = serializers.IntegerField()
    errors_24h = serializers.IntegerField()
    in_errors_24h = serializers.IntegerField(help_text="Errores de entrada (reservas, calendarios) en 24 h")
    last_out_at = serializers.DateTimeField(allow_null=True, help_text="Último envío al canal")
    last_in_at = serializers.DateTimeField(allow_null=True, help_text="Última reserva o calendario recibido")


class ChannelIntegrationInfoSerializer(serializers.Serializer):
    kind = serializers.CharField()
    mode = serializers.CharField(help_text="real | simulated")
    enabled = serializers.BooleanField()
    config = serializers.DictField()
    secrets = serializers.ListField(
        child=serializers.CharField(), help_text="Secretos configurados (sin valor)"
    )


class ChannelConnectionSerializer(serializers.ModelSerializer):
    """A connection with its mappings. `delivery`: push (the OTA sends its bookings), pull (the PMS downloads
    them: Channex) or ical (calendars). `simulated`: served by the OTA simulator."""

    status = serializers.CharField(read_only=True, help_text="active | paused | error")
    channel_code = serializers.CharField(read_only=True, help_text="booksim | airsim | ical | channex")
    channel_label = serializers.SerializerMethodField()
    mode = serializers.SerializerMethodField(help_text="real | simulated")
    delivery = serializers.SerializerMethodField(help_text="push | pull | ical")
    simulated = serializers.SerializerMethodField()
    room_mappings = serializers.SerializerMethodField()
    rate_mappings = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()
    integration = serializers.SerializerMethodField()

    class Meta:
        model = ChannelConnection
        fields = [
            "id",
            "channel_code",
            "channel_label",
            "name",
            "status",
            "mode",
            "delivery",
            "simulated",
            "settings",
            "last_sync_at",
            "last_error",
            "created_at",
            "updated_at",
            "room_mappings",
            "rate_mappings",
            "stats",
            "integration",
        ]
        read_only_fields = fields

    def get_channel_label(self, connection) -> str:
        return channel_label(connection.channel_code)

    def get_mode(self, connection) -> str:
        return connection_mode(connection)

    def get_delivery(self, connection) -> str:
        return delivery(connection.channel_code)

    def get_simulated(self, connection) -> bool:
        if connection.channel_code == ICAL:
            return False
        return connection.channel_code in SIM_CHANNELS or connection_mode(connection) == "simulated"

    @extend_schema_field(ChannelRoomMappingSerializer(many=True))
    def get_room_mappings(self, connection):
        return ChannelRoomMappingSerializer(connection.room_mappings.all(), many=True).data

    @extend_schema_field(ChannelRateMappingSerializer(many=True))
    def get_rate_mappings(self, connection):
        return ChannelRateMappingSerializer(connection.rate_mappings.all(), many=True).data

    @extend_schema_field(ChannelConnectionStatsSerializer)
    def get_stats(self, connection):
        stats = self.context.get("stats")
        if stats is None:
            stats = connection_stats([connection])
        return stats.get(connection.pk, empty_stats())

    @extend_schema_field(ChannelIntegrationInfoSerializer(allow_null=True))
    def get_integration(self, connection):
        kind = CHANNEL_KINDS.get(connection.channel_code)
        return integration_info(connection.property, kind) if kind else None


class ChannelConnectionWriteResultSerializer(ChannelConnectionSerializer):
    """Response of create/update (schema only): the connection plus the summary of the full sync the call ran
    (`null` when it only queued the changes)."""

    sync = serializers.JSONField(
        allow_null=True, read_only=True, help_text="{sent, retrying, failed, connections}"
    )

    class Meta(ChannelConnectionSerializer.Meta):
        fields = [*ChannelConnectionSerializer.Meta.fields, "sync"]
        read_only_fields = fields


def empty_stats() -> dict:
    return {
        "pending_updates": 0,
        "failed_updates": 0,
        "reservations": 0,
        "errors_24h": 0,
        "in_errors_24h": 0,
        "last_out_at": None,
        "last_in_at": None,
    }


def connection_stats(connections) -> dict:
    """Counters per connection in four queries (queue, reservations, recent errors, last exchange per
    direction; connection tests do not count as exchanges)."""
    from django.db.models import Count, Max

    from apps.distribution.models import ExternalReservationMap

    ids = [connection.pk for connection in connections]
    stats = {pk: empty_stats() for pk in ids}
    for row in (
        AriUpdate.objects.filter(connection_id__in=ids)
        .exclude(status=AriUpdate.Status.SENT)
        .values("connection_id", "status")
        .annotate(total=Count("id"))
    ):
        key = "failed_updates" if row["status"] == AriUpdate.Status.FAILED else "pending_updates"
        stats[row["connection_id"]][key] += row["total"]
    for row in (
        ExternalReservationMap.objects.filter(connection_id__in=ids)
        .values("connection_id")
        .annotate(total=Count("id"))
    ):
        stats[row["connection_id"]]["reservations"] = row["total"]
    since = timezone.now() - timedelta(hours=24)
    for row in (
        SyncLog.objects.filter(connection_id__in=ids, status=SyncLog.Status.ERROR, created_at__gte=since)
        .values("connection_id", "direction")
        .annotate(total=Count("id"))
    ):
        stats[row["connection_id"]]["errors_24h"] += row["total"]
        if row["direction"] == SyncLog.Direction.IN:
            stats[row["connection_id"]]["in_errors_24h"] += row["total"]
    for row in (
        SyncLog.objects.filter(connection_id__in=ids)
        .exclude(kind="test")
        .values("connection_id", "direction")
        .annotate(last=Max("created_at"))
    ):
        key = "last_in_at" if row["direction"] == SyncLog.Direction.IN else "last_out_at"
        stats[row["connection_id"]][key] = row["last"]
    return stats


# --- write --------------------------------------------------------------------------------------------------


class ChannelRoomMappingInputSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False, help_text="Mapeo existente que se conserva")
    room_type = serializers.UUIDField()
    room = serializers.UUIDField(required=False, allow_null=True, help_text="Solo iCal: una habitación")
    external_room_id = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")
    ical_import_url = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class ChannelRateMappingInputSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    rate_plan = serializers.UUIDField()
    room_type = serializers.UUIDField(required=False, allow_null=True)
    external_rate_id = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")
    markup_percent = serializers.DecimalField(
        max_digits=6, decimal_places=2, required=False, default=Decimal("0")
    )


class ChannelIntegrationInputSerializer(serializers.Serializer):
    config = serializers.DictField(required=False, default=dict)
    secrets = serializers.DictField(
        child=serializers.CharField(allow_blank=True), required=False, default=dict
    )


class ChannelConnectionWriteSerializer(serializers.Serializer):
    """Create (`channel_code` required) or change a connection. A mappings list replaces the current one."""

    channel_code = serializers.CharField(required=False, help_text="booksim | airsim | ical | channex")
    name = serializers.CharField(required=False, allow_blank=True, max_length=120)
    settings = serializers.DictField(required=False, help_text="iCal: {import_all_events: bool}")
    room_mappings = ChannelRoomMappingInputSerializer(many=True, required=False)
    rate_mappings = ChannelRateMappingInputSerializer(many=True, required=False)
    mode = serializers.CharField(required=False, help_text="iCal/Channex: real | simulated")
    integration = ChannelIntegrationInputSerializer(required=False)
    full_sync = serializers.BooleanField(required=False, default=False, help_text="Sincronizar 365 días ya")

    def validate(self, attrs):
        prop = self.context["property"]
        connection = self.context.get("connection")
        channel = connection.channel_code if connection is not None else attrs.get("channel_code")
        errors = {}
        if connection is None and channel not in CHANNEL_CODES:
            errors["channel_code"] = [f"Canal desconocido; usa uno de: {', '.join(CHANNEL_CODES)}"]
            raise serializers.ValidationError(errors)
        if "room_mappings" in attrs:
            attrs["room_mappings"] = self._rooms(prop, channel, connection, attrs["room_mappings"], errors)
        if "rate_mappings" in attrs:
            attrs["rate_mappings"] = self._rates(prop, channel, connection, attrs["rate_mappings"], errors)
        if "settings" in attrs:
            attrs["settings"] = self._settings(channel, attrs["settings"], errors)
        self._integration(channel, attrs, errors)
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    @staticmethod
    def _rooms(prop, channel, connection, items, errors) -> list[dict]:
        room_types = RoomType.objects.in_bulk([item["room_type"] for item in items])
        room_ids = [item["room"] for item in items if item.get("room")]
        rooms = Room.objects.in_bulk(room_ids)
        known = set(connection.room_mappings.values_list("pk", flat=True)) if connection else set()
        problems, external_ids, units = [], set(), set()
        for index, item in enumerate(items, start=1):
            room_type = room_types.get(item["room_type"])
            if room_type is None or room_type.property_id != prop.pk:
                problems.append(f"Fila {index}: la categoría no existe en este hotel")
                continue
            if item.get("id") and item["id"] not in known:
                problems.append(f"Fila {index}: el mapeo no pertenece a esta conexión")
            if item.get("room"):
                room = rooms.get(item["room"])
                if channel != ICAL:
                    problems.append(
                        f"Fila {index}: solo los calendarios iCal mapean habitaciones individuales"
                    )
                elif room is None or room.room_type_id != room_type.pk:
                    problems.append(f"Fila {index}: la habitación no es de la categoría {room_type.code}")
            unit = (room_type.pk, item.get("room"))
            if unit in units:
                problems.append(f"Fila {index}: la categoría {room_type.code} ya está mapeada")
            units.add(unit)
            external = (item.get("external_room_id") or "").strip()
            item["external_room_id"] = external
            if channel != ICAL and not external:
                problems.append(f"Fila {index}: falta el código de la habitación en el canal")
            if external:
                if external in external_ids:
                    problems.append(f"Fila {index}: el código «{external}» está repetido")
                external_ids.add(external)
            url = (item.get("ical_import_url") or "").strip()
            if url and channel != ICAL:
                problems.append(f"Fila {index}: solo las conexiones iCal importan calendarios")
            elif url:
                url = normalize_calendar_url(url)
                item["ical_import_url"] = url
                from apps.distribution.services.ical import local_export_mapping

                if local_export_mapping(url) is None:
                    try:
                        check_public_url(url)
                    except ChannelError as exc:
                        problems.append(f"Fila {index}: {exc.message}")
            else:
                item["ical_import_url"] = ""
        if problems:
            errors["room_mappings"] = problems
        return items

    @staticmethod
    def _rates(prop, channel, connection, items, errors) -> list[dict]:
        if items and channel == ICAL:
            errors["rate_mappings"] = ["Los calendarios iCal no llevan tarifas"]
            return items
        plans = RatePlan.objects.in_bulk([item["rate_plan"] for item in items])
        room_types = RoomType.objects.in_bulk([item["room_type"] for item in items if item.get("room_type")])
        known = set(connection.rate_mappings.values_list("pk", flat=True)) if connection else set()
        problems, external_ids, pairs = [], set(), set()
        for index, item in enumerate(items, start=1):
            plan = plans.get(item["rate_plan"])
            if plan is None or plan.property_id != prop.pk:
                problems.append(f"Fila {index}: el plan tarifario no existe en este hotel")
                continue
            if item.get("id") and item["id"] not in known:
                problems.append(f"Fila {index}: el mapeo no pertenece a esta conexión")
            if item.get("room_type"):
                room_type = room_types.get(item["room_type"])
                if room_type is None or room_type.property_id != prop.pk:
                    problems.append(f"Fila {index}: la categoría no existe en este hotel")
            pair = (plan.pk, item.get("room_type"))
            if pair in pairs:
                problems.append(f"Fila {index}: el plan {plan.code} ya está mapeado")
            pairs.add(pair)
            external = (item.get("external_rate_id") or "").strip()
            item["external_rate_id"] = external
            if not external:
                problems.append(f"Fila {index}: falta el código de la tarifa en el canal")
            elif external in external_ids:
                problems.append(f"Fila {index}: el código «{external}» está repetido")
            external_ids.add(external)
            markup = item.get("markup_percent") or Decimal("0")
            if not MARKUP_MIN <= markup <= MARKUP_MAX:
                problems.append(f"Fila {index}: el recargo debe estar entre {MARKUP_MIN} % y {MARKUP_MAX} %")
        if problems:
            errors["rate_mappings"] = problems
        return items

    @staticmethod
    def _settings(channel, settings, errors) -> dict:
        clean = {}
        for key, value in (settings or {}).items():
            expected = SETTINGS_SCHEMA.get(key)
            if expected is None or channel != ICAL:
                errors.setdefault("settings", []).append(f"Ajuste desconocido: {key}")
            elif not isinstance(value, expected):
                errors.setdefault("settings", []).append(f"{key} debe ser verdadero o falso")
            else:
                clean[key] = value
        return clean

    @staticmethod
    def _integration(channel, attrs, errors) -> None:
        kind = CHANNEL_KINDS.get(channel)
        integration = attrs.get("integration") or {}
        if not kind:
            if attrs.get("mode") or integration.get("config") or integration.get("secrets"):
                errors["mode"] = [f"{channel_label(channel)} siempre es simulado"]
            return
        if attrs.get("mode") and attrs["mode"] not in MODES:
            errors["mode"] = ["Modo inválido: real o simulated"]
        if attrs.get("mode") and attrs["mode"] not in integrations.providers_for(kind):
            errors["mode"] = ["No hay proveedor para ese modo"]
        fields = {field["name"]: field for field in config_fields(kind)}
        problems = []
        for key, value in (integration.get("config") or {}).items():
            field = fields.get(key)
            if field is None or field.get("secret"):
                problems.append(f"Campo desconocido: {key}")
            elif field.get("options") and value not in [option["value"] for option in field["options"]]:
                problems.append(f"Valor inválido para {key}")
        for key in integration.get("secrets") or {}:
            if not fields.get(key, {}).get("secret"):
                problems.append(f"Secreto desconocido: {key}")
        if problems:
            errors["integration"] = problems


# --- log, queue, options ------------------------------------------------------------------------------------


class ChannelConnectionRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    channel_code = serializers.CharField()


class SyncLogSerializer(serializers.ModelSerializer):
    connection = ChannelConnectionRefSerializer()
    direction = serializers.CharField(help_text="in | out")
    status = serializers.CharField(help_text="success | warning | error | skipped")
    reservation = serializers.SerializerMethodField()

    class Meta:
        model = SyncLog
        fields = [
            "id",
            "connection",
            "direction",
            "kind",
            "status",
            "message",
            "payload",
            "external_id",
            "reservation",
            "created_at",
        ]

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_reservation(self, log):
        if log.reservation_id is None:
            return None
        return {"id": str(log.reservation_id), "code": log.reservation.code, "status": log.reservation.status}


class AriUpdateSerializer(serializers.ModelSerializer):
    connection = ChannelConnectionRefSerializer()
    room_type = serializers.SerializerMethodField()
    status = serializers.CharField(help_text="pending | sending | sent | failed")

    class Meta:
        model = AriUpdate
        fields = [
            "id",
            "connection",
            "room_type",
            "start",
            "end",
            "kinds",
            "status",
            "attempts",
            "next_attempt_at",
            "last_error",
            "sent_at",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field(serializers.DictField())
    def get_room_type(self, update):
        room_type = update.room_type
        return {"id": str(room_type.pk), "code": room_type.code, "name": room_type.name}


class AriQueueRetrySerializer(serializers.Serializer):
    connection = serializers.UUIDField(required=False, allow_null=True)


class ChannelTestResultSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    message = serializers.CharField()


# --- simulator ----------------------------------------------------------------------------------------------


class OtaSimGuestSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=32)
    country = serializers.CharField(required=False, allow_blank=True, max_length=2)
    language = serializers.CharField(required=False, allow_blank=True, max_length=2)


class OtaSimBookingCreateSerializer(serializers.Serializer):
    external_room_id = serializers.CharField(max_length=120)
    external_rate_id = serializers.CharField(max_length=120)
    checkin = serializers.DateField()
    checkout = serializers.DateField()
    adults = serializers.IntegerField(min_value=1, max_value=20)
    children = serializers.IntegerField(min_value=0, max_value=20, required=False, default=0)
    guest = OtaSimGuestSerializer(required=False)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")
    force = serializers.BooleanField(required=False, default=False)


class OtaSimBookingModifySerializer(serializers.Serializer):
    external_room_id = serializers.CharField(max_length=120, required=False)
    external_rate_id = serializers.CharField(max_length=120, required=False)
    checkin = serializers.DateField(required=False)
    checkout = serializers.DateField(required=False)
    adults = serializers.IntegerField(min_value=1, max_value=20, required=False)
    children = serializers.IntegerField(min_value=0, max_value=20, required=False)
    force = serializers.BooleanField(required=False, default=False)


class OtaSimBookingSerializer(serializers.ModelSerializer):
    status = serializers.CharField(help_text="new | modified | cancelled")
    pms_status = serializers.CharField(help_text="pending | imported | failed")
    reservation = serializers.SerializerMethodField()

    class Meta:
        model = SimOtaBooking
        fields = [
            "id",
            "external_id",
            "status",
            "revision",
            "pms_status",
            "pms_message",
            "payload",
            "reservation",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_reservation(self, booking):
        reservations = self.context.get("reservations")
        if reservations is None:
            from apps.distribution.models import ExternalReservationMap

            item = (
                ExternalReservationMap.objects.filter(
                    connection_id=booking.connection_id, external_id=booking.external_id
                )
                .select_related("reservation")
                .first()
            )
            reservation = item.reservation if item else None
        else:
            reservation = reservations.get(booking.external_id)
        if reservation is None:
            return None
        return {"id": str(reservation.pk), "code": reservation.code, "status": reservation.status}
