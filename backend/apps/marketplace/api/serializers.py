"""Validation of the public marketplace requests (query strings and bodies) and of the staff settings.

Choice-like fields that exist in other apps with other options (language, document type, property type)
are plain strings validated here, so the OpenAPI schema never gets colliding enum names.
"""

import re

from django.utils import timezone
from rest_framework import serializers

from apps.core.models import Property
from apps.guests.models import Guest
from apps.marketplace.services.engine import CHANNELS, MAX_ONLINE_NIGHTS
from apps.marketplace.services.search import SORTS

LANGUAGES = ("es", "en")
PAYMENT_OPTIONS = ("pay_now", "pay_at_hotel")
MAX_ITEMS = 10
MAX_UNITS = 10
LIST_PARAMS = ("children_ages", "type", "stars", "amenities")


def query_dict(params, list_fields=LIST_PARAMS) -> dict:
    """Query string → plain dict; list parameters accept repeated keys and comma-separated values."""
    data = {}
    for key in params:
        if key in list_fields:
            values = []
            for raw in params.getlist(key):
                values.extend(part.strip() for part in str(raw).split(",") if part.strip())
            data[key] = values
        else:
            data[key] = params.get(key)
    return data


class StayQuerySerializer(serializers.Serializer):
    checkin = serializers.DateField(required=False, allow_null=True, default=None)
    checkout = serializers.DateField(required=False, allow_null=True, default=None)
    adults = serializers.IntegerField(min_value=1, max_value=20, default=2)
    children = serializers.IntegerField(min_value=0, max_value=10, default=0)
    children_ages = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=17), required=False, default=list
    )

    dates_required = False

    def validate(self, data):
        checkin, checkout = data.get("checkin"), data.get("checkout")
        if self.dates_required and not (checkin and checkout):
            raise serializers.ValidationError({"checkin": ["Indica las fechas de llegada y salida"]})
        if bool(checkin) != bool(checkout):
            raise serializers.ValidationError({"checkout": ["Indica las fechas de llegada y salida"]})
        if checkin and checkout:
            if checkout <= checkin:
                raise serializers.ValidationError({"checkout": ["La salida debe ser posterior a la llegada"]})
            if checkin < timezone.localdate():
                raise serializers.ValidationError({"checkin": ["La llegada no puede ser en el pasado"]})
            if (checkout - checkin).days > MAX_ONLINE_NIGHTS:
                raise serializers.ValidationError(
                    {"checkout": [f"Las reservas en línea son de máximo {MAX_ONLINE_NIGHTS} noches"]}
                )
        ages = data.get("children_ages") or []
        if ages and len(ages) != data.get("children", 0):
            raise serializers.ValidationError({"children_ages": ["Indica la edad de cada niño"]})
        return data


class SearchQuerySerializer(StayQuerySerializer):
    city = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    type = serializers.ListField(child=serializers.CharField(max_length=20), required=False, default=list)
    stars = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=5), required=False, default=list
    )
    amenities = serializers.ListField(
        child=serializers.CharField(max_length=50), required=False, default=list
    )
    min_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=0, required=False, allow_null=True, default=None
    )
    max_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=0, required=False, allow_null=True, default=None
    )
    sort = serializers.CharField(required=False, default="recommended")

    def validate_type(self, value):
        unknown = sorted(set(value) - set(Property.PropertyType.values))
        if unknown:
            raise serializers.ValidationError(f"Tipos desconocidos: {', '.join(unknown)}")
        return value

    def validate_sort(self, value):
        if value not in SORTS:
            raise serializers.ValidationError(f"Usa uno de: {', '.join(SORTS)}")
        return value


class OffersQuerySerializer(StayQuerySerializer):
    dates_required = True
    via = serializers.ChoiceField(choices=CHANNELS, default="marketplace")
    promo_code = serializers.CharField(required=False, allow_blank=True, max_length=40, default="")
    foreign = serializers.BooleanField(required=False, default=False)


