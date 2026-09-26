"""Booking factories. A stay's room type / rate plan are created in the reservation's property."""

from datetime import timedelta
from decimal import Decimal

import factory
from django.utils.timezone import localdate

from apps.bookings.models import Reservation, ReservationGroup, Stay
from apps.core.tests.factories import PropertyFactory
from apps.guests.tests.factories import GuestFactory
from apps.inventory.tests.factories import RoomTypeFactory
from apps.rates.tests.factories import RatePlanFactory


class ReservationGroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ReservationGroup

    property = factory.SubFactory(PropertyFactory)
    name = factory.Sequence(lambda n: f"Grupo {n}")


class ReservationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Reservation

    property = factory.SubFactory(PropertyFactory)
    code = factory.Sequence(lambda n: f"HT-T{n:05d}")
    status = Reservation.Status.CONFIRMED
    source = Reservation.Source.FRONT_DESK
    booker = factory.SubFactory(GuestFactory, organization=factory.SelfAttribute("..property.organization"))
    checkin_date = factory.LazyFunction(lambda: localdate() + timedelta(days=7))
    checkout_date = factory.LazyAttribute(lambda o: o.checkin_date + timedelta(days=2))
    adults = 2
    children = 0
    currency = "COP"
    total_amount = Decimal("0")
    language = "es"


class StayFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Stay
        skip_postgeneration_save = True

    reservation = factory.SubFactory(ReservationFactory)
    room_type = factory.SubFactory(RoomTypeFactory, property=factory.SelfAttribute("..reservation.property"))
    rate_plan = factory.SubFactory(RatePlanFactory, property=factory.SelfAttribute("..reservation.property"))
    room = None
    bed = None
    checkin_date = factory.SelfAttribute("reservation.checkin_date")
    checkout_date = factory.SelfAttribute("reservation.checkout_date")
    adults = factory.SelfAttribute("reservation.adults")
    children = factory.SelfAttribute("reservation.children")
    status = factory.SelfAttribute("reservation.status")
    total_amount = Decimal("0")

    @factory.post_generation
    def occupants(self, create, extracted, **kwargs):
        if create and extracted:
            self.occupants.set(extracted)
