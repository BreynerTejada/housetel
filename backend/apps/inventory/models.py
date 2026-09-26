"""Inventory (spec §4): categories (RoomType) → rooms → beds, with category→room attribute inheritance."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import F, Q

from apps.core.fields import i18n_field, json_field
from apps.core.i18n import t
from apps.core.models import BaseModel, Organization, Property

# A room may override exactly these RoomType attributes (in `Room.overrides`); see
# services.effective_attributes.
ROOM_OVERRIDABLE_FIELDS = [
    "name",
    "description",
    "base_occupancy",
    "max_adults",
    "max_children",
    "max_occupancy",
    "beds",
    "size_m2",
    "view",
    "smoking_allowed",
    "accessible",
    "housekeeping_minutes",
]


class Amenity(BaseModel):
    """`organization=None` = global catalog; organizations can add their own codes."""

    class Category(models.TextChoices):
        ROOM = "room", "Habitación"
        BATHROOM = "bathroom", "Baño"
        PROPERTY = "property", "Propiedad"
        ACCESSIBILITY = "accessibility", "Accesibilidad"
        VIEW = "view", "Vista"

    organization = models.ForeignKey(
        Organization, null=True, blank=True, on_delete=models.CASCADE, related_name="amenities"
    )
    code = models.CharField(max_length=50)
    name = i18n_field()
    icon = models.CharField(max_length=50, blank=True)  # lucide-react icon name, e.g. "wifi"
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.ROOM)

    class Meta:
        ordering = ["category", "code"]
        verbose_name_plural = "amenities"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"], nulls_distinct=False, name="amenity_code_unique"
            )
        ]

    def __str__(self) -> str:
        return t(self.name) or self.code


class RoomType(BaseModel):
    """Category. Private: units are rooms. Dorm: units are beds (one person per bed)."""

    class Kind(models.TextChoices):
        PRIVATE = "private", "Privada"
        DORM = "dorm", "Dormitorio (venta por cama)"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="room_types")
    code = models.CharField(max_length=20)
    name = i18n_field()
    description = i18n_field()
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PRIVATE)
    base_occupancy = models.PositiveSmallIntegerField(default=2)
    max_adults = models.PositiveSmallIntegerField(default=2)
    max_children = models.PositiveSmallIntegerField(default=0)
    max_occupancy = models.PositiveSmallIntegerField(default=2)
    beds = json_field(default=list)  # [{"type": "queen", "count": 1}]
    size_m2 = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    view = models.CharField(max_length=50, blank=True)
    smoking_allowed = models.BooleanField(default=False)
    accessible = models.BooleanField(default=False)
    amenities = models.ManyToManyField(Amenity, blank=True, related_name="room_types")
    color = models.CharField(max_length=7, default="#4E6C88")
    housekeeping_minutes = models.PositiveSmallIntegerField(default=30)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    custom_values = json_field()

    class Meta:
        ordering = ["sort_order", "code"]
        constraints = [models.UniqueConstraint(fields=["property", "code"], name="room_type_code_unique")]

    def __str__(self) -> str:
        return f"{self.code} · {t(self.name)}"


class Room(BaseModel):
    class HousekeepingStatus(models.TextChoices):
        CLEAN = "clean", "Limpia"
        DIRTY = "dirty", "Sucia"
        INSPECTED = "inspected", "Inspeccionada"
        OUT_OF_SERVICE = "out_of_service", "Fuera de servicio"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="rooms")
    room_type = models.ForeignKey(RoomType, on_delete=models.RESTRICT, related_name="rooms")
    number = models.CharField(max_length=20)
    name = models.CharField(max_length=100, blank=True)  # optional display name of this room
    floor = models.CharField(max_length=20, blank=True)
    building = models.CharField(max_length=50, blank=True)
    overrides = json_field()  # only keys in ROOM_OVERRIDABLE_FIELDS
    extra_amenities = models.ManyToManyField(Amenity, blank=True, related_name="rooms_with_extra")
    removed_amenities = models.ManyToManyField(Amenity, blank=True, related_name="rooms_without")
    custom_values = json_field()
    housekeeping_status = models.CharField(
        max_length=20, choices=HousekeepingStatus.choices, default=HousekeepingStatus.CLEAN
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    connecting_rooms = models.ManyToManyField("self", blank=True)

    class Meta:
        ordering = ["sort_order", "number"]
        constraints = [models.UniqueConstraint(fields=["property", "number"], name="room_number_unique")]
        indexes = [models.Index(fields=["property", "housekeeping_status"], name="room_property_hk_idx")]

    def __str__(self) -> str:
        return self.number

    def clean(self):
        errors = {}
        if not isinstance(self.overrides, dict):
            errors["overrides"] = ["Debe ser un objeto {campo: valor}"]
        else:
            invalid = sorted(set(self.overrides) - set(ROOM_OVERRIDABLE_FIELDS))
            if invalid:
                errors["overrides"] = [f"Campos no sobrescribibles: {', '.join(invalid)}"]
        if self.room_type_id and self.property_id and self.room_type.property_id != self.property_id:
            errors["room_type"] = ["La categoría pertenece a otra propiedad"]
        if errors:
            raise ValidationError(errors)


class Bed(BaseModel):
    """Sellable bed of a dorm room."""

    class BedType(models.TextChoices):
        SINGLE = "single", "Sencilla"
        BUNK_TOP = "bunk_top", "Camarote (arriba)"
        BUNK_BOTTOM = "bunk_bottom", "Camarote (abajo)"
        DOUBLE = "double", "Doble"

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="beds")
    label = models.CharField(max_length=20)
    bed_type = models.CharField(max_length=20, choices=BedType.choices, default=BedType.SINGLE)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["label"]
        constraints = [models.UniqueConstraint(fields=["room", "label"], name="bed_label_unique")]

    def __str__(self) -> str:
        return f"{self.room.number}-{self.label}"


class CustomFieldDefinition(BaseModel):
    """Hotel-defined field; values live in `<model>.custom_values` (validated by
    services.validate_custom_values)."""

    class AppliesTo(models.TextChoices):
        ROOM_TYPE = "room_type", "Categoría"
        ROOM = "room", "Habitación"
        GUEST = "guest", "Huésped"
        RESERVATION = "reservation", "Reserva"

    class FieldType(models.TextChoices):
        TEXT = "text", "Texto"
        NUMBER = "number", "Número"
        BOOLEAN = "boolean", "Sí/No"
        SELECT = "select", "Lista"
        MULTISELECT = "multiselect", "Lista múltiple"
        DATE = "date", "Fecha"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="custom_field_definitions"
    )
    property = models.ForeignKey(
        Property, null=True, blank=True, on_delete=models.CASCADE, related_name="custom_field_definitions"
    )  # null = whole organization
    applies_to = models.CharField(max_length=20, choices=AppliesTo.choices)
    key = models.SlugField(max_length=50)
    label = i18n_field()
    field_type = models.CharField(max_length=20, choices=FieldType.choices, default=FieldType.TEXT)
    options = json_field(default=list)  # [{"value": "sea", "label": {"es": "Mar", "en": "Sea"}}]
    required = models.BooleanField(default=False)
    default_value = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    show_in_marketplace = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["applies_to", "sort_order", "key"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "property", "applies_to", "key"],
                nulls_distinct=False,
                name="custom_field_key_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.applies_to}.{self.key}"


class Photo(BaseModel):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="photos")
    room_type = models.ForeignKey(
        RoomType, null=True, blank=True, on_delete=models.CASCADE, related_name="photos"
    )
    room = models.ForeignKey(Room, null=True, blank=True, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="photos/%Y/%m/")
    caption = i18n_field()
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self) -> str:
        return self.image.name


class RoomBlock(BaseModel):
    """Takes a room (or one dorm bed) out of inventory for [start_date, end_date) until released."""

    class Kind(models.TextChoices):
        OUT_OF_ORDER = "out_of_order", "Fuera de orden"
        OUT_OF_SERVICE = "out_of_service", "Fuera de servicio"
        MAINTENANCE = "maintenance", "Mantenimiento"
        OWNER_HOLD = "owner_hold", "Uso del propietario"

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="blocks")
    bed = models.ForeignKey(Bed, null=True, blank=True, on_delete=models.CASCADE, related_name="blocks")
    start_date = models.DateField()
    end_date = models.DateField()  # exclusive
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OUT_OF_ORDER)
    reason = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["start_date", "created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(end_date__gt=F("start_date")), name="room_block_dates_valid")
        ]
        indexes = [models.Index(fields=["room", "start_date", "end_date"], name="room_block_range_idx")]

    def __str__(self) -> str:
        return f"{self.room} {self.start_date}→{self.end_date} ({self.kind})"

    @property
    def is_active(self) -> bool:
        return self.released_at is None
