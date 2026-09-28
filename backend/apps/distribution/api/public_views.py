"""Public distribution API (`/api/v1/public/distribution/`, no session): the iCal export that listing sites
(Airbnb, VRBO, Booking.com…) poll. The secret token in the URL is the only credential."""

from django.http import Http404, HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.distribution.services.ical import export_calendar, mapping_for_token


class IcalExportThrottle(AnonRateThrottle):
    scope = "distribution_ical_export"
    rate = "120/min"


class IcalExportView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [IcalExportThrottle]

    @extend_schema(
        summary="Calendario iCal exportado (público)",
        responses={
            (200, "text/calendar"): OpenApiResponse(OpenApiTypes.STR, description="VCALENDAR"),
            404: OpenApiResponse(description="Token desconocido"),
        },
        auth=[],
    )
    def get(self, request, token: str):
        mapping = mapping_for_token(token)
        if mapping is None:
            raise Http404("Calendario no encontrado")
        response = HttpResponse(export_calendar(mapping), content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = f'inline; filename="housetel-{mapping.room_type.code.lower()}.ics"'
        response["Cache-Control"] = "private, max-age=300"
        return response
