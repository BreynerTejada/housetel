"""Inventory serializers. Validation lives here and is shared by the API and by the services that take plain
data (`provision_room_type`, bulk operations), so both paths accept and reject exactly the same input.

Every serializer needs `context["property"]` (the API view passes `request.property`).
"""

import re
import unicodedata

from django.db.models import Max, Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.errors import DomainError
from apps.core.models import Property
from apps.inventory.custom_fields import clean_custom_values, custom_field_definitions, validate_custom_values
from apps.inventory.models import (
    ROOM_OVERRIDABLE_FIELDS,
    Amenity,
    Bed,
    CustomFieldDefinition,
    Photo,
    Room,
    RoomBlock,
    RoomType,
)

LANGUAGES = ("es", "en")
# Bed configuration of a category (`RoomType.beds`, `[{"type", "count"}]`); dorm sellable beds are `Bed` rows.
BED_CONFIG_TYPES = ["single", "twin", "double", "queen", "king", "bunk", "sofa_bed", "crib"]
CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,19}$")
HEX_COLOR = r"^#[0-9A-Fa-f]{6}$"
_STOPWORDS = {
    "DE",
    "DEL",
    "LA",
    "LAS",
    "EL",
    "LOS",
    "AL",
    "Y",
    "CON",
    "EN",
    "PARA",
    "OF",
    "THE",
    "WITH",
    "AND",
    "A",
}
PRIVATE_DEFAULTS = {"base_occupancy": 2, "max_adults": 2, "max_children": 0}
DORM_OCCUPANCY = {"base_occupancy": 1, "max_adults": 1, "max_children": 0, "max_occupancy": 1}


def plain_errors(errors):
    """serializer.errors (ErrorDetail) → plain str/list/dict, ready for DomainError(fields=...)."""
    if isinstance(errors, dict):
        return {str(key): plain_errors(value) for key, value in errors.items()}
    if isinstance(errors, list | tuple):
        return [plain_errors(value) for value in errors]
    return str(errors)


def validated(serializer_class, *, data, context, instance=None, partial=False, message=None):
    """Run a serializer on plain data; invalid → DomainError(code="validation_error", fields=...)."""
    serializer = serializer_class(instance, data=data, context=context, partial=partial)
    if not serializer.is_valid():
        raise DomainError(
            message or "Hay datos inválidos", code="validation_error", fields=plain_errors(serializer.errors)
        )
    return serializer


def _organization(context):
    return context["property"].organization


# ---- Fields --------------------------------------------------------------------------------------------


I18N_SCHEMA = {
    "type": "object",
    "properties": {"es": {"type": "string"}, "en": {"type": "string"}},
    "example": {"es": "Suite vista al mar", "en": "Sea view suite"},
}


@extend_schema_field(I18N_SCHEMA)
class I18nTextField(serializers.Field):
    """Translatable text `{"es": ..., "en": ...}`; a plain string is taken as Spanish. Empty languages are
    dropped and other language keys ignored. `required_text=True` demands at least one language."""

    default_error_messages = {
        "invalid": "Debe ser un texto o un objeto {{es, en}}",
        "empty": "Escribe el texto en español o en inglés",
        "max_length": "Máximo {max_length} caracteres",
    }

    def __init__(self, *, max_length=200, required_text=False, **kwargs):
        self.max_length = max_length
        self.required_text = required_text
        super().__init__(**kwargs)

    def validate_empty_values(self, data):
        if data is None and self.required_text:
            self.fail("empty")
        return super().validate_empty_values(data)

    def to_internal_value(self, data):
        if data is None:
            data = {}
        if isinstance(data, str):
            data = {"es": data}
        if not isinstance(data, dict):
            self.fail("invalid")
        cleaned = {}
        for language in LANGUAGES:
            value = data.get(language)
            if value is None:
                continue
            if not isinstance(value, str):
                self.fail("invalid")
            value = value.strip()
            if len(value) > self.max_length:
                self.fail("max_length", max_length=self.max_length)
            if value:
                cleaned[language] = value
        if self.required_text and not cleaned:
            self.fail("empty")
        return cleaned

    def to_representation(self, value):
        return dict(value or {})


@extend_schema_field(
    {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": BED_CONFIG_TYPES},
                "count": {"type": "integer"},
            },
        },
    }
)
class BedsField(serializers.Field):
    """`[{"type": "queen", "count": 1}]` with types from BED_CONFIG_TYPES and counts 1–20."""

    default_error_messages = {
        "invalid": 'Debe ser una lista [{{"type", "count"}}]',
        "type": "Tipo de cama inválido: {value}",
        "count": "La cantidad de camas debe estar entre 1 y 20",
        "too_many": "Máximo 10 tipos de cama",
    }

    def to_internal_value(self, data):
        if data in (None, ""):
            return []
        if not isinstance(data, list):
            self.fail("invalid")
        if len(data) > 10:
            self.fail("too_many")
        beds = []
        for item in data:
            if not isinstance(item, dict):
                self.fail("invalid")
            bed_type = item.get("type")
            if isinstance(bed_type, str):
                bed_type = bed_type.strip().lower()
            if bed_type not in BED_CONFIG_TYPES:
                self.fail("type", value=bed_type)
            count = item.get("count", 1)
            if isinstance(count, str) and count.strip().isdigit():
                count = int(count)
            if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 20:
                self.fail("count")
            beds.append({"type": bed_type, "count": count})
        return beds

    def to_representation(self, value):
        return list(value or [])


