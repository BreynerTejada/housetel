from django.urls import path

from apps.messaging.api.webhooks import WhatsAppWebhookView

app_name = "messaging_public"

urlpatterns: list = [
    path("webhooks/whatsapp/", WhatsAppWebhookView.as_view(), name="whatsapp-webhook"),
]
