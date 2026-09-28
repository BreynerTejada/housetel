"""Public AI API (`/api/v1/public/ai/`, no session): the hotel chatbot of the public pages and of the guest
portal. A hotel whose chatbot is switched off (or inactive) answers 404, so the widget stays hidden."""

from django.http import Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.ai import chatbot
from apps.ai.api import serializers as s


class ChatReadThrottle(AnonRateThrottle):
    scope = "ai_chatbot_read"
    rate = "120/min"


class ChatWriteThrottle(AnonRateThrottle):
    scope = "ai_chatbot"
    rate = "30/min"


class PublicView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get_throttles(self):
        return [ChatReadThrottle()] if self.request.method == "GET" else [ChatWriteThrottle()]

    def target(self, **kwargs):
        """(property, reservation) of the chat, or 404."""
        raise NotImplementedError

    def reply_payload(self, conversation, reply) -> dict:
        entry = conversation.messages[-1]
        return {
            "session_id": conversation.session_id,
            "reply": {
                "role": "assistant",
                "content": reply.content,
                "cards": reply.cards,
                "at": entry.get("at"),
            },
            "handoff": chatbot.handoff_state(conversation),
        }


class ChatbotBaseView(PublicView):
    @extend_schema(
        parameters=[
            OpenApiParameter(
                "session_id", OpenApiTypes.STR, description="Sesión del widget (continúa el chat)"
            ),
            OpenApiParameter("language", OpenApiTypes.STR, enum=["es", "en"]),
        ],
        responses=s.ChatConfigSerializer,
    )
    def get(self, request, **kwargs):
        """Widget configuration (greeting, suggestions) and, with `session_id`, the conversation so far."""
        prop, reservation = self.target(**kwargs)
        lang = request.query_params.get("language") or "es"
        payload = {**chatbot.widget_config(prop, lang), "session_id": None, "messages": [], "handoff": None}
        session_id = request.query_params.get("session_id") or ""
        if chatbot.SESSION_ID.match(session_id):
            conversation = chatbot.get_conversation(prop, session_id)
            if conversation is not None:
                payload.update(
                    session_id=conversation.session_id,
                    messages=chatbot.public_messages(conversation),
                    handoff=chatbot.handoff_state(conversation),
                )
        return Response(payload)

    @extend_schema(request=s.ChatMessageSerializer, responses=s.ChatReplySerializer)
    def post(self, request, **kwargs):
        """The guest's message → the assistant's answer (+ offer cards and hand-off state)."""
        prop, reservation = self.target(**kwargs)
        serializer = s.ChatMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        reply = chatbot.reply(
            prop,
            data["message"],
            session_id=data.get("session_id") or None,
            lang=data["language"],
            reservation=reservation,
        )
        return Response(self.reply_payload(reply.conversation, reply))


class ChatbotContactBaseView(PublicView):
    @extend_schema(request=s.ChatContactSerializer, responses={200: s.HandoffSerializer})
    def post(self, request, **kwargs):
        """After a hand-off: how to reach the guest (alert + inbox thread for the staff)."""
        prop, _ = self.target(**kwargs)
        serializer = s.ChatContactSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        conversation = (
            chatbot.get_conversation(prop, data["session_id"])
            if chatbot.SESSION_ID.match(data["session_id"])
            else None
        )
        if conversation is None:
            raise Http404("Conversación no encontrada")
        conversation = chatbot.submit_contact(
            conversation, name=data["name"], email=data["email"], phone=data["phone"], message=data["message"]
        )
        return Response({"ok": True, "handoff": chatbot.handoff_state(conversation)})


class _PropertyTarget:
    def target(self, *, slug):
        prop = chatbot.chatbot_property(slug)
        if prop is None:
            raise Http404("Chat no disponible")
        return prop, None


class _PortalTarget:
    def target(self, *, token):
        reservation = chatbot.portal_reservation(token)
        if reservation is None:
            raise Http404("Chat no disponible")
        return reservation.property, reservation


class ChatbotView(_PropertyTarget, ChatbotBaseView):
    pass


class ChatbotContactView(_PropertyTarget, ChatbotContactBaseView):
    pass


class PortalChatbotView(_PortalTarget, ChatbotBaseView):
    pass


class PortalChatbotContactView(_PortalTarget, ChatbotContactBaseView):
    pass