class RoundedDecimalField(serializers.DecimalField):
    """DecimalField that rounds extra decimals (ROUND_HALF_UP) instead of rejecting them: 24.335 → 24.34."""

    def validate_precision(self, value):
        from decimal import ROUND_HALF_UP, Decimal

        if self.decimal_places is not None:
            value = value.quantize(Decimal(1).scaleb(-self.decimal_places), rounding=ROUND_HALF_UP)
        return super().validate_precision(value)


@extend_schema_field({"type": "array", "items": {"type": "string"}, "example": ["wifi", "air_conditioning"]})
class AmenityCodesField(serializers.Field):
    """Amenities by code (global catalog + the organization's own). Reads a related manager, writes a list of
    `Amenity` instances."""

    default_error_messages = {
        "invalid": "Debe ser una lista de códigos",
        "unknown": "Amenidades desconocidas: {codes}",
    }

    def to_representation(self, value):
        return sorted(amenity.code for amenity in value.all())

    def to_internal_value(self, data):
        if data is None:
            data = []
        if not isinstance(data, list) or any(not isinstance(code, str) for code in data):
            self.fail("invalid")
        codes = list(dict.fromkeys(code.strip() for code in data if code.strip()))
        return resolve_amenities(_organization(self.context), codes, field=self)


def amenity_catalog(organization):
    """Amenities an organization can use: the global catalog plus its own (its own win on equal codes)."""
    return Amenity.objects.filter(Q(organization__isnull=True) | Q(organization=organization))


def resolve_amenities(organization, codes: list[str], *, field=None) -> list[Amenity]:
    found: dict[str, Amenity] = {}
    for amenity in amenity_catalog(organization).filter(code__in=codes).order_by("organization_id"):
        if amenity.code not in found or amenity.organization_id is not None:
            found[amenity.code] = amenity
    missing = [code for code in codes if code not in found]
    if missing:
        if field is not None:
            field.fail("unknown", codes=", ".join(missing))
        raise serializers.ValidationError(f"Amenidades desconocidas: {', '.join(missing)}")
    return [found[code] for code in codes]


# ---- Codes ---------------------------------------------------------------------------------------------


def _ascii_upper(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char)).upper()


def code_from_name(name: dict) -> str:
    """ "Suite Vista al Mar" → "SVM", "Estándar" → "EST", "Dorm 6 camas" → "D6C" (initials, whole numbers)."""
    text = _ascii_upper(name.get("es") or name.get("en") or "")
    words = [word for word in re.findall(r"[A-Z0-9]+", text) if word not in _STOPWORDS]
    if not words:
        return "RT"
    if len(words) == 1:
        return words[0][:3]
    return "".join(word if word.isdigit() else word[0] for word in words)[:20]


def sanitize_code(value) -> str:
    """Code-looking text → a valid category code: ASCII, upper case, any run of other characters → "-",
    trimmed and cut to 20 characters ("Suite Vista" → "SUITE-VISTA", 305 → "305"). "" when nothing usable
    is left."""
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return ""
    code = re.sub(r"[^A-Z0-9_-]+", "-", _ascii_upper(value.strip()))
    return code.strip("-_")[:20].rstrip("-_")


def unique_room_type_code(property, base: str, *, exclude_pk=None) -> str:
    taken = set(
        RoomType.objects.filter(property=property).exclude(pk=exclude_pk).values_list("code", flat=True)
    )
    if base not in taken:
        return base
    for suffix in range(2, 1000):
        candidate = f"{base[: 20 - len(str(suffix))]}{suffix}"
        if candidate not in taken:
            return candidate
    raise DomainError("No se pudo generar un código único", code="validation_error")


# ---- Room types ----------------------------------------------------------------------------------------

OCCUPANCY_FIELDS = ("base_occupancy", "max_adults", "max_children", "max_occupancy")


def occupancy_errors(values: dict) -> dict:
    """Occupancy consistency (category or effective room): base ≤ max, adults ≤ max, children ≤ max − 1."""
    errors = {}
    maximum = values["max_occupancy"]
    if values["base_occupancy"] > maximum:
        errors["base_occupancy"] = [f"No puede superar la ocupación máxima ({maximum})"]
    if values["max_adults"] > maximum:
        errors["max_adults"] = [f"No puede superar la ocupación máxima ({maximum})"]
    if values["max_children"] > maximum - 1:
        errors["max_children"] = ["Debe quedar cupo para al menos un adulto"]
    return errors


