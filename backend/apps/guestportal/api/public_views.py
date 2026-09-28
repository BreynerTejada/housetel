"""Public guest portal API: `/api/v1/public/guestportal/<token>/…` (no session; the signed token is the key).

Every view resolves the token first (`InvalidLink` → 404 `invalid_link`), answers with `Cache-Control:
no-store` and never exposes staff-only data. Writes run through the owning apps' contracts."""

import time
from datetime import datetime

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.core.errors import DomainError
from apps.guestportal.api import serializers as s
from apps.guestportal.services import checkin, manage, payments
from apps.guestportal.services import requests as requests_service
from apps.guestportal.services.access import portal_reservation
from apps.guestportal.services.summary import portal_summary


class _PortalThrottle(AnonRateThrottle):
    def timer(
        self,
    ):  # read the clock at call time (a class attribute bound to time.time breaks under freezegun)
        return time.time()


class PortalReadThrottle(_PortalThrottle):
    scope = "guestportal_read"
    rate = "120/min"


class PortalWriteThrottle(_PortalThrottle):
    scope = "guestportal_write"
    rate = "40/min"


class PortalView(APIView):
    """Base of the portal endpoints: resolves `self.reservation` from the token before the handler runs."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [PortalReadThrottle]
    write_throttle_classes = [PortalWriteThrottle]

    def get_throttles(self):
        classes = (
            self.throttle_classes if self.request.method in ("GET", "HEAD") else self.write_throttle_classes
        )
        return [throttle() for throttle in classes]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.reservation = portal_reservation(kwargs.get("token", ""))

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store, private"
        response["X-Robots-Tag"] = "noindex, nofollow"
        response["Referrer-Policy"] = "no-referrer"
        return response

    def meta(self) -> dict:
        """Evidence kept with the online check-in (the latest step's origin)."""
        return {
            "ip": self.request.META.get("REMOTE_ADDR") or None,
            "user_agent": (self.request.META.get("HTTP_USER_AGENT") or "")[:300],
        }

    def summary(self) -> Response:
        return Response(portal_summary(self.reservation))


class PortalSummaryView(PortalView):
    """`GET <token>/` — the booking, its stays and guests, balance, check-in status, extras, requests and what
    the guest may still change or cancel."""

    @extend_schema(responses=OpenApiTypes.OBJECT, auth=[])
    def get(self, request, token):
        return self.summary()


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on", "si", "sí")


def _parse_time(value, *, field="eta"):
    """`"HH:MM"` → time; blank → None; anything else → validation error on `field`."""
    if value in (None, ""):
        return None
    try:
        return datetime.strptime(str(value).strip()[:5], "%H:%M").time()
    except ValueError:
        raise DomainError("Usa el formato HH:MM", code="validation_error",
                          fields={field: ["Usa el formato HH:MM"]}) from None  # fmt: skip


class CheckinView(PortalView):
    """`GET <token>/checkin/` — slots, data, documents, missing items and settings of the online check-in.
    `POST <token>/checkin/` `{step: guests|documents|arrival|signature, ...}` — saves one step (documents:
    multipart `{step, guest_id, kind, file}` uploads one file; without file it confirms the step)."""

    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @extend_schema(responses=OpenApiTypes.OBJECT, auth=[])
    def get(self, request, token):
        return Response(checkin.checkin_payload(self.reservation))

    @extend_schema(request=s.CheckinStepSerializer, responses=OpenApiTypes.OBJECT, auth=[])
    def post(self, request, token):
        step = request.data.get("step")
        reservation, meta = self.reservation, self.meta()
        if step == "guests":
            checkin.save_guests(reservation, request.data.get("guests"), meta=meta)
        elif step == "documents" and request.FILES.get("file") is not None:
            document = checkin.save_document(
                reservation,
                guest_id=request.data.get("guest_id"),
                kind=request.data.get("kind") or "",
                file=request.FILES["file"],
                meta=meta,
            )
            payload = {
                "document": {
                    "id": str(document.pk),
                    "kind": document.kind,
                    "guest_id": str(document.guest_id),
                },
                "checkin": checkin.checkin_payload(reservation),
            }
            return Response(payload, status=status.HTTP_201_CREATED)
        elif step == "documents":
            checkin.confirm_documents(reservation, meta=meta)
        elif step == "arrival":
            checkin.save_arrival(reservation, eta=_parse_time(request.data.get("eta")), meta=meta)
        elif step == "signature":
            checkin.save_signature(
                reservation,
                signature=request.data.get("signature") or "",
                accept_terms=_truthy(request.data.get("accept_terms")),
                marketing_consent=_truthy(request.data.get("marketing_consent")),
                meta=meta,
            )
        else:
            raise DomainError("Paso inválido", code="validation_error",
                              fields={"step": ["Usa guests, documents, arrival o signature"]})  # fmt: skip
        return Response(checkin.checkin_payload(reservation))


class CheckinCompleteView(PortalView):
    """`POST <token>/checkin/complete/` — validates every requirement; `guest_checked_in_online` once."""

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT, auth=[])
    def post(self, request, token):
        checkin.complete_checkin(self.reservation, meta=self.meta())
        return Response(checkin.checkin_payload(self.reservation))


