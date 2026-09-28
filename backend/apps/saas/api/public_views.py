"""Public SaaS API (`/api/v1/public/saas/…`): plans, signup and the platform Wompi webhook."""

import logging

from django.conf import settings
from django.contrib.auth import login
from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.accounts.api.serializers import MeSerializer
from apps.core.api.authentication import enforce_csrf
from apps.finance import wompi
from apps.saas.api.serializers import PublicPlanSerializer, SignupSerializer
from apps.saas.models import PlatformInvoice
from apps.saas.services import billing
from apps.saas.services.plans import active_plans, ensure_default_plans
from apps.saas.services.signup import signup

logger = logging.getLogger("housetel.saas")


class SignupThrottle(AnonRateThrottle):
    scope = "saas_signup"
    rate = "30/hour"


class PublicPlansView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(responses=PublicPlanSerializer(many=True), auth=[])
    def get(self, request):
        ensure_default_plans()
        return Response(PublicPlanSerializer(active_plans(), many=True).data)


class SignupView(APIView):
    """`POST signup/` → organization in trial + property + owner + trial subscription; starts the owner's
    session and answers `{redirect: "/app/getting-started", me}` (201). CSRF is required, like the login."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [SignupThrottle]

    @extend_schema(request=SignupSerializer, responses={201: OpenApiTypes.OBJECT}, auth=[])
    def post(self, request):
        enforce_csrf(request)
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        language = data.get("language") or (
            "en" if (request.headers.get("Accept-Language") or "").lower().startswith("en") else "es"
        )
        result = signup(data, language=language)
        login(request._request, result.user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(
            {
                "redirect": "/app/getting-started",
                "organization": {"id": str(result.organization.pk), "slug": result.organization.slug},
                "property": {"id": str(result.property.pk), "slug": result.property.slug},
                "me": MeSerializer(result.user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class PlatformWompiWebhookView(APIView):
    """`POST webhooks/wompi/`: events of the platform's Wompi account. The checksum is verified with
    `WOMPI_PLATFORM_EVENTS_SECRET`; the invoice is then verified actively with the API (the body is never
    trusted)."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT, auth=[])
    def post(self, request):
        event = request.data if isinstance(request.data, dict) else {}
        secret = getattr(settings, "WOMPI_PLATFORM_EVENTS_SECRET", "")
        if not wompi.verify_event(event, secret, request.headers.get("X-Event-Checksum")):
            return Response({"detail": "Firma inválida", "code": "invalid_signature"}, status=400)
        transaction_data = (
            (event.get("data") or {}).get("transaction") if isinstance(event.get("data"), dict) else None
        )
        reference = str((transaction_data or {}).get("reference") or "")
        number = "-".join(reference.split("-")[:3])  # HTP-2026-00012-P7KQ → HTP-2026-00012
        invoice = PlatformInvoice.objects.filter(number=number).select_related("organization").first()
        if invoice is None:
            return Response({"received": True, "ignored": True})
        try:
            with transaction.atomic():
                billing.verify_invoice_payment(invoice)
        except Exception:  # noqa: BLE001 - Wompi must get a 200; the billing cycle verifies again
            logger.exception("Could not verify platform invoice %s from a webhook", invoice.pk)
        return Response({"received": True})