class ChannelQuerySerializer(serializers.Serializer):
    via = serializers.ChoiceField(choices=CHANNELS, default="marketplace")


# ---- Checkout / booking bodies ---------------------------------------------------------------------------


class BookingItemSerializer(serializers.Serializer):
    room_type_id = serializers.UUIDField()
    rate_plan_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_UNITS, default=1)
    adults = serializers.IntegerField(min_value=1, max_value=20)
    children = serializers.IntegerField(min_value=0, max_value=10, default=0)
    children_ages = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=17), required=False, default=list
    )

    def validate(self, data):
        ages = data.get("children_ages") or []
        if ages and len(ages) != data.get("children", 0):
            raise serializers.ValidationError({"children_ages": ["Indica la edad de cada niño"]})
        return data


class BookingExtraSerializer(serializers.Serializer):
    extra_id = serializers.UUIDField()
    quantity = serializers.IntegerField(
        min_value=1, max_value=99, required=False, allow_null=True, default=None
    )


class ResidenceSerializer(serializers.Serializer):
    """What the price depends on: nationality and residence decide the IVA exemption (ET art. 481)."""

    nationality = serializers.CharField(required=False, allow_blank=True, max_length=2, default="")
    country_of_residence = serializers.CharField(required=False, allow_blank=True, max_length=2, default="")

    def validate_nationality(self, value):
        return _country(value)

    def validate_country_of_residence(self, value):
        return _country(value)


def _country(value: str) -> str:
    value = (value or "").strip().upper()
    if value and (len(value) != 2 or not value.isalpha()):
        raise serializers.ValidationError("Usa el código de país de dos letras (ISO 3166)")
    return value