class PayView(PortalView):
    """`POST <token>/pay/` `{amount?}` — payment link for the balance (or part of it); returns `checkout_url`
    (the gateway sends the guest back to `/g/<token>?paid=1&payment_ref=<reference>`)."""

    @extend_schema(request=s.PaySerializer, responses=OpenApiTypes.OBJECT, auth=[])
    def post(self, request, token):
        intent = payments.create_payment(self.reservation, amount=request.data.get("amount"))
        return Response(payments.intent_payload(intent), status=status.HTTP_201_CREATED)


class ExtrasView(PortalView):
    """`GET <token>/extras/` — extras sold online with this booking's price."""

    @extend_schema(responses=OpenApiTypes.OBJECT, auth=[])
    def get(self, request, token):
        return Response(requests_service.portal_extras(self.reservation))


class RequestsView(PortalView):
    """`POST <token>/requests/` `{kind, extra_id?, quantity?, requested_time?, notes?}` — buy an extra or ask
    for a late check-out, early check-in, transfer or anything else."""

    @extend_schema(request=s.ServiceRequestCreateSerializer, responses=OpenApiTypes.OBJECT, auth=[])
    def post(self, request, token):
        created = requests_service.create_request(
            self.reservation,
            kind=request.data.get("kind") or "",
            extra_id=request.data.get("extra_id"),
            quantity=request.data.get("quantity"),
            requested_time=_parse_time(request.data.get("requested_time"), field="requested_time"),
            notes=request.data.get("notes") or "",
        )
        payload = {"request": requests_service.request_payload(created), **portal_summary(self.reservation)}
        return Response(payload, status=status.HTTP_201_CREATED)


class CancelView(PortalView):
    """`POST <token>/cancel/` `{confirm: true, reason?}` — cancels within the policy (the penalty shown in the
    summary's `cancellation` block is charged)."""

    @extend_schema(request=s.CancelSerializer, responses=OpenApiTypes.OBJECT, auth=[])
    def post(self, request, token):
        manage.cancel_from_portal(
            self.reservation,
            confirm=request.data.get("confirm") is True,
            reason=request.data.get("reason") or "",
        )
        return Response(portal_summary(portal_reservation(token)))


class ModifyPreviewView(PortalView):
    """`POST <token>/modify-preview/` `{checkin, checkout}` — new total and balance, nothing saved."""

    @extend_schema(request=s.ModifySerializer, responses=OpenApiTypes.OBJECT, auth=[])
    def post(self, request, token):
        return Response(
            manage.preview_modification(
                self.reservation, checkin=request.data.get("checkin"), checkout=request.data.get("checkout")
            )
        )


class ModifyView(PortalView):
    """`POST <token>/modify/` `{checkin, checkout}` — moves the stay (repriced) → `{total, balance, currency,
    summary}` (`summary` = the refreshed portal summary)."""

    @extend_schema(request=s.ModifySerializer, responses=OpenApiTypes.OBJECT, auth=[])
    def post(self, request, token):
        result = manage.modify_from_portal(
            self.reservation, checkin=request.data.get("checkin"), checkout=request.data.get("checkout")
        )
        return Response({**result, "summary": portal_summary(portal_reservation(token))})