class RoomTypeSerializer(serializers.ModelSerializer):
    """Category with every spec §4 parameter. Rules:

    - `code`: A–Z, 0–9, `_`, `-` (≤ 20), upper-cased, unique in the property; derived from the name on create
      when missing.
    - Occupancy (private): base ≤ max, adults ≤ max, children ≤ max − 1. On create, missing values are
      filled (children 0, adults = base or 2, max = adults + children, base = min(2, adults)).
    - Dorm: units are beds for one person, so occupancy is always 1/1/0/1.
    - `kind` cannot change while the category has rooms.
    - `custom_values` validated with the organization's `room_type` definitions (on create even if absent).
    """

    code = serializers.CharField(max_length=40, required=False, allow_blank=True)
    name = I18nTextField(max_length=100, required_text=True)
    description = I18nTextField(max_length=2000, required=False)
    beds = BedsField(required=False)
    amenities = AmenityCodesField(required=False)
    color = serializers.RegexField(
        HEX_COLOR, required=False, error_messages={"invalid": "Color inválido (#RRGGBB)"}
    )
    base_occupancy = serializers.IntegerField(min_value=1, max_value=20, required=False)
    max_adults = serializers.IntegerField(min_value=1, max_value=20, required=False)
    max_children = serializers.IntegerField(min_value=0, max_value=20, required=False)
    max_occupancy = serializers.IntegerField(min_value=1, max_value=20, required=False)
    housekeeping_minutes = serializers.IntegerField(min_value=5, max_value=480, required=False)
    size_m2 = RoundedDecimalField(
        max_digits=6, decimal_places=2, min_value=1, allow_null=True, required=False
    )
    custom_values = serializers.JSONField(required=False)
    rooms_count = serializers.SerializerMethodField()
    active_rooms_count = serializers.SerializerMethodField()
    beds_count = serializers.SerializerMethodField()
    units_count = serializers.SerializerMethodField()
    photos_count = serializers.SerializerMethodField()
    cover_photo = serializers.SerializerMethodField()

    class Meta:
        model = RoomType
        fields = [
            "id",
            "code",
            "name",
            "description",
            "kind",
            "base_occupancy",
            "max_adults",
            "max_children",
            "max_occupancy",
            "beds",
            "size_m2",
            "view",
            "smoking_allowed",
            "accessible",
            "amenities",
            "color",
            "housekeeping_minutes",
            "sort_order",
            "is_active",
            "custom_values",
            "rooms_count",
            "active_rooms_count",
            "beds_count",
            "units_count",
            "photos_count",
            "cover_photo",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    # Counts come annotated by RoomTypeViewSet.get_queryset(); the fallbacks keep other callers working.
    def get_rooms_count(self, obj) -> int:
        value = getattr(obj, "rooms_count", None)
        return obj.rooms.count() if value is None else value

    def get_active_rooms_count(self, obj) -> int:
        value = getattr(obj, "active_rooms_count", None)
        return obj.rooms.filter(is_active=True).count() if value is None else value

    def get_beds_count(self, obj) -> int:
        value = getattr(obj, "beds_count", None)
        if value is None:
            value = Bed.objects.filter(room__room_type=obj, room__is_active=True, is_active=True).count()
        return value

    def get_units_count(self, obj) -> int:
        return (
            self.get_beds_count(obj) if obj.kind == RoomType.Kind.DORM else self.get_active_rooms_count(obj)
        )

    def get_photos_count(self, obj) -> int:
        return len(obj.photos.all())

    def get_cover_photo(self, obj) -> str | None:
        photos = sorted(obj.photos.all(), key=lambda photo: (photo.sort_order, photo.created_at))
        return photos[0].image.url if photos else None

    def validate_code(self, value):
        return value.strip().upper()

    def validate_custom_values(self, value):
        return self._clean_custom_values(value)

    def _clean_custom_values(self, value):
        prop = self.context["property"]
        defs = custom_field_definitions(organization=prop.organization, applies_to="room_type", property=prop)
        try:
            return validate_custom_values(defs, value)
        except DomainError as exc:
            raise serializers.ValidationError(exc.extra.get("fields") or exc.message) from None

    def validate(self, attrs):
        prop = self.context["property"]
        instance = self.instance
        errors: dict[str, list[str]] = {}

        code = attrs.get("code")
        if code is None and instance is None or code == "":
            if instance is not None:
                errors["code"] = ["Este campo es obligatorio"]
            else:
                attrs["code"] = unique_room_type_code(prop, code_from_name(attrs.get("name") or {}))
        elif code is not None:
            if not CODE_PATTERN.match(code):
                errors["code"] = ["Usa solo letras A–Z, números, guion y guion bajo (máximo 20)"]
            elif (
                RoomType.objects.filter(property=prop, code=code)
                .exclude(pk=getattr(instance, "pk", None))
                .exists()
            ):
                errors["code"] = ["Ya existe una categoría con este código"]

        kind = attrs.get("kind", getattr(instance, "kind", RoomType.Kind.PRIVATE))
        if instance is not None and kind != instance.kind and instance.rooms.exists():
            errors["kind"] = ["No puedes cambiar el tipo de una categoría que ya tiene habitaciones"]

        if kind == RoomType.Kind.DORM:
            attrs.update(DORM_OCCUPANCY)
        else:
            errors.update(self._occupancy_errors(attrs, instance))
            if not errors and instance is not None:
                errors.update(self._room_override_errors(attrs, instance, kind))

        if instance is None:
            if "custom_values" not in attrs:
                try:
                    attrs["custom_values"] = self._clean_custom_values({})
                except serializers.ValidationError as exc:
                    errors["custom_values"] = exc.detail
            if "sort_order" not in attrs:
                current = RoomType.objects.filter(property=prop).aggregate(top=Max("sort_order"))["top"]
                attrs["sort_order"] = 10 if current is None else current + 10

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    @staticmethod
    def _room_override_errors(attrs, instance, kind) -> dict:
        """A new category occupancy must still hold for the rooms that override part of it (their effective
        occupancy mixes both); otherwise name those rooms on the changed field."""
        changed = [
            field for field in OCCUPANCY_FIELDS if field in attrs and attrs[field] != getattr(instance, field)
        ]
        if not changed:
            return {}
        from types import SimpleNamespace

        proposed = SimpleNamespace(
            kind=kind, **{field: attrs.get(field, getattr(instance, field)) for field in OCCUPANCY_FIELDS}
        )
        broken = sorted(
            (
                room.number
                for room in instance.rooms.all()
                if set(OCCUPANCY_FIELDS) & set(room.overrides or {})
                and room_occupancy_errors(proposed, room.overrides or {})
            ),
            key=lambda number: (len(number), number),
        )
        if not broken:
            return {}
        field = "max_occupancy" if "max_occupancy" in changed else changed[0]
        numbers = ", ".join(broken)
        if len(broken) == 1:
            message = (
                f"La habitación {numbers} sobrescribe la ocupación y quedaría inválida: ajústala primero"
            )
        else:
            message = (
                f"Las habitaciones {numbers} sobrescriben la ocupación y quedarían inválidas: "
                "ajústalas primero"
            )
        return {field: [message]}

    @staticmethod
    def _occupancy_errors(attrs, instance) -> dict:
        def current(field):
            if field in attrs:
                return attrs[field]
            return getattr(instance, field) if instance is not None else None

        values = {
            field: current(field)
            for field in ("base_occupancy", "max_adults", "max_children", "max_occupancy")
        }
        if instance is None:  # fill what the caller left out, from what they gave
            if values["max_children"] is None:
                values["max_children"] = PRIVATE_DEFAULTS["max_children"]
            if values["max_adults"] is None:
                if values["base_occupancy"] is not None:
                    values["max_adults"] = values["base_occupancy"]
                elif values["max_occupancy"] is not None:
                    values["max_adults"] = max(1, values["max_occupancy"] - values["max_children"])
                else:
                    values["max_adults"] = PRIVATE_DEFAULTS["max_adults"]
            if values["max_occupancy"] is None:
                values["max_occupancy"] = max(
                    values["max_adults"] + values["max_children"], values["base_occupancy"] or 1
                )
            if values["base_occupancy"] is None:
                values["base_occupancy"] = min(PRIVATE_DEFAULTS["base_occupancy"], values["max_adults"])
            attrs.update(values)

        return occupancy_errors(values)

    def create(self, validated_data):
        amenities = validated_data.pop("amenities", None)
        room_type = super().create(validated_data)
        if amenities is not None:
            room_type.amenities.set(amenities)
        return room_type

    def update(self, instance, validated_data):
        amenities = validated_data.pop("amenities", None)
        room_type = super().update(instance, validated_data)
        if amenities is not None:
            room_type.amenities.set(amenities)
        return room_type


# ---- Rooms: overrides and custom values ---------------------------------------------------------------


def clean_override(field: str, value, *, context):
    """One `Room.overrides` value, validated with the category field of the same name and stored JSON-safe
    (size_m2 as a string). Raises serializers.ValidationError."""
    if field not in ROOM_OVERRIDABLE_FIELDS:
        raise serializers.ValidationError("Este campo no se puede sobrescribir")
    cleaned = RoomTypeSerializer(context=context).fields[field].run_validation(value)
    if field == "size_m2" and cleaned is not None:
        return format(cleaned, "f")
    return cleaned


def clean_overrides(overrides, *, context) -> dict:
    if overrides is None:
        return {}
    if not isinstance(overrides, dict):
        raise serializers.ValidationError("Debe ser un objeto {campo: valor}")
    errors, cleaned = {}, {}
    for field, value in overrides.items():
        try:
            cleaned[field] = clean_override(field, value, context=context)
        except serializers.ValidationError as exc:
            errors[field] = exc.detail
    if errors:
        raise serializers.ValidationError(errors)
    return cleaned


def effective_occupancy(room_type, overrides: dict) -> dict:
    return {field: overrides.get(field, getattr(room_type, field)) for field in OCCUPANCY_FIELDS}


def room_occupancy_errors(room_type, overrides: dict) -> dict:
    """Errors keyed by override field for an effective occupancy that does not hold; dorm rooms cannot
    override occupancy (a dorm unit is one bed for one person)."""
    if room_type.kind == RoomType.Kind.DORM:
        return {
            field: ["En un dormitorio la ocupación es de una persona por cama"]
            for field in OCCUPANCY_FIELDS
            if field in overrides
        }
    errors = occupancy_errors(effective_occupancy(room_type, overrides))
    # blame an overridden field when the category value is the one that breaks the rule
    return {
        (
            field if field in overrides else next((f for f in OCCUPANCY_FIELDS if f in overrides), field)
        ): messages
        for field, messages in errors.items()
    }


def clean_room_custom_values(property, values, *, partial: bool = False) -> dict:
    """A room's `custom_values`: its own fields (definitions `applies_to="room"`, defaults and required
    applied unless `partial`) plus overrides of its category's fields (`applies_to="room_type"`, only the
    keys given). Raises DomainError(code="invalid_custom_values", fields={key: [...]})."""
    organization = property.organization
    room_defs = custom_field_definitions(organization=organization, applies_to="room", property=property)
    type_defs = custom_field_definitions(organization=organization, applies_to="room_type", property=property)
    values = values if values is not None else {}
    if not isinstance(values, dict):
        raise DomainError(
            "Los campos personalizados deben ser un objeto", code="invalid_custom_values",
            fields={"custom_values": ["Debe ser un objeto {clave: valor}"]},
        )  # fmt: skip
    room_keys = {definition.key for definition in room_defs}
    errors, cleaned = {}, {}
    for defs, part, is_partial in (
        (room_defs, {k: v for k, v in values.items() if k in room_keys}, partial),
        (type_defs, {k: v for k, v in values.items() if k not in room_keys}, True),
    ):
        try:
            cleaned.update(clean_custom_values(defs, part, partial=is_partial))
        except DomainError as exc:
            errors.update(exc.extra.get("fields") or {})
    if errors:
        raise DomainError("Hay campos personalizados inválidos", code="invalid_custom_values", fields=errors)
    return cleaned


def room_custom_defaults(property) -> dict:
    """Default values of the property's room-level custom fields (applied to rooms created in bulk)."""
    defs = custom_field_definitions(organization=property.organization, applies_to="room", property=property)
    return {
        definition.key: definition.default_value
        for definition in defs
        if definition.default_value is not None
    }


@extend_schema_field(OpenApiTypes.UUID)
class PropertyRoomTypeField(serializers.PrimaryKeyRelatedField):
    """A room type of `context["property"]`."""

    def get_queryset(self):
        return RoomType.objects.filter(property=self.context["property"])


class RoomBulkFieldsSerializer(serializers.Serializer):
    """Plain `Room` fields accepted by `rooms/bulk-update/` (`name` is the room's own display name; the
    category name override is `overrides.name`)."""

    floor = serializers.CharField(max_length=20, allow_blank=True, required=False)
    building = serializers.CharField(max_length=50, allow_blank=True, required=False)
    name = serializers.CharField(max_length=100, allow_blank=True, required=False)
    room_type = PropertyRoomTypeField(required=False)
    is_active = serializers.BooleanField(required=False)
    sort_order = serializers.IntegerField(min_value=0, required=False)
    notes = serializers.CharField(allow_blank=True, required=False)
    housekeeping_status = serializers.ChoiceField(choices=Room.HousekeepingStatus.choices, required=False)


# ---- Rooms ---------------------------------------------------------------------------------------------


def jsonable(value):
    """Decimal → "42.00", UUID → str, date → ISO (recursively), for dict payloads like `effective`."""
    from datetime import date as date_type
    from decimal import Decimal
    from uuid import UUID

    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, date_type):
        return value.isoformat()
    return value


