"""Staff API of the guest portal: `/api/v1/guestportal/…` (session + `X-Property-Id`).

`guestportal.view` reads (check-ins, data, signature, link, requests, settings); `guestportal.manage` sends
links, decides requests and edits the settings."""

from datetime import date

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.bookings.models import Reservation
from apps.core.errors import DomainError, NotFoundError
from apps.core.tenancy import PropertyScopedAPIView, PropertyScopedMixin
from apps.guestportal.api import serializers as s
from apps.guestportal.models import OnlineCheckin, ServiceRequest
from apps.guestportal.services import requests as requests_service
from apps.guestportal.services import staff
from apps.guestportal.services.access import portal_settings, terms_of
from apps.rates.models import Extra


def _reservation(request, pk) -> Reservation:
    return get_object_or_404(
        Reservation.objects.select_related("property__organization", "booker"),
        pk=pk,
        property=request.property,
    )


class ArrivalsCheckinsView(PropertyScopedAPIView):
    """`GET checkins/?date=YYYY-MM-DD` — arrivals of the day (default: business date) and their check-in."""

    required_permissions = {"get": "guestportal.view"}

    @extend_schema(
        parameters=[OpenApiParameter("date", OpenApiTypes.DATE, required=False)],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        raw = request.query_params.get("date")
        try:
            day = date.fromisoformat(raw) if raw else request.property.business_date
        except ValueError:
            raise DomainError("Usa el formato AAAA-MM-DD", code="validation_error",
                              fields={"date": ["Fecha inválida"]}) from None  # fmt: skip
        return Response(staff.arrivals_checkins(request.property, day))


class ReservationCheckinView(PropertyScopedAPIView):
    """`GET reservations/{id}/checkin/` — data, documents (private links), signature link, missing items."""

    required_permissions = {"get": "guestportal.view"}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, pk):
        return Response(staff.staff_checkin_detail(_reservation(request, pk)))


class ReservationSignatureView(PropertyScopedAPIView):
    """`GET reservations/{id}/checkin/signature/` — the signature PNG (private, never cached)."""

    required_permissions = {"get": "guestportal.view"}

    @extend_schema(responses={(200, "image/png"): OpenApiTypes.BINARY})
    def get(self, request, pk):
        reservation = _reservation(request, pk)
        checkin = OnlineCheckin.objects.filter(reservation=reservation).first()
        if checkin is None or not checkin.signature:
            raise NotFoundError("Esta reserva no tiene firma")
        response = FileResponse(checkin.signature.open("rb"), content_type="image/png")
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ReservationLinkView(PropertyScopedAPIView):
    """`GET reservations/{id}/link/` — `{url, checkin_url, qr_png}` (QR as a PNG data URL)."""

    required_permissions = {"get": "guestportal.view"}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, pk):
        return Response(staff.portal_link(_reservation(request, pk)))


class SendLinkView(PropertyScopedAPIView):
    """`POST reservations/{id}/send-link/` `{send_via?: ["email", "whatsapp"]}` — `checkin_invitation`
    (same payload as finance's payment link; email by default)."""

    required_permissions = {"post": "guestportal.manage"}

    @extend_schema(request=s.SendLinkSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        reservation = _reservation(request, pk)
        serializer = s.SendLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        channels = serializer.validated_data.get("send_via") or ["email"]
        return Response(staff.send_checkin_link(reservation, channels=channels, actor=request.user))


class ServiceRequestViewSet(PropertyScopedMixin, viewsets.GenericViewSet):
    """`GET service-requests/?status=&kind=&reservation=` and `POST service-requests/{id}/approve|reject|
    complete/`."""

    property_field = "reservation__property"
    queryset = ServiceRequest.objects.select_related("reservation__booker", "reservation__property", "extra")
    required_permissions = {"list": "guestportal.view", "*": "guestportal.manage"}

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if params.get("status"):
            queryset = queryset.filter(status__in=params.getlist("status"))
        if params.get("kind"):
            queryset = queryset.filter(kind__in=params.getlist("kind"))
        if params.get("reservation"):
            queryset = queryset.filter(reservation_id=params["reservation"])
        return queryset.order_by("-created_at")

    @staticmethod
    def payload(request) -> dict:
        reservation = request.reservation
        return {
            **requests_service.request_payload(request),
            "reservation": {
                "id": str(reservation.pk),
                "code": reservation.code,
                "guest_name": reservation.booker.full_name,
                "checkin_date": reservation.checkin_date.isoformat(),
                "checkout_date": reservation.checkout_date.isoformat(),
                "status": reservation.status,
            },
        }

    @extend_schema(
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR, many=True),
            OpenApiParameter("kind", OpenApiTypes.STR, many=True),
            OpenApiParameter("reservation", OpenApiTypes.UUID),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response([self.payload(item) for item in page])

    @extend_schema(request=s.ApproveRequestSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        item = self.get_object()
        extra = None
        if request.data.get("extra_id"):
            extra = Extra.objects.filter(
                pk=request.data["extra_id"], property=request.property, is_active=True
            ).first()
            if extra is None:
                raise DomainError("Ese extra no existe en este hotel", code="invalid_extra")
        updated = requests_service.approve_request(
            item,
            actor=request.user,
            extra=extra,
            quantity=request.data.get("quantity"),
            note=request.data.get("note") or "",
        )
        return Response(self.payload(updated))

    @extend_schema(request=s.RejectRequestSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        updated = requests_service.reject_request(
            self.get_object(), actor=request.user, reason=request.data.get("reason") or ""
        )
        return Response(self.payload(updated))

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return Response(
            self.payload(requests_service.complete_request(self.get_object(), actor=request.user))
        )


class SettingsView(PropertyScopedAPIView):
    """`GET/PATCH settings/` — check-in window, requirements, self-service rules and terms (ES/EN)."""

    required_permissions = {"get": "guestportal.view", "patch": "guestportal.manage"}

    @staticmethod
    def payload(settings) -> dict:
        data = s.GuestPortalSettingsSerializer(settings).data
        data["terms"] = terms_of(settings)
        return data

    @extend_schema(responses=s.GuestPortalSettingsSerializer)
    def get(self, request):
        return Response(self.payload(portal_settings(request.property)))

    @extend_schema(request=s.GuestPortalSettingsSerializer, responses=s.GuestPortalSettingsSerializer)
    def patch(self, request):
        from apps.core import audit

        settings = portal_settings(request.property)
        serializer = s.GuestPortalSettingsSerializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        before = s.GuestPortalSettingsSerializer(settings).data
        serializer.save()
        changes = audit.diff(dict(before), dict(s.GuestPortalSettingsSerializer(settings).data))
        if changes:
            audit.record(
                action="guestportal.settings_updated",
                target=settings,
                summary="Actualizó la configuración del portal del huésped",
                actor=request.user,
                property=request.property,
                changes=changes,
            )
        return Response(self.payload(settings))
