from django.urls import path

from apps.finance.api.public_views import IntentStatusView, SimDecisionView, SimIntentView, WompiWebhookView

app_name = "finance_public"

urlpatterns = [
    path("sim/intents/<str:reference>/", SimIntentView.as_view(), name="sim-intent"),
    path("sim/intents/<str:reference>/decide/", SimDecisionView.as_view(), name="sim-decide"),
    path("intents/<str:reference>/status/", IntentStatusView.as_view(), name="intent-status"),
    path("webhooks/wompi/", WompiWebhookView.as_view(), name="webhook-wompi"),
]
