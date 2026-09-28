"""Housekeeping factories. A task / ticket belongs to the property of its room."""

import factory

from apps.housekeeping.models import HousekeepingTask, MaintenanceTicket, Priority
from apps.inventory.tests.factories import RoomFactory


class HousekeepingTaskFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = HousekeepingTask

    room = factory.SubFactory(RoomFactory)
    property = factory.SelfAttribute("room.property")
    kind = HousekeepingTask.Kind.DEPARTURE_CLEAN
    status = HousekeepingTask.Status.PENDING
    priority = Priority.NORMAL
    business_date = factory.LazyAttribute(lambda o: o.property.business_date)
    estimated_minutes = 30
    created_source = HousekeepingTask.Source.MANUAL


class MaintenanceTicketFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MaintenanceTicket

    room = factory.SubFactory(RoomFactory)
    property = factory.SelfAttribute("room.property")
    title = factory.Sequence(lambda n: f"Daño {n}")
    description = "Reportado por limpieza"
    priority = Priority.NORMAL
    status = MaintenanceTicket.Status.OPEN