@extend_schema_field(OpenApiTypes.UUID)
class PropertyRoomsField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        return Room.objects.filter(property=self.context["property"])


class ActiveBlockSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    bed = serializers.UUIDField(source="bed_id", allow_null=True)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    kind = serializers.CharField()
    reason = serializers.CharField()


class RoomSerializer(serializers.ModelSerializer):
    """A room: its own fields, `overrides` (only ROOM_OVERRIDABLE_FIELDS, validated like the category field),
    amenity changes by code, `custom_values` (own fields + overrides of category fields) and, read-only, the
    resolved `effective` attributes (services.effective_attributes), `overridden_fields` and the current or
    next `active_block`. `housekeeping_status` is read-only here (use `rooms/{id}/status/`)."""

    number = serializers.CharField(max_length=20)
    room_type = PropertyRoomTypeField()
    overrides = serializers.JSONField(required=False)
    extra_amenities = AmenityCodesField(required=False)
    removed_amenities = AmenityCodesField(required=False)
    custom_values = serializers.JSONField(required=False)
    connecting_rooms = PropertyRoomsField(many=True, required=False)
    room_type_code = serializers.CharField(source="room_type.code", read_only=True)
    room_type_name = serializers.JSONField(source="room_type.name", read_only=True)
    kind = serializers.CharField(source="room_type.kind", read_only=True)
    color = serializers.CharField(source="room_type.color", read_only=True)
    beds_count = serializers.SerializerMethodField()
    active_beds_count = serializers.SerializerMethodField()
    effective = serializers.SerializerMethodField()
    overridden_fields = serializers.SerializerMethodField()
    active_block = serializers.SerializerMethodField()

    class Meta:
        model = Room
        fields = [
            "id",
            "number",
            "name",
            "floor",
            "building",
            "room_type",
            "room_type_code",
            "room_type_name",
            "kind",
            "color",
            "overrides",
            "extra_amenities",
            "removed_amenities",
            "custom_values",
            "housekeeping_status",
            "is_active",
            "sort_order",
            "notes",
            "connecting_rooms",
            "beds_count",
            "active_beds_count",
            "effective",
            "overridden_fields",
            "active_block",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "housekeeping_status", "created_at", "updated_at"]

    def _effective(self, obj) -> dict:
        cache = self.context.setdefault("_effective_cache", {})
        if obj.pk not in cache:
            from apps.inventory.services import effective_attributes

            cache[obj.pk] = jsonable(effective_attributes(obj))
        return cache[obj.pk]

    def get_effective(self, obj) -> dict:
        return self._effective(obj)

    def get_overridden_fields(self, obj) -> list[str]:
        return self._effective(obj)["overridden_fields"]

    def get_beds_count(self, obj) -> int:
        value = getattr(obj, "beds_count", None)
        return obj.beds.count() if value is None else value

    def get_active_beds_count(self, obj) -> int:
        value = getattr(obj, "active_beds_count", None)
        return obj.beds.filter(is_active=True).count() if value is None else value

    def get_active_block(self, obj) -> dict | None:
        blocks = getattr(obj, "current_blocks", None)
        if blocks is None:
            business_date = obj.property.business_date
            blocks = list(
                obj.blocks.filter(released_at__isnull=True, end_date__gt=business_date).order_by("start_date")
            )
        return ActiveBlockSerializer(blocks[0]).data if blocks else None

    def validate_number(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Este campo es obligatorio")
        taken = Room.objects.filter(property=self.context["property"], number=value)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError("Ya existe una habitación con este número")
        return value

    def validate_overrides(self, value):
        return clean_overrides(value, context=self.context)

    def validate(self, attrs):
        instance = self.instance
        errors: dict = {}
        room_type = attrs.get("room_type") or getattr(instance, "room_type", None)
        overrides = (
            attrs["overrides"] if "overrides" in attrs else dict(getattr(instance, "overrides", None) or {})
        )
        if room_type is not None:
            occupancy = room_occupancy_errors(room_type, overrides)
            if occupancy:
                errors["overrides"] = occupancy
        extra = {a.code for a in attrs.get("extra_amenities") or []}
        removed = {a.code for a in attrs.get("removed_amenities") or []}
        if extra & removed:
            errors["removed_amenities"] = [
                f"No puede agregar y quitar a la vez: {', '.join(sorted(extra & removed))}"
            ]
        if instance is None or "custom_values" in attrs:
            try:
                attrs["custom_values"] = clean_room_custom_values(
                    self.context["property"], attrs.get("custom_values") or {}
                )
            except DomainError as exc:
                errors["custom_values"] = exc.extra.get("fields") or [exc.message]
        if instance is not None and any(
            room.pk == instance.pk for room in attrs.get("connecting_rooms") or []
        ):
            errors["connecting_rooms"] = ["Una habitación no puede comunicarse consigo misma"]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class RoomBulkCreateSerializer(serializers.Serializer):
    """`POST rooms/bulk-create/` body."""

    room_type = PropertyRoomTypeField()
    numbers = serializers.CharField(help_text='Números o rangos: "101-110,201,203"')
    floor = serializers.CharField(
        max_length=20, required=False, allow_blank=True, allow_null=True, default=None
    )
    building = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    beds_per_room = serializers.IntegerField(
        min_value=0, max_value=50, required=False, allow_null=True, default=None
    )


class RoomBulkCreateResultSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    rooms = RoomSerializer(many=True)


class RoomBulkUpdateSerializer(serializers.Serializer):
    """`POST rooms/bulk-update/` body (values are validated by services.bulk_update_rooms)."""

    ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    set = serializers.DictField(required=False, default=dict)
    reset = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class RoomBulkUpdateResultSerializer(serializers.Serializer):
    updated = serializers.IntegerField()
    rooms = RoomSerializer(many=True)


class ResetOverrideSerializer(serializers.Serializer):
    field = serializers.CharField(help_text="Campo sobrescribible, custom_values.<clave> o amenities")


class RoomStatusSerializer(serializers.Serializer):
    housekeeping_status = serializers.ChoiceField(choices=Room.HousekeepingStatus.choices)


# ---- Beds ----------------------------------------------------------------------------------------------


class BedSerializer(serializers.ModelSerializer):
    label = serializers.CharField(max_length=20)

    class Meta:
        model = Bed
        fields = ["id", "room", "label", "bed_type", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "room", "created_at", "updated_at"]

    def validate_label(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Este campo es obligatorio")
        room = self.context["room"]
        taken = room.beds.filter(label=value)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError("Ya existe una cama con esta etiqueta en la habitación")
        return value


class BedBulkSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=1, max_value=50)
    prefix = serializers.CharField(max_length=10, required=False, allow_blank=True, default="C")
    bed_type = serializers.ChoiceField(
        choices=["single", "bunk_top", "bunk_bottom", "double", "bunk"], required=False, default="single",
        help_text='"bunk" alterna camarote abajo/arriba',
    )  # fmt: skip


# ---- Photos --------------------------------------------------------------------------------------------

MAX_PHOTO_BYTES = 10 * 1024 * 1024
PHOTO_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


class CaptionField(I18nTextField):
    """Caption: `{"es", "en"}`, a JSON string of it (multipart forms) or plain Spanish text."""

    def to_internal_value(self, data):
        if isinstance(data, str) and data.strip().startswith("{"):
            import json

            try:
                data = json.loads(data)
            except ValueError:
                pass
        return super().to_internal_value(data)


class PhotoSerializer(serializers.ModelSerializer):
    """Photos are public (marketplace, booking engine): `url` is the plain media URL."""

    url = serializers.SerializerMethodField()
    caption = CaptionField(max_length=300, required=False)

    class Meta:
        model = Photo
        fields = ["id", "url", "caption", "sort_order", "room_type", "created_at"]
        read_only_fields = ["id", "url", "sort_order", "room_type", "created_at"]

    def get_url(self, obj) -> str:
        return obj.image.url


class PhotoUploadSerializer(serializers.Serializer):
    image = serializers.ImageField()
    caption = CaptionField(max_length=300, required=False)

    def validate_image(self, image):
        if image.size > MAX_PHOTO_BYTES:
            raise serializers.ValidationError("La imagen supera 10 MB")
        pil_image = getattr(image, "image", None)
        if pil_image is None or pil_image.format not in PHOTO_FORMATS:
            raise serializers.ValidationError("Formatos permitidos: JPG, PNG o WEBP")
        return image


class ReorderSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField())