class BookingGuestSerializer(ResidenceSerializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    email = serializers.EmailField(max_length=254)
    phone = serializers.CharField(max_length=32)
    nationality = serializers.CharField(max_length=2)
    country_of_residence = serializers.CharField(max_length=2)
    city_of_residence = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    document_type = serializers.CharField(required=False, allow_blank=True, max_length=10, default="")
    document_number = serializers.CharField(required=False, allow_blank=True, max_length=40, default="")
    data_processing_consent = serializers.BooleanField()
    marketing_consent = serializers.BooleanField(required=False, default=False)

    def validate_document_type(self, value):
        value = (value or "").strip().upper()
        if value and value not in Guest.DocumentType.values:
            raise serializers.ValidationError("Tipo de documento inválido")
        return value

    def validate_data_processing_consent(self, value):
        if value is not True:
            raise serializers.ValidationError(
                "Necesitamos tu autorización para tratar tus datos y gestionar la reserva (Ley 1581 de 2012)"
            )
        return value

    def validate(self, data):
        if data.get("document_number") and not data.get("document_type"):
            raise serializers.ValidationError({"document_type": ["Indica el tipo de documento"]})
        return data


class CheckoutSerializer(serializers.Serializer):
    property_slug = serializers.SlugField(max_length=80)
    via = serializers.ChoiceField(choices=CHANNELS, default="marketplace")
    checkin = serializers.DateField()
    checkout = serializers.DateField()
    items = BookingItemSerializer(many=True)
    extras = BookingExtraSerializer(many=True, required=False, default=list)
    promo_code = serializers.CharField(required=False, allow_blank=True, max_length=40, default="")
    payment_option = serializers.ChoiceField(choices=PAYMENT_OPTIONS, default="pay_at_hotel")
    guest = ResidenceSerializer(required=False, default=dict)

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("Elige al menos una habitación")
        if len(items) > MAX_ITEMS:
            raise serializers.ValidationError(f"Máximo {MAX_ITEMS} opciones por reserva")
        return items

    def validate(self, data):
        if data["checkout"] <= data["checkin"]:
            raise serializers.ValidationError({"checkout": ["La salida debe ser posterior a la llegada"]})
        extras = [str(extra["extra_id"]) for extra in data.get("extras") or []]
        if len(extras) != len(set(extras)):
            raise serializers.ValidationError({"extras": ["Cada extra va una sola vez"]})
        return data


class BookingSerializer(CheckoutSerializer):
    guest = BookingGuestSerializer()
    special_requests = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")
    eta = serializers.TimeField(required=False, allow_null=True, default=None)
    language = serializers.CharField(required=False, default="es")

    def validate_language(self, value):
        value = (value or "es").strip().lower()[:2]
        return value if value in LANGUAGES else "es"


class LookupQuerySerializer(serializers.Serializer):
    email = serializers.EmailField()


# ---- Staff settings ----------------------------------------------------------------------------------------

HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
I18N_KEYS = ("es", "en")


class I18nTextField(serializers.JSONField):
    """`{"es": "...", "en": "..."}` (a plain string counts as Spanish); each text trimmed, ≤ `max_length`."""

    def __init__(self, *, max_length: int, **kwargs):
        self.max_length = max_length
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = {"es": data}
        if not isinstance(data, dict) or set(data) - set(I18N_KEYS):
            raise serializers.ValidationError('Usa {"es": "...", "en": "..."}')
        clean = {}
        for key, value in data.items():
            if value in (None, ""):
                continue
            if not isinstance(value, str):
                raise serializers.ValidationError("Cada idioma debe ser un texto")
            value = value.strip()
            if len(value) > self.max_length:
                raise serializers.ValidationError(f"Máximo {self.max_length} caracteres")
            if value:
                clean[key] = value
        return clean


class EngineSettingsSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    primary_color = serializers.CharField(required=False, allow_blank=True, max_length=7)
    headline = I18nTextField(max_length=120, required=False)
    show_promo_field = serializers.BooleanField(required=False)
    allowed_rate_plans = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=50)
    min_advance_hours = serializers.IntegerField(min_value=0, max_value=720, required=False)
    max_advance_days = serializers.IntegerField(min_value=1, max_value=730, required=False)
    terms = I18nTextField(max_length=2000, required=False)

    def validate_primary_color(self, value):
        if value and not HEX_COLOR.match(value):
            raise serializers.ValidationError("Usa un color #RRGGBB")
        return value.upper()

    def validate_allowed_rate_plans(self, value):
        from apps.marketplace.services.configuration import selectable_plans

        valid = {plan.pk for plan in selectable_plans(self.context["property"])}
        unknown = [str(pk) for pk in value if pk not in valid]
        if unknown:
            raise serializers.ValidationError("Solo puedes elegir tarifas públicas y activas de este hotel")
        return list(dict.fromkeys(value))


class ListingSerializer(serializers.Serializer):
    marketplace_listed = serializers.BooleanField(required=False)
    tagline = I18nTextField(max_length=140, required=False)
    highlights = serializers.ListField(child=I18nTextField(max_length=120), required=False, max_length=6)
    neighborhood = serializers.CharField(required=False, allow_blank=True, max_length=100)
    featured_photo_ids = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=12)

    def validate_highlights(self, value):
        return [item for item in value if item]

    def validate_featured_photo_ids(self, value):
        from apps.inventory.models import Photo

        ids = list(dict.fromkeys(value))
        found = set(
            Photo.objects.filter(
                pk__in=ids, property=self.context["property"], room__isnull=True
            ).values_list("pk", flat=True)
        )
        if len(found) != len(ids):
            raise serializers.ValidationError("Elige fotos de este hotel")
        return ids


class ImageUploadSerializer(serializers.Serializer):
    image = serializers.ImageField()

    def validate_image(self, image):
        if image.size > MAX_IMAGE_BYTES:
            raise serializers.ValidationError("La imagen supera 10 MB")
        pil_image = getattr(image, "image", None)
        if pil_image is None or pil_image.format not in IMAGE_FORMATS:
            raise serializers.ValidationError("Formatos permitidos: JPG, PNG o WEBP")
        return image
