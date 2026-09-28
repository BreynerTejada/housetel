"""Who the magic link belongs to, the portal settings of a property and when the online check-in is open."""

from dataclasses import dataclass
from datetime import date, timedelta

from apps.bookings.models import Reservation
from apps.core.errors import NotFoundError
from apps.core.tokens import read_reservation_token
from apps.guestportal.models import GuestPortalSettings, OnlineCheckin

DEFAULT_TERMS = {
    "es": (
        "Confirmo que los datos registrados son verdaderos y corresponden a los huéspedes de esta reserva. "
        "Autorizo al hotel a tratar mis datos personales y los de mis acompañantes para el registro "
        "hotelero (Tarjeta de Registro Alojamiento), los reportes a Migración Colombia cuando apliquen y la "
        "prestación del servicio, conforme a la Ley 1581 de 2012. Acepto el reglamento del hotel y los "
        "horarios de ingreso y salida."
    ),
    "en": (
        "I confirm that the data provided is true and belongs to the guests of this booking. I authorize the "
        "hotel to process my personal data and that of my companions for the hotel registration (Tarjeta de "
        "Registro Alojamiento), the reports to Colombian Migration when they apply and the provision of the "
        "service, under Colombian Law 1581 of 2012. I accept the hotel rules and the check-in and check-out "
        "times."
    ),
}


class InvalidLink(NotFoundError):
    code = "invalid_link"


def portal_reservation(token: str) -> Reservation:
    """The reservation of a magic link, or InvalidLink (404) when the token was tampered with, signed for
    something else or its reservation no longer exists."""
    reservation = read_reservation_token(token or "")
    if reservation is None:
        raise InvalidLink("Este enlace no es válido o ya no está disponible")
    return (
        Reservation.objects.select_related("property__organization", "booker")
        .filter(pk=reservation.pk)
        .first()
    ) or reservation


def portal_settings(prop) -> GuestPortalSettings:
    """The property's portal settings (created with the defaults the first time)."""
    settings, _ = GuestPortalSettings.objects.get_or_create(property=prop)
    return settings


def terms_of(settings: GuestPortalSettings) -> dict:
    """The hotel's terms, falling back to the default text per language."""
    terms = settings.terms or {}
    return {lang: (terms.get(lang) or "").strip() or text for lang, text in DEFAULT_TERMS.items()}


def checkin_of(reservation) -> OnlineCheckin | None:
    return OnlineCheckin.objects.filter(reservation=reservation).first()


def ensure_checkin(reservation) -> OnlineCheckin:
    checkin, _ = OnlineCheckin.objects.get_or_create(reservation=reservation)
    return checkin


@dataclass(frozen=True)
class CheckinWindow:
    """`reason` when closed: not_open_yet | tentative | checked_in | checked_out | cancelled | no_show |
    past."""

    opens_on: date
    is_open: bool
    reason: str | None

    def as_dict(self) -> dict:
        return {"opens_on": self.opens_on.isoformat(), "is_open": self.is_open, "reason": self.reason}


CLOSED_STATUSES = {"tentative", "checked_in", "checked_out", "cancelled", "no_show"}


def checkin_window(reservation, settings: GuestPortalSettings) -> CheckinWindow:
    """The online check-in opens `checkin_opens_days_before` days before arrival (business date of the
    property) and stays open until the guest checks in, for confirmed reservations only."""
    opens_on = reservation.checkin_date - timedelta(days=settings.checkin_opens_days_before)
    today = reservation.property.business_date
    if reservation.status in CLOSED_STATUSES:
        return CheckinWindow(opens_on, False, reservation.status)
    if today < opens_on:
        return CheckinWindow(opens_on, False, "not_open_yet")
    if today >= reservation.checkout_date:
        return CheckinWindow(opens_on, False, "past")
    return CheckinWindow(opens_on, True, None)
