from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.messaging.api.views import (
    ConversationViewSet,
    LifecycleRuleViewSet,
    RecipientView,
    SendView,
    SimulatorContactsView,
    SimulatorInboundView,
    SimulatorThreadView,
    TemplateViewSet,
    VariablesView,
)

app_name = "messaging"

router = SimpleRouter()
router.register("conversations", ConversationViewSet, basename="conversation")
router.register("templates", TemplateViewSet, basename="template")
router.register("lifecycle-rules", LifecycleRuleViewSet, basename="lifecycle-rule")

urlpatterns = [
    path("variables/", VariablesView.as_view(), name="variables"),
    path("send/", SendView.as_view(), name="send"),
    path("recipient/", RecipientView.as_view(), name="recipient"),
    path("simulator/whatsapp/inbound/", SimulatorInboundView.as_view(), name="simulator-inbound"),
    path("simulator/whatsapp/thread/", SimulatorThreadView.as_view(), name="simulator-thread"),
    path("simulator/whatsapp/contacts/", SimulatorContactsView.as_view(), name="simulator-contacts"),
    *router.urls,
]
