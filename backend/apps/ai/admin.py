from django.contrib import admin

from apps.ai.models import (
    AISettings,
    AIUsage,
    ChatbotConversation,
    CopilotAction,
    CopilotMessage,
    CopilotSession,
    PropertyFAQ,
)


@admin.register(AISettings)
class AISettingsAdmin(admin.ModelAdmin):
    list_display = ["property", "copilot_enabled", "chatbot_enabled", "draft_replies_enabled"]


@admin.register(AIUsage)
class AIUsageAdmin(admin.ModelAdmin):
    list_display = ["created_at", "property", "feature", "provider", "model", "success", "latency_ms"]
    list_filter = ["provider", "feature", "success"]


class CopilotMessageInline(admin.TabularInline):
    model = CopilotMessage
    extra = 0
    fields = ["position", "role", "content", "name", "provider", "simulated"]
    readonly_fields = fields


@admin.register(CopilotSession)
class CopilotSessionAdmin(admin.ModelAdmin):
    list_display = ["title", "property", "user", "last_message_at"]
    inlines = [CopilotMessageInline]


@admin.register(CopilotAction)
class CopilotActionAdmin(admin.ModelAdmin):
    list_display = ["created_at", "action_code", "status", "summary"]
    list_filter = ["action_code", "status"]


@admin.register(PropertyFAQ)
class PropertyFAQAdmin(admin.ModelAdmin):
    list_display = ["question", "property", "language", "sort", "is_active"]
    list_filter = ["language", "is_active"]


@admin.register(ChatbotConversation)
class ChatbotConversationAdmin(admin.ModelAdmin):
    list_display = ["session_id", "property", "language", "handoff_requested", "last_message_at"]
    list_filter = ["handoff_requested", "language"]