# ---- Custom fields -------------------------------------------------------------------------------------

CUSTOM_KEY_PATTERN = r"^[a-z][a-z0-9_]{0,49}$"
INVENTORY_TARGETS = ("room_type", "room")  # values merged in effective_attributes


class CustomFieldDefinitionSerializer(serializers.ModelSerializer):
    """`scope`: "organization" (every property) or "property" (only the active one). `key`, `applies_to`,
    `field_type` and `scope` cannot change after creation. Options of select fields: strings or
    `{"value", "label": {es, en}}` (normalized to the latter)."""

    key = serializers.RegexField(
        CUSTOM_KEY_PATTERN,
        error_messages={"invalid": "Usa minúsculas, números y guion bajo (empieza con letra)"},
    )
    label = I18nTextField(max_length=100, required_text=True)
    options = serializers.JSONField(required=False)
    default_value = serializers.JSONField(required=False, allow_null=True)
    scope = serializers.ChoiceField(
        choices=["organization", "property"], required=False, default="organization"
    )

    IMMUTABLE = ("key", "applies_to", "field_type", "scope")

    class Meta:
        model = CustomFieldDefinition
        fields = [
            "id",
            "applies_to",
            "key",
            "label",
            "field_type",
            "options",
            "required",
            "default_value",
            "show_in_marketplace",
            "sort_order",
            "scope",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["scope"] = "organization" if instance.property_id is None else "property"
        return data

    def validate_options(self, value):
        if value in (None, ""):
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("Debe ser una lista")
        options, seen = [], set()
        for item in value:
            if isinstance(item, str | int | float) and not isinstance(item, bool):
                option = {"value": item, "label": {"es": str(item)}}
            elif isinstance(item, dict) and isinstance(item.get("value"), str | int | float):
                label = I18nTextField(max_length=100).run_validation(item.get("label") or str(item["value"]))
                option = {"value": item["value"], "label": label or {"es": str(item["value"])}}
            else:
                raise serializers.ValidationError('Cada opción es un texto o {"value", "label"}')
            if option["value"] in ("", None) or option["value"] in seen:
                raise serializers.ValidationError(f"Opción vacía o repetida: {option['value']}")
            seen.add(option["value"])
            options.append(option)
        return options

    def validate(self, attrs):
        instance = self.instance
        errors: dict = {}
        if instance is not None:
            current_scope = "organization" if instance.property_id is None else "property"
            for field in self.IMMUTABLE:
                if field in self.initial_data:
                    current = current_scope if field == "scope" else getattr(instance, field)
                    if attrs.get(field, current) != current:
                        errors[field] = ["No se puede cambiar después de crear el campo"]
                attrs.pop(field, None)

        field_type = attrs.get("field_type", getattr(instance, "field_type", "text"))
        options = attrs.get("options", getattr(instance, "options", None) or [])
        if field_type in ("select", "multiselect"):
            if not options:
                errors["options"] = ["Agrega al menos una opción"]
        elif "options" in attrs:
            attrs["options"] = []

        default = attrs.get("default_value", getattr(instance, "default_value", None))
        if default not in (None, "", []) and "options" not in errors:
            from apps.inventory.custom_fields import clean_custom_value

            probe = CustomFieldDefinition(field_type=field_type, options=options)
            try:
                attrs["default_value"] = clean_custom_value(probe, default)
            except ValueError as exc:
                errors["default_value"] = [str(exc)]
        elif "default_value" in attrs and default in ("", []):
            attrs["default_value"] = None

        if instance is None and "key" in attrs:
            # an organization-wide key clashes with any definition of that key; a property key with the
            # organization-wide one or another definition of the same property. Room and category fields
            # share one namespace: a room inherits its category's values and overrides them by key.
            prop = self.context["property"]
            applies_to = attrs.get("applies_to")
            targets = INVENTORY_TARGETS if applies_to in INVENTORY_TARGETS else (applies_to,)
            same_key = CustomFieldDefinition.objects.filter(
                organization=prop.organization, applies_to__in=targets, key=attrs["key"]
            )
            if attrs.get("scope") != "organization":
                same_key = same_key.filter(Q(property__isnull=True) | Q(property=prop))
            clash = same_key.first()
            if clash is not None and clash.applies_to == applies_to:
                errors["key"] = ["Ya existe un campo con esta clave"]
            elif clash is not None:
                errors["key"] = [
                    "Ya existe un campo de categoría o de habitación con esta clave "
                    "(la habitación hereda los campos de su categoría)"
                ]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


# ---- Blocks --------------------------------------------------------------------------------------------


class RoomBlockSerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source="room.number", read_only=True)
    room_type = serializers.UUIDField(source="room.room_type_id", read_only=True)
    bed_label = serializers.CharField(source="bed.label", read_only=True, default=None)
    created_by_name = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = RoomBlock
        fields = [
            "id",
            "room",
            "room_number",
            "room_type",
            "bed",
            "bed_label",
            "start_date",
            "end_date",
            "kind",
            "reason",
            "created_by_name",
            "released_at",
            "is_active",
            "created_at",
        ]
        read_only_fields = fields

    def get_created_by_name(self, obj) -> str:
        user = obj.created_by
        return (user.full_name or user.email) if user is not None else ""


