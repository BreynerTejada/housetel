"""Helpers shared by the bookings tests (plain functions; fixtures live in conftest.py)."""

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from apps.bookings.types import ReservationRequest, StayRequest
from apps.guests.types import GuestInput


def oct_(day: int) -> date:
    """2026-10-01 is a Thursday."""
    return date(2026, 10, 1) + timedelta(days=day - 1)


def build_hotel(prop) -> SimpleNamespace:
    """The hotel described in conftest.py, created in `prop` (business date 2026-10-01)."""
    from apps.inventory.tests.factories import BedFactory, DormRoomTypeFactory, RoomFactory, RoomTypeFactory
    from apps.rates.tests.factories import RatePlanFactory, RoomTypeRateDefaultsFactory, TaxFactory

    prop.business_date = oct_(1)
    prop.save(update_fields=["business_date", "updated_at"])
    dbl = RoomTypeFactory(
        property=prop,
        code="DBL",
        base_occupancy=2,
        max_adults=2,
        max_children=1,
        max_occupancy=3,
        sort_order=1,
    )
    ste = RoomTypeFactory(
        property=prop,
        code="STE",
        base_occupancy=2,
        max_adults=2,
        max_children=1,
        max_occupancy=3,
        sort_order=2,
    )
    dorm_type = DormRoomTypeFactory(property=prop, code="DORM", sort_order=3)
    rooms = {
        "101": RoomFactory(room_type=dbl, number="101", floor="1", sort_order=1),
        "102": RoomFactory(room_type=dbl, number="102", floor="1", sort_order=2),
        "201": RoomFactory(room_type=dbl, number="201", floor="2", sort_order=3),
        "301": RoomFactory(room_type=ste, number="301", floor="3", sort_order=4),
        "D1": RoomFactory(room_type=dorm_type, number="D1", floor="1", sort_order=5),
    }
    beds = {label: BedFactory(room=rooms["D1"], label=label) for label in "ABCD"}
    plan = RatePlanFactory(property=prop, code="BAR", room_types=[dbl, ste, dorm_type])
    for room_type, price in ((dbl, "320000"), (ste, "650000"), (dorm_type, "65000")):
        RoomTypeRateDefaultsFactory(room_type=room_type, rate_plan=plan, price=Decimal(price))
    iva = TaxFactory(
        property=prop,
        code="IVA",
        rate=Decimal("19.00"),
        applies_to="room",
        included_in_price=False,
        exempt_foreign_non_residents=True,
    )
    return SimpleNamespace(
        prop=prop,
        dbl=dbl,
        ste=ste,
        dorm_type=dorm_type,
        rooms=rooms,
        dorm=rooms["D1"],
        beds=beds,
        plan=plan,
        iva=iva,
    )


_document_seq = iter(range(1, 10_000_000))


def guest_input(**overrides) -> GuestInput:
    """A Colombian resident booker with a unique document (IVA applies)."""
    number = next(_document_seq)
    values = {
        "first_name": "Laura",
        "last_name": "Gómez",
        "email": f"laura{number}@example.com",
        "document_type": "CC",
        "document_number": f"{52000000 + number}",
        "nationality": "CO",
        "country_of_residence": "CO",
    }
    values.update(overrides)
    return GuestInput(**values)


def foreign_input(**overrides) -> GuestInput:
    """A foreign non-resident booker (IVA-exempt lodging)."""
    number = next(_document_seq)
    values = {
        "first_name": "John",
        "last_name": "Smith",
        "email": f"john{number}@example.com",
        "document_type": "PA",
        "document_number": f"X{number:08d}",
        "nationality": "US",
        "country_of_residence": "US",
        "language": "en",
    }
    values.update(overrides)
    return GuestInput(**values)


def stay_request(hotel, checkin, checkout, *, room_type=None, plan=None, adults=2, **kwargs) -> StayRequest:
    return StayRequest(
        room_type_id=(room_type or hotel.dbl).pk,
        rate_plan_id=(plan or hotel.plan).pk,
        checkin=checkin,
        checkout=checkout,
        adults=adults,
        **kwargs,
    )


def reservation_request(hotel, stays, **kwargs) -> ReservationRequest:
    booker = kwargs.pop("booker", None) or guest_input()
    return ReservationRequest(property=hotel.prop, booker=booker, stays=list(stays), **kwargs)


def book(
    hotel, checkin, checkout, *, actor=None, room_type=None, plan=None, adults=2, stay_kwargs=None, **kwargs
):
    """Create a one-stay reservation through the real service."""
    from apps.bookings.services.reservations import create_reservation

    stay = stay_request(
        hotel, checkin, checkout, room_type=room_type, plan=plan, adults=adults, **(stay_kwargs or {})
    )
    return create_reservation(reservation_request(hotel, [stay], **kwargs), actor=actor)


def money(value) -> Decimal:
    return Decimal(str(value))


def entry(day: date, amount, net, tax) -> dict:
    """A Stay.nightly_rates entry as B2b stores it (money as 2-decimal strings)."""
    return {
        "date": day.isoformat(),
        "amount": f"{Decimal(str(amount)):.2f}",
        "net": f"{Decimal(str(net)):.2f}",
        "tax": f"{Decimal(str(tax)):.2f}",
    }
