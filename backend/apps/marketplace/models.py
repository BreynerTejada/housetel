"""Marketplace and booking engine (plan C4).

- `BookingEngineSettings`: the hotel's own booking page `/h/<slug>` and embeddable widget `/embed/<slug>`.
  `primary_color` / `logo` override the hotel brand (`Property.branding`) on the engine; an empty value
  inherits it. The advance window (`min_advance_hours`, `max_advance_days`) applies to every online booking
  (booking engine and marketplace).
- `ListingContent`: how the hotel shows up in the public marketplace (featured photos in order, highlights,
  neighborhood, tagline). Whether it is listed at all is `Property.marketplace_listed` (C4 edits it through
  its own listing API — authorized exception of the plan).

Rows are optional: a property without them uses the defaults (`services.engine.engine_settings`).
"""

from django.core.validators import MaxValueValidator
from django.db import models

from apps.core.fields import i18n_field, json_field
from apps.core.models import BaseModel, Property
from apps.inventory.models import Photo
from apps.rates.models import RatePlan

DEFAULT_MAX_ADVANCE_DAYS = 365


def _engine_upload(instance, filename):
    return f"booking-engine/{instance.property_id}/{filename}"


class BookingEngineSettings(BaseModel):
    property = models.OneToOneField(Property, on_delete=models.CASCADE, related_name="booking_engine")
    enabled = models.BooleanField(default=True)
    primary_color = models.CharField(max_length=7, blank=True)  # "#RRGGBB"; empty → Property.branding
    logo = models.ImageField(upload_to=_engine_upload, blank=True)  # empty → Property.branding.logo
    hero_image = models.ImageField(upload_to=_engine_upload, blank=True)  # empty → first listing photo
    headline = i18n_field()  # {"es": "...", "en": "..."}
    show_promo_field = models.BooleanField(default=True)
    allowed_rate_plans = models.ManyToManyField(RatePlan, blank=True, related_name="+")  # empty = all public
    min_advance_hours = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(720)])
    max_advance_days = models.PositiveSmallIntegerField(
        default=DEFAULT_MAX_ADVANCE_DAYS, validators=[MaxValueValidator(730)]
    )
    terms = i18n_field()

    class Meta:
        verbose_name = "booking engine settings"
        verbose_name_plural = "booking engine settings"

    def __str__(self) -> str:
        return f"Motor de reservas · {self.property}"


class ListingContent(BaseModel):
    property = models.OneToOneField(Property, on_delete=models.CASCADE, related_name="listing")
    featured_photos = models.ManyToManyField(Photo, through="ListingPhoto", blank=True, related_name="+")
    tagline = i18n_field()  # one line for cards: {"es": "...", "en": "..."}
    highlights = json_field(default=list)  # [{"es": "...", "en": "..."}], at most 6
    neighborhood = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "listing content"
        verbose_name_plural = "listing contents"

    def __str__(self) -> str:
        return f"Ficha del marketplace · {self.property}"


class ListingPhoto(BaseModel):
    """Featured photo of a listing, in order (the first one is the cover)."""

    listing = models.ForeignKey(ListingContent, on_delete=models.CASCADE, related_name="listing_photos")
    photo = models.ForeignKey(Photo, on_delete=models.CASCADE, related_name="+")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]
        constraints = [models.UniqueConstraint(fields=["listing", "photo"], name="listing_photo_unique")]

    def __str__(self) -> str:
        return f"{self.listing_id} · {self.photo_id}"