class RoomBlockCreateSerializer(serializers.Serializer):
    room = PropertyRoomsField()
    bed = serializers.UUIDField(required=False, allow_null=True)
    start_date = serializers.DateField()
    end_date = serializers.DateField(help_text="Exclusiva (el bloqueo cubre [start_date, end_date))")
    kind = serializers.ChoiceField(choices=RoomBlock.Kind.choices)
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)
    force = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        errors = {}
        if attrs["end_date"] <= attrs["start_date"]:
            errors["end_date"] = ["Debe ser posterior a la fecha inicial"]
        bed_id = attrs.pop("bed", None)
        attrs["bed"] = None
        if bed_id is not None:
            bed = attrs["room"].beds.filter(pk=bed_id).first()
            if bed is None:
                errors["bed"] = ["La cama no pertenece a esta habitación"]
            attrs["bed"] = bed
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


# ---- Amenities -----------------------------------------------------------------------------------------


class AmenitySerializer(serializers.ModelSerializer):
    code = serializers.CharField(max_length=50)
    name = I18nTextField(max_length=100, required_text=True)
    icon = serializers.CharField(max_length=50, required=False, allow_blank=True, default="sparkles")
    is_global = serializers.SerializerMethodField()

    class Meta:
        model = Amenity
        fields = ["id", "code", "name", "icon", "category", "is_global"]
        read_only_fields = ["id", "is_global"]

    def get_is_global(self, obj) -> bool:
        return obj.organization_id is None

    def validate_code(self, value):
        code = re.sub(r"[^a-z0-9]+", "-", _ascii_upper(value).lower()).strip("-")
        if not code:
            raise serializers.ValidationError("Código inválido")
        taken = amenity_catalog(_organization(self.context)).filter(code=code)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError("Ya existe una amenidad con este código")
        return code


