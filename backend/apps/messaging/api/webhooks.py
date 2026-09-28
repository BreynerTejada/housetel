"""Public webhooks of messaging: `GET/POST /api/v1/public/messaging/webhooks/whatsapp/` (Meta Cloud API).

Meta sends every phone number of the app to one URL, so the hotel is found by the `phone_number_id` of each
change and the notification is only applied for hotels whose app secret validates `X-Hub-Signature-256`.
"""

import hmac
import json

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.core.integrations import get_secrets
from apps.core.models import IntegrationSetting
from apps.messaging.services import process_whatsapp_webhook
from apps.messaging.whatsapp import signature_is_valid


class WebhookThrottle(AnonRateThrottle):
    scope = "messaging_webhook"
    rate = "600/min"


def _real_settings():
    return IntegrationSetting.objects.filter(
        kind="whatsapp", mode="real", property__isnull=False
    ).select_related("property")


def _phone_number_ids(payload) -> set[str]:
    ids = set()
    entries = payload.get("entry") if isinstance(payload, dict) else None
    for entry in entries if isinstance(entries, list) else []:
        changes = entry.get("changes") if isinstance(entry, dict) else None
        for change in changes if isinstance(changes, list) else []:
            value = change.get("value") if isinstance(change, dict) else None
            metadata = value.get("metadata") if isinstance(value, dict) else None
            if isinstance(metadata, dict) and metadata.get("phone_number_id"):
                ids.add(str(metadata["phone_number_id"]))
    return ids


class WhatsAppWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [WebhookThrottle]

    @extend_schema(
        parameters=[
            OpenApiParameter("hub.mode", str),
            OpenApiParameter("hub.verify_token", str),
            OpenApiParameter("hub.challenge", str),
        ],
        responses={200: str, 403: None},
    )
    def get(self, request):
        """Meta's subscription check: answer the challenge when the verify token matches a hotel's."""
        token = request.query_params.get("hub.verify_token") or ""
        if request.query_params.get("hub.mode") == "subscribe" and token:
            for setting in _real_settings():
                expected = get_secrets(setting).get("verify_token") or ""
                if expected and hmac.compare_digest(expected.encode(), token.encode()):
                    return HttpResponse(
                        request.query_params.get("hub.challenge", ""), content_type="text/plain"
                    )
        return HttpResponse(status=403)

    @extend_schema(request=None, responses={200: dict, 400: None, 403: None})
    def post(self, request):
        """Incoming messages and delivery receipts, signed with the hotel's app secret."""
        raw = request.body
        try:
            payload = json.loads(raw)
        except ValueError:
            return Response({"detail": "Cuerpo inválido", "code": "invalid_body"}, status=400)
        signature = request.META.get("HTTP_X_HUB_SIGNATURE_256", "")
        ids = _phone_number_ids(payload)
        verified = {
            str(setting.config.get("phone_number_id")): setting.property
            for setting in _real_settings().filter(config__phone_number_id__in=list(ids))
            if signature_is_valid(raw, signature, get_secrets(setting).get("app_secret") or "")
        }
        if not verified:
            return Response({"detail": "Firma inválida", "code": "invalid_signature"}, status=403)
        counts = process_whatsapp_webhook(payload, verified)
        return Response({"received": True, **counts})
