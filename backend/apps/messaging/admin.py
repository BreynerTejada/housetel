from django.contrib import admin

from apps.messaging.models import Conversation, LifecycleDispatch, LifecycleRule, Message, MessageTemplate


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    """Overrides only: the system defaults live in code (`apps.messaging.defaults`)."""

    list_display = ["code", "channel", "language", "organization", "property", "is_active", "updated_at"]
    list_filter = ["channel", "language", "is_active"]
    list_select_related = ["organization", "property"]
    search_fields = ["code", "name", "subject"]
    raw_id_fields = ["organization", "property", "updated_by"]


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ["created_at", "direction", "channel", "status", "sender_label", "body"]
    readonly_fields = fields
    can_delete = False
    show_change_link = True


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ["__str__", "property", "channel", "status", "unread_count", "last_message_at"]
    list_filter = ["channel", "status"]
    list_select_related = ["property"]
    search_fields = ["contact_name", "external_thread_key", "reservation__code"]
    raw_id_fields = ["property", "guest", "reservation", "assigned_to"]
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["created_at", "conversation", "direction", "channel", "status", "template_code"]
    list_filter = ["direction", "channel", "status"]
    list_select_related = ["conversation"]
    search_fields = ["provider_message_id", "recipient", "template_code"]
    raw_id_fields = ["conversation", "reservation", "sent_by"]


@admin.register(LifecycleRule)
class LifecycleRuleAdmin(admin.ModelAdmin):
    list_display = ["property", "event", "enabled", "days_offset", "template_code", "send_after"]
    list_filter = ["event", "enabled"]
    list_select_related = ["property"]
    raw_id_fields = ["property"]


@admin.register(LifecycleDispatch)
class LifecycleDispatchAdmin(admin.ModelAdmin):
    list_display = ["reservation", "event", "status", "attempts", "created_at"]
    list_filter = ["event", "status"]
    list_select_related = ["reservation"]
    search_fields = ["reservation__code"]
    raw_id_fields = ["reservation"]