# ---- Property profile ----------------------------------------------------------------------------------

LANGUAGE_CODE_PATTERN = re.compile(r"^[a-z]{2}$")
DEFAULT_POLICIES = {
    "pets_allowed": False,
    "smoking_allowed": False,
    "children_allowed": True,
    "events_allowed": False,
    "min_checkin_age": 18,
}
PROFILE_RECOMMENDED = ["legal_name", "nit", "rnt_number", "phone", "email", "address", "city", "description"]


class BrandingSerializer(serializers.Serializer):
    primary_color = serializers.RegexField(
        HEX_COLOR, required=False, allow_blank=True, error_messages={"invalid": "Color inválido (#RRGGBB)"}
    )
    logo = serializers.CharField(read_only=True)


class PoliciesSerializer(serializers.Serializer):
    pets_allowed = serializers.BooleanField(required=False)
    smoking_allowed = serializers.BooleanField(required=False)
    children_allowed = serializers.BooleanField(required=False)
    events_allowed = serializers.BooleanField(required=False)
    min_checkin_age = serializers.IntegerField(min_value=0, max_value=99, required=False, allow_null=True)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = sorted(set(data) - set(self.fields))
            if unknown:
                raise serializers.ValidationError({key: ["Política desconocida"] for key in unknown})
        return super().to_internal_value(data)


