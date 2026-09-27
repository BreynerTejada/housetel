"""Filters of `GET reservations/` (dates are inclusive: `arrival_from ≤ checkin_date ≤ arrival_to`)."""

from django.db.models import Exists, OuterRef, Q, Value
from django.db.models.functions import Concat
from django_filters import rest_framework as filters

from apps.bookings.models import BookingStatus, Reservation, Stay


class ReservationFilter(filters.FilterSet):
    status = filters.MultipleChoiceFilter(choices=BookingStatus.choices)
    source = filters.MultipleChoiceFilter(choices=Reservation.Source.choices)
    channel_code = filters.CharFilter()
    arrival_from = filters.DateFilter(field_name="checkin_date", lookup_expr="gte")
    arrival_to = filters.DateFilter(field_name="checkin_date", lookup_expr="lte")
    departure_from = filters.DateFilter(field_name="checkout_date", lookup_expr="gte")
    departure_to = filters.DateFilter(field_name="checkout_date", lookup_expr="lte")
    in_house_on = filters.DateFilter(
        method="filter_in_house_on",
        help_text="Una estadía confirmada, en casa o finalizada cubre esa noche (checkin ≤ fecha < checkout)",
    )
    room_type = filters.UUIDFilter(method="filter_room_type")
    unassigned = filters.BooleanFilter(
        method="filter_unassigned", help_text="Estadías por llegar sin habitación"
    )
    balance_due = filters.BooleanFilter(method="filter_balance_due", help_text="Saldo pendiente > 0")
    booker = filters.UUIDFilter(field_name="booker_id")
    group = filters.UUIDFilter(field_name="group_id")
    q = filters.CharFilter(
        method="filter_q", help_text="Código, nombre, email o teléfono del huésped, id externo"
    )

    class Meta:
        model = Reservation
        fields: list = []

    def filter_in_house_on(self, queryset, name, value):
        stays = Stay.objects.filter(
            reservation=OuterRef("pk"),
            checkin_date__lte=value,
            checkout_date__gt=value,
            status__in=[BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN, BookingStatus.CHECKED_OUT],
        )
        return queryset.filter(Exists(stays))

    def filter_room_type(self, queryset, name, value):
        return queryset.filter(Exists(Stay.objects.filter(reservation=OuterRef("pk"), room_type_id=value)))

    def filter_unassigned(self, queryset, name, value):
        waiting = Exists(
            Stay.objects.filter(
                reservation=OuterRef("pk"),
                room__isnull=True,
                status__in=[BookingStatus.TENTATIVE, BookingStatus.CONFIRMED],
            )
        )
        return queryset.filter(waiting) if value else queryset.exclude(waiting)

    def filter_balance_due(self, queryset, name, value):
        return queryset.filter(balance__gt=0) if value else queryset.filter(balance__lte=0)

    def filter_q(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        queryset = queryset.annotate(
            booker_name=Concat("booker__first_name", Value(" "), "booker__last_name")
        )
        return queryset.filter(
            Q(code__icontains=value)
            | Q(booker_name__icontains=value)
            | Q(booker__email__icontains=value)
            | Q(booker__phone__icontains=value)
            | Q(external_id__icontains=value)
        )
