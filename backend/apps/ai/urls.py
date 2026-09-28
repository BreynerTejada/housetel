from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.ai.api.views import (
    AISettingsView,
    ChatbotConversationViewSet,
    CopilotActionViewSet,
    CopilotSessionViewSet,
    CopilotStatusView,
    DraftReplyView,
    OnboardingApplyView,
    OnboardingNormalizeView,
    OnboardingProposeView,
    PropertyFAQViewSet,
    UsageView,
)

app_name = "ai"

router = SimpleRouter()
router.register("copilot/sessions", CopilotSessionViewSet, basename="copilot-session")
router.register("copilot/actions", CopilotActionViewSet, basename="copilot-action")
router.register("faqs", PropertyFAQViewSet, basename="faq")
router.register("chatbot-conversations", ChatbotConversationViewSet, basename="chatbot-conversation")

urlpatterns: list = [
    path("settings/", AISettingsView.as_view(), name="settings"),
    path("usage/", UsageView.as_view(), name="usage"),
    path("copilot/status/", CopilotStatusView.as_view(), name="copilot-status"),
    path("draft-reply/", DraftReplyView.as_view(), name="draft-reply"),
    path("onboarding/propose/", OnboardingProposeView.as_view(), name="onboarding-propose"),
    path("onboarding/normalize/", OnboardingNormalizeView.as_view(), name="onboarding-normalize"),
    path("onboarding/apply/", OnboardingApplyView.as_view(), name="onboarding-apply"),
    *router.urls,
]
