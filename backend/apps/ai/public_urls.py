from django.urls import path

from apps.ai.api.public_views import (
    ChatbotContactView,
    ChatbotView,
    PortalChatbotContactView,
    PortalChatbotView,
)

app_name = "ai_public"

urlpatterns: list = [
    path("chat/<slug:slug>/", ChatbotView.as_view(), name="chat"),
    path("chat/<slug:slug>/contact/", ChatbotContactView.as_view(), name="chat-contact"),
    path("portal-chat/<str:token>/", PortalChatbotView.as_view(), name="portal-chat"),
    path("portal-chat/<str:token>/contact/", PortalChatbotContactView.as_view(), name="portal-chat-contact"),
]
