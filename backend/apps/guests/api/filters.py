import re

from django.db.models import Q
from django_filters import rest_framework as filters
from rest_framework.filters import OrderingFilter

from apps.guests.models import Guest
from apps.guests.normalization import normalize_document
from apps.guests.selectors import has_stayed

MIN_PHONE_DIGITS = 3


class StableOrderingFilter(OrderingFilter):
    """`?ordering=` (or the default order) followed by the primary key. Many guests share a sort value (0
    stays, the same surname); without a tie-breaker the database may order them differently on each page,
    so a paginated list would repeat some guests and skip others."""

    def get_ordering(self, request, queryset, view):
        ordering = list(super().get_ordering(request, queryset, view) or queryset.model._meta.ordering)
        if not any(field.lstrip("-") in ("pk", "id") for field in ordering):
            ordering.append("pk")
        return ordering


def search_q(query: str) -> Q:
    """Every word must match a name (accents ignored), the email, the phone digits or the document; the
    whole query also matches a formatted phone or document ("300 111 2233", "1.020.304.050")."""
    words = query.split()
    if not words:
        return Q()
    every_word = Q()
    for word in words:
        match = (
            Q(first_name__unaccent__icontains=word)
            | Q(last_name__unaccent__icontains=word)
            | Q(email__icontains=word)
            | Q(document_number__icontains=normalize_document(word))
        )
        digits = re.sub(r"\D", "", word)
        if len(digits) >= MIN_PHONE_DIGITS:
            match |= Q(phone__contains=digits)
        every_word &= match
    all_digits = re.sub(r"\D", "", query)
    whole = Q(document_number__icontains=normalize_document(query))
    if len(all_digits) >= MIN_PHONE_DIGITS:
        whole |= Q(phone__contains=all_digits)
    return every_word | whole


class GuestFilter(filters.FilterSet):
    q = filters.CharFilter(method="filter_q", label="Nombre, email, teléfono o documento")
    is_vip = filters.BooleanFilter()
    blacklisted = filters.BooleanFilter()
    nationality = filters.CharFilter(method="filter_nationality", label="País ISO-2 (CO, US…)")
    tag = filters.CharFilter(method="filter_tag")
    has_stays = filters.BooleanFilter(method="filter_has_stays", label="Con estancias (check-in o check-out)")

    class Meta:
        model = Guest
        fields = ["is_vip", "blacklisted"]

    def filter_q(self, queryset, name, value):
        return queryset.filter(search_q(value)) if value.strip() else queryset

    def filter_nationality(self, queryset, name, value):
        return queryset.filter(nationality=value.strip().upper())

    def filter_tag(self, queryset, name, value):
        return queryset.filter(tags__contains=[value.strip()])

    def filter_has_stays(self, queryset, name, value):
        return queryset.filter(has_stayed()) if value else queryset.exclude(has_stayed())
