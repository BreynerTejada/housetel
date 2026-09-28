"""Helpers of the front desk tests: reservations in every state, created through the booking services."""

from datetime import date, time
from decimal import Decimal

from apps.bookings.models import Stay
from apps.bookings.services.reservations import (
    assign_room,
    cancel_reservation,
    check_in,
    check_out,
    mark_no_show,
)
from apps.bookings.tests.helpers import book, guest_input


def fresh(stay) -> Stay:
    return Stay.objects.select_related("reservation", "room", "bed").get(pk=stay.pk)


def set_business_date(hotel, day: date) -> None:
    hotel.prop.business_date = day
    hotel.prop.save(update_fields=["business_date", "updated_at"])


def new_stay(hotel, checkin, checkout, *, room=None, bed=None, room_type=None, adults=None, **kwargs) -> Stay:
    """One-stay reservation (dorm: one bed) through `create_reservation`, optionally assigned."""
    room_type = room_type or hotel.dbl
    if adults is None:
        adults = 1 if room_type.kind == "dorm" else 2
    reservation = book(hotel, checkin, checkout, room_type=room_type, adults=adults, **kwargs)
    stay = reservation.stays.get()
    if room is not None:
        assign_room(stay, room, bed=bed)
    return fresh(stay)


def arrived(hotel, checkin, checkout, **kwargs) -> Stay:
    """A stay already in house (checked in with force when its arrival is in the past)."""
    stay = new_stay(hotel, checkin, checkout, **kwargs)
    check_in(stay, force=True)
    return fresh(stay)


def departed(hotel, checkin, checkout, **kwargs) -> Stay:
    """A stay checked in and out (balance left unpaid: forced check-out)."""
    stay = arrived(hotel, checkin, checkout, **kwargs)
    check_out(stay, force=True)
    return fresh(stay)


def cancelled(hotel, checkin, checkout, **kwargs) -> Stay:
    stay = new_stay(hotel, checkin, checkout, **kwargs)
    cancel_reservation(stay.reservation, reason="Cambio de planes")
    return fresh(stay)


def no_show(hotel, checkin, checkout, **kwargs) -> Stay:
    stay = new_stay(hotel, checkin, checkout, **kwargs)
    mark_no_show(stay.reservation, source="user")
    return fresh(stay)


def vip_booker(**overrides):
    return guest_input(first_name="Valeria", last_name="Mejía", **overrides)


def eta(hour: int, minute: int = 0) -> time:
    return time(hour, minute)


def money(value) -> Decimal:
    return Decimal(str(value))
