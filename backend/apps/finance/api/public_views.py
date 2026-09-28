"""Public finance API (`/api/v1/public/finance/`, no session): the simulated gateway, status polling for
return pages and the Wompi events webhook."""

import logging
import re

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.finance import services
from apps.finance.api import serializers as s
from apps.finance.cash import money_str
from apps.finance.models import PaymentIntent
from apps.finance.providers import redirect_url_for

logger = logging.getLogger("housetel.finance")

try:  # pilot plan P1: 404 when simulations are off (production without HOUSETEL_ALLOW_SIMULATIONS=1)
    from apps.core.runtime import require_simulations
except ImportError:  # P1's `apps.core.runtime` not merged yet: behave as today (development)

    def require_simulations(view_func):
        return view_func


TRANSACTION_ID = re.compile(r"[A-Za-z0-9_-]{1,120}")
RECHECK_SECONDS = 2  # status polling hits the provider at most every 2 s per link


class PublicReadThrottle(AnonRateThrottle):
    scope = "finance_public_read"
    rate = "120/min"


class SimDecisionThrottle(AnonRateThrottle):
    scope = "finance_sim_decision"
    rate = "30/min"


class WebhookThrottle(AnonRateThrottle):
    scope = "finance_webhook"
    rate = "600/min"


class PublicView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [PublicReadThrottle]


def _intent_or_404(reference, **filters) -> PaymentIntent:
    queryset = PaymentIntent.objects.select_related("property", "folio__reservation__booker", "folio__guest")
    return get_object_or_404(queryset, reference=reference, **filters)


def _simulated_intent_or_404(reference) -> PaymentIntent:
    """A simulated link of a hotel that still works in simulated mode (after going live they are gone)."""
    intent = _intent_or_404(reference, mode=PaymentIntent.Mode.SIMULATED)
    if not services.simulated_payments_enabled(intent.property):
        raise Http404("Link de pago no encontrado")
    return intent


def _display_status(intent) -> str:
    return PaymentIntent.Status.EXPIRED if services.intent_is_stale(intent) else intent.status


def sim_payload(intent) -> dict:
    prop = intent.property
    branding = prop.branding or {}
    reservation = intent.folio.reservation if intent.folio.reservation_id else None
    guest = services.guest_of(intent.folio)
    return {
        "reference": intent.reference,
        "amount": money_str(intent.amount),
        "currency": intent.currency,
        "status": _display_status(intent),
        "mode": intent.mode,
        "method": intent.method,
        "expires_at": intent.expires_at.isoformat() if intent.expires_at else None,
        "created_at": intent.created_at.isoformat(),
        "return_url": redirect_url_for(intent),
        "property": {
            "name": prop.name,
            "slug": prop.slug,
            "city": prop.city,
            "primary_color": branding.get("primary_color", ""),
            "logo": branding.get("logo", ""),
        },
        "reservation_code": reservation.code if reservation else None,
        "payer_first_name": guest.first_name if guest else None,
    }


@require_simulations
class SimIntentView(PublicView):
    """`GET sim/intents/<reference>/` — what the simulated gateway shows (only simulated links). 404 when the
    runtime has simulations off (`core.runtime.require_simulations`, production)."""

    @extend_schema(responses=s.SimIntentSerializer, auth=[])
    def get(self, request, reference):
        return Response(sim_payload(_simulated_intent_or_404(reference)))


@require_simulations
class SimDecisionView(PublicView):
    """`POST sim/intents/<reference>/decide/` `{outcome, method}` — the guest's decision (simulated only). 404
    when the runtime has simulations off (`core.runtime.require_simulations`)."""

    throttle_classes = [SimDecisionThrottle]

    @extend_schema(request=s.SimDecisionSerializer, responses=s.SimIntentSerializer, auth=[])
    def post(self, request, reference):
        intent = _simulated_intent_or_404(reference)
        data = s.SimDecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.decide_simulated_intent(intent, **data.validated_data)
        return Response(sim_payload(_intent_or_404(reference)))


class IntentStatusView(PublicView):
    """`GET intents/<reference>/status/?id=<provider transaction id>` — verifies with the provider (at most
    every few seconds) and answers whether the link is paid. Used by the pages the gateway returns to."""

    @extend_schema(
        parameters=[OpenApiParameter("id", OpenApiTypes.STR, description="Id de la transacción (redirect)")],
        responses=s.IntentStatusSerializer,
        auth=[],
    )
    def get(self, request, reference):
        intent = _intent_or_404(reference)
        transaction_id = (request.query_params.get("id") or "").strip()
        if (
            transaction_id
            and intent.mode == PaymentIntent.Mode.REAL
            and not intent.provider_transaction_id
            and TRANSACTION_ID.fullmatch(transaction_id)
        ):
            PaymentIntent.objects.filter(pk=intent.pk, provider_transaction_id="").update(
                provider_transaction_id=transaction_id
            )
        recently = (
            intent.last_checked_at
            and (timezone.now() - intent.last_checked_at).total_seconds() < RECHECK_SECONDS
        )
        if (
            intent.status not in (PaymentIntent.Status.APPROVED, PaymentIntent.Status.EXPIRED)
            and not recently
        ):
            services.sync_payment_intent(intent)
        intent = _intent_or_404(reference)
        reservation = intent.folio.reservation if intent.folio.reservation_id else None
        return Response(
            {
                "reference": intent.reference,
                "status": _display_status(intent),
                "paid": intent.status == PaymentIntent.Status.APPROVED,
                "amount": money_str(intent.amount),
                "currency": intent.currency,
                "method": intent.method,
                "reservation_code": reservation.code if reservation else None,
                "property_slug": intent.property.slug,
            }
        )


def _event_transaction(event) -> dict:
    """`data.transaction` of a Wompi event, or {} for anything else (malformed bodies are acknowledged)."""
    data = event.get("data") if isinstance(event, dict) else None
    transaction = data.get("transaction") if isinstance(data, dict) else None
    return transaction if isinstance(transaction, dict) else {}


class WompiWebhookView(PublicView):
    """`POST webhooks/wompi/` — Wompi events. Signed `transaction.updated` events of our links trigger an
    active verification (`sync_payment_intent`); everything else is acknowledged with 200 so Wompi does not
    retry. A bad checksum answers 400 `invalid_signature`."""

    throttle_classes = [WebhookThrottle]

    @extend_schema(request=OpenApiTypes.OBJECT, responses=s.WebhookAckSerializer, auth=[])
    def post(self, request):
        reference = str(_event_transaction(request.data).get("reference") or "")
        intent = (
            PaymentIntent.objects.select_related("property").filter(reference=reference, mode="real").first()
            if reference
            else None
        )
        if intent is None:
            return Response({"received": True, "ignored": True})
        parsed = services.provider_for_intent(intent).parse_webhook(request)
        if parsed is None:
            logger.warning("Wompi event with an invalid checksum for %s", reference)
            return Response(
                {"detail": "La firma del evento no es válida", "code": "invalid_signature"}, status=400
            )
        if parsed["event"] != "transaction.updated":
            return Response({"received": True, "ignored": True})
        if parsed["transaction_id"] and not intent.provider_transaction_id:
            PaymentIntent.objects.filter(pk=intent.pk, provider_transaction_id="").update(
                provider_transaction_id=parsed["transaction_id"][:120]
            )
        synced = services.sync_payment_intent(intent)
        return Response({"received": True, "ignored": False, "status": synced.status})
