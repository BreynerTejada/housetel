"""Which properties sell online, through which channel, and within which booking window.

Channels (`via`): `marketplace` (the Housetel marketplace, needs `Property.marketplace_listed`) and
`booking_engine` (the hotel's own page `/h/<slug>`, needs `BookingEngineSettings.enabled`, on by default).
Both need an active property of an organization that is not suspended or cancelled.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import QuerySet

from apps.core import integrations
from apps.core.dates import nights, property_now
from apps.core.errors import DomainError, NotFoundError
from apps.core.models import IntegrationSetting, Property
from apps.core.runtime import simulations_enabled
from apps.marketplace.models import BookingEngineSettings, ListingContent

MARKETPLACE = "marketplace"
BOOKING_ENGINE = "booking_engine"
CHANNELS = (MARKETPLACE, BOOKING_ENGINE)
ONLINE_ORGANIZATION_STATUSES = ("trial", "active", "past_due")
MAX_ONLINE_NIGHTS = 30
DEFAULT_PRIMARY_COLOR = "#B4583B"


def selling_properties() -> QuerySet:
    """Active properties of organizations that still operate (trial, active, past due)."""
    return Property.objects.select_related("organization").filter(
        status=Property.Status.ACTIVE, organization__status__in=ONLINE_ORGANIZATION_STATUSES
    )


def listed_properties() -> QuerySet:
    return selling_properties().filter(marketplace_listed=True)


def engine_settings(prop) -> BookingEngineSettings:
    """The property's settings row, or unsaved defaults (public reads never write)."""
    try:
        return prop.booking_engine
    except BookingEngineSettings.DoesNotExist:
        return BookingEngineSettings(property=prop)


def listing_content(prop) -> ListingContent:
    try:
        return prop.listing
    except ListingContent.DoesNotExist:
        return ListingContent(property=prop)


def channel_property(slug: str, via: str) -> Property:
    """The property that sells on `via`, or 404 (`not_found`, or `booking_engine_disabled`)."""
    if via not in CHANNELS:
        raise DomainError(
            "Canal inválido", code="invalid_channel", fields={"via": ["Usa marketplace o booking_engine"]}
        )
    prop = selling_properties().filter(slug=slug).first()
    if prop is None or (via == MARKETPLACE and not prop.marketplace_listed):
        raise NotFoundError("Este hotel no está disponible en el marketplace")
    if via == BOOKING_ENGINE and not engine_settings(prop).enabled:
        raise NotFoundError("Este hotel no recibe reservas en línea", code="booking_engine_disabled")
    return prop


def allowed_plan_ids(settings: BookingEngineSettings) -> set:
    """Plans the booking engine may sell (empty = every public plan)."""
    if settings.pk is None:
        return set()
    return set(settings.allowed_rate_plans.values_list("pk", flat=True))


def online_payments_enabled(prop) -> bool:
    """Whether guests can pay online (plan P6): the payments integration is enabled (a missing row means the
    default) and, where simulations are off (production), really live: enabled, in real mode and configured
    (`core.integrations.is_live`). Otherwise the checkout only offers "Pagar en el hotel" and plans that
    need a deposit are not sold online."""
    if not simulations_enabled():
        return integrations.is_live(prop, "payments")
    enabled = (
        IntegrationSetting.objects.filter(property=prop, kind=IntegrationSetting.Kind.PAYMENTS)
        .values_list("enabled", flat=True)
        .first()
    )
    return True if enabled is None else bool(enabled)


def local_today(prop) -> date:
    """Today's calendar date where the hotel is (the business date may lag until the night audit)."""
    return property_now(prop).date()


@dataclass(frozen=True)
class BookingWindow:
    earliest_checkin: date
    latest_checkin: date
    max_nights: int = MAX_ONLINE_NIGHTS

    def as_dict(self) -> dict:
        return {
            "earliest_checkin": self.earliest_checkin.isoformat(),
            "latest_checkin": self.latest_checkin.isoformat(),
            "max_nights": self.max_nights,
        }


def booking_window(prop, settings: BookingEngineSettings | None = None) -> BookingWindow:
    """Online check-ins go from the local date of `now + min_advance_hours` to today + `max_advance_days`."""
    settings = settings or engine_settings(prop)
    now = property_now(prop)
    earliest = (now + timedelta(hours=settings.min_advance_hours or 0)).date()
    latest = now.date() + timedelta(days=settings.max_advance_days or 0)
    return BookingWindow(earliest_checkin=earliest, latest_checkin=max(latest, earliest))


def check_stay_dates(prop, checkin, checkout, settings: BookingEngineSettings | None = None) -> None:
    """Validate an online stay against the booking window (400 with a stable `code`)."""
    if not checkin or not checkout or checkout <= checkin:
        raise DomainError("La salida debe ser posterior a la llegada", code="invalid_dates")
    window = booking_window(prop, settings)
    if checkin < window.earliest_checkin:
        raise DomainError(
            "Este hotel no recibe reservas en línea para esa fecha de llegada",
            code="too_soon",
            earliest_checkin=window.earliest_checkin,
        )
    if checkin > window.latest_checkin:
        raise DomainError(
            "Esa fecha todavía no está abierta para reservas en línea",
            code="too_far",
            latest_checkin=window.latest_checkin,
        )
    if len(nights(checkin, checkout)) > window.max_nights:
        raise DomainError(
            f"Las reservas en línea son de máximo {window.max_nights} noches",
            code="stay_too_long",
            max_nights=window.max_nights,
        )


def brand(prop, settings: BookingEngineSettings | None = None) -> dict:
    """Colors and logo of the hotel on its guest-facing pages: engine override → hotel brand → Housetel."""
    settings = settings or engine_settings(prop)
    branding = prop.branding or {}
    return {
        "primary_color": settings.primary_color or branding.get("primary_color") or DEFAULT_PRIMARY_COLOR,
        "logo": settings.logo.url if settings.logo else (branding.get("logo") or ""),
    }