class PropertyProfileSerializer(serializers.ModelSerializer):
    """Profile of the active property. Settings-backed extras: `languages` (codes the staff speaks),
    `policies` (merged into DEFAULT_POLICIES), `amenities` (property-level amenity codes). `branding.logo` is
    set by `property/logo/`."""

    name = serializers.CharField(max_length=200)
    description = I18nTextField(max_length=4000, required=False)
    house_rules = I18nTextField(max_length=4000, required=False)
    check_in_time = serializers.TimeField(format="%H:%M", required=False)
    check_out_time = serializers.TimeField(format="%H:%M", required=False)
    default_language = serializers.ChoiceField(choices=["es", "en"], required=False)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90,
                                        required=False, allow_null=True)  # fmt: skip
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-180, max_value=180,
                                         required=False, allow_null=True)  # fmt: skip
    star_rating = serializers.IntegerField(min_value=1, max_value=5, required=False, allow_null=True)
    phone = serializers.RegexField(r"^[+\d][\d\s().-]{6,31}$", required=False, allow_blank=True,
                                   error_messages={"invalid": "Teléfono inválido"})  # fmt: skip
    nit = serializers.CharField(max_length=30, required=False, allow_blank=True)
    branding = BrandingSerializer(required=False)
    languages = serializers.ListField(
        child=serializers.CharField(max_length=2), required=False, max_length=12
    )
    policies = PoliciesSerializer(required=False)
    amenities = serializers.ListField(child=serializers.CharField(max_length=50), required=False)

    class Meta:
        model = Property
        fields = [
            "id",
            "name",
            "slug",
            "property_type",
            "status",
            "timezone",
            "currency",
            "business_date",
            "marketplace_listed",
            "description",
            "address",
            "city",
            "department",
            "country",
            "latitude",
            "longitude",
            "phone",
            "email",
            "website",
            "rnt_number",
            "nit",
            "legal_name",
            "star_rating",
            "check_in_time",
            "check_out_time",
            "default_language",
            "languages",
            "house_rules",
            "policies",
            "amenities",
            "branding",
        ]
        read_only_fields = [
            "id", "slug", "property_type", "status", "timezone", "currency", "business_date",
            "marketplace_listed", "country",
        ]  # fmt: skip

    def to_representation(self, instance):
        data = super().to_representation(instance)
        settings = instance.settings or {}
        data["languages"] = list(settings.get("languages") or [instance.default_language])
        data["policies"] = {**DEFAULT_POLICIES, **(settings.get("policies") or {})}
        data["amenities"] = list(settings.get("amenities") or [])
        data["branding"] = {"primary_color": "", "logo": "", **(instance.branding or {})}
        return data

    def validate_nit(self, value):
        value = re.sub(r"[.\s]", "", value)
        if value and not re.fullmatch(r"\d{6,12}(-\d)?", value):
            raise serializers.ValidationError("NIT inválido (ej. 900123456-7)")
        return value

    def validate_languages(self, value):
        codes = list(dict.fromkeys(code.strip().lower() for code in value))
        if any(not LANGUAGE_CODE_PATTERN.match(code) for code in codes):
            raise serializers.ValidationError("Usa códigos de idioma de dos letras (es, en, fr…)")
        return codes

    def validate_amenities(self, value):
        codes = list(dict.fromkeys(code.strip() for code in value if code.strip()))
        resolve_amenities(self.instance.organization, codes)
        return codes

    def update(self, instance, validated_data):
        settings = dict(instance.settings or {})
        if "languages" in validated_data:
            settings["languages"] = validated_data.pop("languages")
        if "policies" in validated_data:
            settings["policies"] = {**(settings.get("policies") or {}), **validated_data.pop("policies")}
        if "amenities" in validated_data:
            settings["amenities"] = validated_data.pop("amenities")
        if "branding" in validated_data:
            instance.branding = {**(instance.branding or {}), **validated_data.pop("branding")}
        instance.settings = settings
        return super().update(instance, validated_data)
