"""Staff AI API (`/api/v1/ai/`, header `X-Property-Id`). Permissions (plan §D): ai.copilot (copilot),
ai.onboarding (assisted onboarding), ai.settings (settings, FAQ, usage, chatbot conversations) and
messaging.send (draft replies for the inbox)."""

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.ai.api import serializers as s
from apps.ai.copilot.actions import execute_action, reject_action
from apps.ai.copilot.agent import run_turn
from apps.ai.drafts import draft_reply
from apps.ai.features import ai_settings, require_feature
from apps.ai.models import ChatbotConversation, CopilotAction, CopilotMessage, CopilotSession, PropertyFAQ
from apps.ai.onboarding import apply_proposal, normalize_proposal, propose
from apps.ai.status import copilot_suggestions, provider_info, update_provider, usage_report
from apps.core import audit
from apps.core.alerts import resolve_alert
from apps.core.tenancy import PropertyScopedAPIView, PropertyScopedMixin, PropertyScopedViewSet

UUID_REGEX = "[0-9a-fA-F-]{36}"


class CopilotThrottle(UserRateThrottle):
    """Each message can make up to 5 model calls: keep a person from burning the provider's quota."""

    scope = "ai_copilot"
    rate = "30/min"


class CopilotSessionViewSet(
    PropertyScopedMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """The user's copilot conversations in the active property."""

    queryset = CopilotSession.objects.all()
    lookup_value_regex = UUID_REGEX
    required_permissions = {"*": "ai.copilot"}

    def get_queryset(self):
        queryset = super().get_queryset().filter(user=self.request.user)
        if self.action == "retrieve":
            queryset = queryset.prefetch_related(
                Prefetch("messages", queryset=CopilotMessage.objects.order_by("position")),
                Prefetch("actions", queryset=CopilotAction.objects.order_by("created_at")),
            )
        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return s.CopilotSessionDetailSerializer
        if self.action == "messages":
            return s.CopilotAskSerializer
        return s.CopilotSessionSerializer

    def get_throttles(self):
        return [CopilotThrottle()] if self.action == "messages" else super().get_throttles()

    def perform_create(self, serializer):
        serializer.save(property=self.request.property, user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        detail = s.CopilotSessionDetailSerializer(serializer.instance)
        return Response(detail.data, status=status.HTTP_201_CREATED)

    @extend_schema(request=s.CopilotAskSerializer, responses=s.CopilotTurnSerializer)
    @action(detail=True, methods=["post"])
    def messages(self, request, pk=None):
        """Ask the copilot: runs the agent loop and returns the new messages and the proposals to confirm."""
        session = self.get_object()
        require_feature(request.property, "copilot_enabled")
        serializer = s.CopilotAskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        turn = run_turn(
            session,
            serializer.validated_data["message"],
            user=request.user,
            lang=serializer.validated_data.get("language"),
        )
        session.refresh_from_db()
        payload = s.CopilotTurnSerializer({"session": session, **turn})
        return Response(payload.data)


class CopilotActionViewSet(PropertyScopedMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Proposals of the user's copilot sessions: confirm (runs the action) or reject."""

    queryset = CopilotAction.objects.select_related("session__property")
    serializer_class = s.CopilotActionSerializer
    property_field = "session__property"
    lookup_value_regex = UUID_REGEX
    required_permissions = {"*": "ai.copilot"}

    def get_queryset(self):
        return super().get_queryset().filter(session__user=self.request.user)

    @extend_schema(request=None, responses=s.CopilotActionSerializer)
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        """Run the proposal now (the permission it needs is checked again)."""
        return Response(s.CopilotActionSerializer(execute_action(self.get_object(), user=request.user)).data)

    @extend_schema(request=None, responses=s.CopilotActionSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return Response(s.CopilotActionSerializer(reject_action(self.get_object(), user=request.user)).data)


class OnboardingThrottle(UserRateThrottle):
    scope = "ai_onboarding"
    rate = "10/min"


class OnboardingProposeView(PropertyScopedAPIView):
    """`{description, website_url?}` → an editable proposal of room types, rooms, rates, policies and
    extras."""

    required_permissions = {"post": "ai.onboarding"}
    throttle_classes = [OnboardingThrottle]

    @extend_schema(request=s.OnboardingProposeSerializer, responses=s.OnboardingProposalSerializer)
    def post(self, request):
        serializer = s.OnboardingProposeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(propose(request.property, **serializer.validated_data))


class OnboardingNormalizeView(PropertyScopedAPIView):
    """`{proposal}` as edited on the review screen → the same proposal made consistent without calling the
    model: codes and room numbers unique in the hotel (rows sent with `room_numbers: []` get new numbers),
    types and ranges fixed, unknown amenities dropped. The review screen calls it when units change."""

    required_permissions = {"post": "ai.onboarding"}

    @extend_schema(request=s.OnboardingApplySerializer, responses=s.OnboardingNormalizedSerializer)
    def post(self, request):
        serializer = s.OnboardingApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        proposal, warnings = normalize_proposal(request.property, serializer.validated_data["proposal"])
        return Response({"proposal": proposal, "warnings": warnings})


class OnboardingApplyView(PropertyScopedAPIView):
    """`{proposal}` (as edited on the review screen) → creates everything in one transaction."""

    required_permissions = {"post": "ai.onboarding"}

    @extend_schema(request=s.OnboardingApplySerializer, responses={201: s.OnboardingSummarySerializer})
    def post(self, request):
        serializer = s.OnboardingApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        summary = apply_proposal(request.property, serializer.validated_data["proposal"], actor=request.user)
        return Response(summary, status=status.HTTP_201_CREATED)


class DraftThrottle(UserRateThrottle):
    scope = "ai_draft_reply"
    rate = "30/min"


class DraftReplyView(PropertyScopedAPIView):
    """Draft of a reply to a guest's message (inbox, C6). 404 when the hotel switched drafts off, so the inbox
    hides its button."""

    required_permissions = {"post": "messaging.send"}
    throttle_classes = [DraftThrottle]

    @extend_schema(request=s.DraftReplyRequestSerializer, responses=s.DraftReplySerializer)
    def post(self, request):
        from apps.bookings.models import Reservation

        if not ai_settings(request.property).draft_replies_enabled:
            raise NotFound("Los borradores con IA están desactivados en este hotel")
        serializer = s.DraftReplyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        reservation = None
        if data["reservation_code"]:
            reservation = (
                Reservation.objects.select_related("booker")
                .filter(property=request.property, code__iexact=data["reservation_code"].strip())
                .first()
            )
        return Response(
            draft_reply(
                request.property,
                guest_message=data["guest_message"],
                reservation=reservation,
                language=data["language"],
                tone=data["tone"],
            )
        )


# ---- settings, FAQ, usage, chatbot conversations ----------------------------------------------------------

FEATURE_FIELDS = ("copilot_enabled", "chatbot_enabled", "draft_replies_enabled", "chatbot_greeting")


def settings_payload(prop) -> dict:
    row = ai_settings(prop)
    return {
        "copilot_enabled": row.copilot_enabled,
        "chatbot_enabled": row.chatbot_enabled,
        "draft_replies_enabled": row.draft_replies_enabled,
        "chatbot_greeting": {"es": "", "en": "", **(row.chatbot_greeting or {})},
        "provider": provider_info(prop),
    }


class AISettingsView(PropertyScopedAPIView):
    """AI features of the hotel and its LLM provider (the provider's secrets live in the integrations
    page)."""

    required_permissions = {"get": "ai.settings", "patch": "ai.settings"}

    @extend_schema(responses=s.AISettingsSerializer)
    def get(self, request):
        return Response(settings_payload(request.property))

    @extend_schema(request=s.AISettingsUpdateSerializer, responses=s.AISettingsSerializer)
    def patch(self, request):
        serializer = s.AISettingsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            row = ai_settings(request.property)
            changes = {}
            for field in FEATURE_FIELDS:
                if field in data and getattr(row, field) != data[field]:
                    changes[field] = [getattr(row, field), data[field]]
                    setattr(row, field, data[field])
            if changes:
                row.save()
            changes.update(
                update_provider(
                    request.property,
                    mode=data.get("mode"),
                    provider=data.get("provider"),
                    model=data.get("model"),
                )
            )
            if changes:
                audit.record(
                    action="ai.settings_updated",
                    target=row,
                    property=request.property,
                    actor=request.user,
                    summary="Actualizó los ajustes de IA",
                    changes=changes,
                )
        return Response(settings_payload(request.property))


class PropertyFAQViewSet(PropertyScopedViewSet):
    """FAQ of the hotel's chatbot, per language (`?language=es|en`)."""

    queryset = PropertyFAQ.objects.all()
    serializer_class = s.PropertyFAQSerializer
    lookup_value_regex = UUID_REGEX
    required_permissions = {"*": "ai.settings"}

    def get_queryset(self):
        queryset = super().get_queryset()
        if language := self.request.query_params.get("language"):
            queryset = queryset.filter(language=language)
        return queryset.order_by("language", "sort", "created_at")

    @extend_schema(parameters=[OpenApiParameter("language", OpenApiTypes.STR, enum=["es", "en"])])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class UsageView(PropertyScopedAPIView):
    """LLM calls of the hotel in the last `days` (1–90): totals, by feature, provider and day, last errors."""

    required_permissions = {"get": "ai.settings"}

    @extend_schema(parameters=[OpenApiParameter("days", OpenApiTypes.INT)], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        try:
            days = min(max(int(request.query_params.get("days", 30)), 1), 90)
        except ValueError:
            days = 30
        return Response(usage_report(request.property, days=days))


class ChatbotConversationViewSet(
    PropertyScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Conversations of the public chatbot (`?handoff=1` the ones that asked for a person)."""

    queryset = ChatbotConversation.objects.select_related("reservation__booker")
    lookup_value_regex = UUID_REGEX
    required_permissions = {"*": "ai.settings"}

    def get_serializer_class(self):
        return (
            s.ChatbotConversationSerializer
            if self.action == "list"
            else s.ChatbotConversationDetailSerializer
        )

    def get_queryset(self):
        queryset = super().get_queryset()
        handoff = self.request.query_params.get("handoff")
        if handoff in ("1", "true"):
            queryset = queryset.filter(handoff_requested=True)
        elif handoff in ("0", "false"):
            queryset = queryset.filter(handoff_requested=False)
        if self.request.query_params.get("open") in ("1", "true"):
            queryset = queryset.filter(handoff_requested=True, handoff_resolved_at__isnull=True)
        return queryset.order_by("-last_message_at", "-created_at")

    @extend_schema(
        parameters=[
            OpenApiParameter("handoff", OpenApiTypes.BOOL),
            OpenApiParameter("open", OpenApiTypes.BOOL),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=None, responses=s.ChatbotConversationDetailSerializer)
    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """The team took care of the guest: closes the hand-off and its alert."""
        conversation = self.get_object()
        if conversation.handoff_resolved_at is None:
            conversation.handoff_resolved_at = timezone.now()
            conversation.save(update_fields=["handoff_resolved_at", "updated_at"])
        resolve_alert(request.property, f"ai:chatbot_handoff:{conversation.pk}", actor=request.user)
        return Response(s.ChatbotConversationDetailSerializer(conversation).data)


class CopilotStatusView(PropertyScopedAPIView):
    """For the copilot panel: switched on?, real or simulated, and quick suggestions for the user's role."""

    required_permissions = {"get": "ai.copilot"}

    @extend_schema(responses=s.CopilotStatusSerializer)
    def get(self, request):
        info = provider_info(request.property)
        lang = request.query_params.get("language") or getattr(request.user, "language", "es")
        return Response(
            {
                "enabled": ai_settings(request.property).copilot_enabled,
                "effective": info["effective"],
                "provider_label": info["effective_label"],
                "suggestions": copilot_suggestions(
                    request.user, request.property, lang if lang in ("es", "en") else "es"
                ),
            }
        )
