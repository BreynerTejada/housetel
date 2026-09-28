"""Staff messaging API (`/api/v1/messaging/`, header `X-Property-Id`; plan C6).

Permissions (plan §D): `messaging.view` reads the inbox, templates, rules and previews; `messaging.send`
answers, writes notes, assigns, closes, writes to a guest and plays the guest in the WhatsApp simulator;
`messaging.templates` edits templates and lifecycle rules. Everything is scoped to the property of the header
(templates also to the organization) and objects of other hotels answer 404.
"""

import re
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Case, Count, F, IntegerField, Prefetch, Q, Sum, Value, When
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.bookings.models import Stay
from apps.core import audit, integrations
from apps.core.errors import ConflictError, DomainError
from apps.core.runtime import require_simulations
from apps.core.tenancy import PropertyScopedAPIView, PropertyScopedMixin
from apps.messaging import editor, inbox
from apps.messaging.api import serializers as s
from apps.messaging.lifecycle import ensure_rules
from apps.messaging.models import Conversation, LifecycleRule, Message, MessageTemplate
from apps.messaging.services import (
    find_guest,
    guest_address,
    message_language,
    receive_whatsapp,
    whatsapp_address,
)
from apps.messaging.variables import VARIABLES

VIEW, SEND, TEMPLATES = "messaging.view", "messaging.send", "messaging.templates"
UUID_REGEX = "[0-9a-fA-F-]{36}"
DEFAULT_MESSAGES_LIMIT = 50
MAX_MESSAGES_LIMIT = 200
SIMULATOR_THREAD_LIMIT = 200
CONTACTS_LIMIT = 20
_HAS_LETTERS = re.compile(r"[^\W\d_]")


# --- helpers -------------------------------------------------------------------------------------------


def _uuid_param(value, name: str) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return UUID(str(value))
    except ValueError:
        raise ValidationError({name: ["UUID inválido"]}) from None


def _reservation_of(request, pk):
    from apps.bookings.models import Reservation

    if pk is None:
        return None
    return get_object_or_404(
        Reservation.objects.select_related("property", "booker"), pk=pk, property=request.property
    )


def _guest_of(request, pk):
    """A guest of the organization (a merged record leads to the guest it now lives in)."""
    from apps.guests.models import Guest
    from apps.guests.services import surviving_guest

    if pk is None:
        return None
    return surviving_guest(get_object_or_404(Guest, pk=pk, organization=request.organization))


def search_conversations(queryset, query: str):
    """Every word must match the contact or guest name (accents ignored), the guest email, the booking code,
    the address or the last message; a phone typed with spaces or dashes matches by its digits."""
    words = query.split()
    if not words:
        return queryset
    every_word = Q()
    for word in words:
        every_word &= (
            Q(contact_name__unaccent__icontains=word)
            | Q(guest__first_name__unaccent__icontains=word)
            | Q(guest__last_name__unaccent__icontains=word)
            | Q(guest__email__icontains=word)
            | Q(reservation__code__icontains=word)
            | Q(external_thread_key__icontains=word)
            | Q(last_message_preview__unaccent__icontains=word)
        )
    digits = re.sub(r"\D", "", query)
    if len(digits) >= 3 and not _HAS_LETTERS.search(query):
        every_word |= Q(external_thread_key__contains=digits) | Q(guest__phone__contains=digits)
    return queryset.filter(every_word)


def _conversation_payload(conversation, request) -> dict:
    return s.ConversationSerializer(conversation, context={"request": request}).data


# --- conversations (unified inbox) ---------------------------------------------------------------------


class ConversationViewSet(
    PropertyScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Threads of the active hotel, newest activity first."""

    queryset = Conversation.objects.select_related("guest", "reservation", "assigned_to").prefetch_related(
        Prefetch("reservation__stays", queryset=Stay.objects.select_related("room", "bed"))
    )
    serializer_class = s.ConversationSerializer
    lookup_value_regex = UUID_REGEX
    required_permissions = {
        "list": VIEW,
        "retrieve": VIEW,
        "read": VIEW,
        "unread_count": VIEW,
        "assign": SEND,
        "close": SEND,
        "reopen": SEND,
        "*": VIEW,
    }

    def get_required_permission(self):
        if getattr(self, "action", None) == "messages" and self.request.method == "POST":
            return SEND
        return super().get_required_permission()

    def get_serializer_class(self):
        if self.action == "retrieve":
            return s.ConversationDetailSerializer
        return super().get_serializer_class()

    def _filtered(self, queryset):
        params = self.request.query_params
        unread = params.get("unread")
        if unread in ("1", "true"):
            queryset = queryset.filter(unread_count__gt=0)
        elif unread in ("0", "false"):
            queryset = queryset.filter(unread_count=0)
        if channel := params.get("channel"):
            queryset = queryset.filter(channel=channel)
        if conversation_status := params.get("status"):
            queryset = queryset.filter(status=conversation_status)
        assigned = params.get("assigned")
        if assigned == "me":
            queryset = queryset.filter(assigned_to=self.request.user)
        elif assigned == "none":
            queryset = queryset.filter(assigned_to__isnull=True)
        elif assigned:
            queryset = queryset.filter(assigned_to_id=_uuid_param(assigned, "assigned"))
        if reservation_id := _uuid_param(params.get("reservation"), "reservation"):
            # The thread's reservation follows its latest message: a returning guest's older booking is found
            # through the messages recorded for it.
            about_it = Message.objects.filter(reservation_id=reservation_id).values("conversation_id")
            queryset = queryset.filter(Q(reservation_id=reservation_id) | Q(pk__in=about_it))
        if guest_id := _uuid_param(params.get("guest"), "guest"):
            queryset = queryset.filter(guest_id=guest_id)
        if query := (params.get("q") or "").strip():
            queryset = search_conversations(queryset, query)
        return queryset.order_by(F("last_message_at").desc(nulls_last=True), "-created_at", "-id")

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "unread", OpenApiTypes.BOOL, description="Solo con mensajes sin leer (1) o sin ellos (0)"
            ),
            OpenApiParameter("channel", OpenApiTypes.STR, description="email | whatsapp | web_chat | ota"),
            OpenApiParameter("status", OpenApiTypes.STR, description="open | closed"),
            OpenApiParameter("assigned", OpenApiTypes.STR, description="me | none | <id de usuario>"),
            OpenApiParameter("reservation", OpenApiTypes.UUID),
            OpenApiParameter("guest", OpenApiTypes.UUID),
            OpenApiParameter(
                "q", OpenApiTypes.STR, description="Nombre, código de reserva, teléfono o texto"
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        queryset = self._filtered(self.get_queryset())
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @extend_schema(
        methods=["GET"],
        parameters=[
            OpenApiParameter(
                "limit", OpenApiTypes.INT, description=f"Máximo {MAX_MESSAGES_LIMIT} (por defecto 50)"
            ),
            OpenApiParameter(
                "before", OpenApiTypes.DATETIME, description="Mensajes anteriores a este momento"
            ),
        ],
        responses=s.MessagePageSerializer,
    )
    @extend_schema(methods=["POST"], request=s.ReplySerializer, responses={201: s.MessageSerializer})
    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        """GET: the thread, oldest first (`before` pages back). POST: answer on the thread's channel, or an
        internal note (`internal: true`, never sent to the guest)."""
        conversation = self.get_object()
        if request.method == "POST":
            return self._reply(conversation, request)
        try:
            limit = min(
                max(int(request.query_params.get("limit") or DEFAULT_MESSAGES_LIMIT), 1), MAX_MESSAGES_LIMIT
            )
        except ValueError:
            raise ValidationError({"limit": ["Número inválido"]}) from None
        messages = conversation.messages.select_related("sent_by").order_by("-created_at", "-id")
        if before := request.query_params.get("before"):
            moment = parse_datetime(before)
            if moment is None:
                raise ValidationError({"before": ["Fecha y hora inválidas (ISO 8601)"]})
            messages = messages.filter(created_at__lt=moment)
        rows = list(messages[: limit + 1])
        page = list(reversed(rows[:limit]))
        return Response({"results": s.MessageSerializer(page, many=True).data, "has_more": len(rows) > limit})

    def _reply(self, conversation, request):
        serializer = s.ReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if values["internal"]:
            message = inbox.add_note(conversation, body=values["body"], author=request.user)
        else:
            message = inbox.reply(
                conversation,
                body=values["body"],
                author=request.user,
                subject=values["subject"],
                template_code=values["template_code"],
                ai_generated=values["ai_generated"],
            )
        return Response(s.MessageSerializer(message).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=s.ConversationSerializer)
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        """Mark the thread as read (unread counter back to 0)."""
        return Response(_conversation_payload(inbox.mark_read(self.get_object()), request))

    @extend_schema(request=s.AssignSerializer, responses=s.ConversationSerializer)
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """Assign to a member with access to this hotel (`user_id: null` = nobody)."""
        from apps.accounts.models import User

        conversation = self.get_object()
        serializer = s.AssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = serializer.validated_data["user_id"]
        user = None
        if user_id is not None:
            user = User.objects.filter(pk=user_id, is_active=True).first()
            if user is None:
                raise DomainError(
                    "Solo puedes asignarla a alguien del equipo de este hotel",
                    code="invalid_user",
                    fields={"user_id": ["Inválido"]},
                )
        return Response(_conversation_payload(inbox.assign(conversation, user), request))

    @extend_schema(request=None, responses=s.ConversationSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        conversation = inbox.set_status(self.get_object(), Conversation.Status.CLOSED)
        return Response(_conversation_payload(conversation, request))

    @extend_schema(request=None, responses=s.ConversationSerializer)
    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        conversation = inbox.set_status(self.get_object(), Conversation.Status.OPEN)
        return Response(_conversation_payload(conversation, request))

    @extend_schema(responses=s.UnreadCountSerializer)
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        """Open threads waiting for an answer and their unread messages (topbar badge)."""
        totals = Conversation.objects.filter(
            property=request.property, status=Conversation.Status.OPEN, unread_count__gt=0
        ).aggregate(conversations=Count("id"), messages=Sum("unread_count"))
        return Response({"conversations": totals["conversations"], "messages": totals["messages"] or 0})


# --- templates -----------------------------------------------------------------------------------------


class TemplateViewSet(
    PropertyScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """`GET templates/` lists every template the hotel can use with the text that applies (property override →
    organization → system default). Writes create or change an override row; deleting it restores the
    inherited text. Organization rows affect every hotel, so only members with access to all of them edit
    them."""

    queryset = MessageTemplate.objects.select_related("property", "organization")
    serializer_class = s.TemplateSerializer
    lookup_value_regex = UUID_REGEX
    required_permissions = {
        "list": VIEW,
        "retrieve": VIEW,
        "preview": VIEW,
        "create": TEMPLATES,
        "update": TEMPLATES,
        "partial_update": TEMPLATES,
        "destroy": TEMPLATES,
        "*": VIEW,
    }

    def get_queryset(self):
        prop = self.request.property
        return self.queryset.filter(organization_id=prop.organization_id).filter(
            Q(property=prop) | Q(property__isnull=True)
        )

    def _require_organization_scope(self):
        if not self.request.membership.all_properties:
            raise PermissionDenied(
                {
                    "detail": "Las plantillas de toda la organización solo las editan miembros con acceso a "
                    "todos sus hoteles",
                    "code": "organization_scope_forbidden",
                }
            )

    def _audit(self, template, action_name, summary, changes=None):
        audit.record(
            action=action_name,
            target=template,
            summary=summary,
            actor=self.request.user,
            changes=changes,
            property=template.property,
            organization=template.organization,
        )

    @extend_schema(responses=s.EffectiveTemplateSerializer(many=True))
    def list(self, request, *args, **kwargs):
        rows = editor.effective_templates(request.property)
        return Response(s.EffectiveTemplateSerializer(rows, many=True).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        scope = values.pop("scope", "property")
        if scope == "organization":
            self._require_organization_scope()
        prop = request.property if scope == "property" else None
        key = {"code": values["code"], "channel": values["channel"], "language": values["language"]}
        existing = MessageTemplate.objects.filter(
            organization=request.organization, property=prop, **key
        ).first()
        if existing is not None:
            raise ConflictError(
                "Ya existe esa plantilla: edítala", code="template_exists", id=str(existing.pk)
            )
        try:
            with transaction.atomic():
                template = MessageTemplate.objects.create(
                    organization=request.organization, property=prop, updated_by=request.user, **values
                )
                self._audit(
                    template,
                    "messaging.template_created",
                    f"Personalizó la plantilla {template}",
                    changes={
                        "subject": template.subject,
                        "body": template.body,
                        "is_active": template.is_active,
                    },
                )
        except IntegrityError:  # created by someone else at the same moment
            existing = MessageTemplate.objects.filter(
                organization=request.organization, property=prop, **key
            ).first()
            raise ConflictError(
                "Ya existe esa plantilla: edítala",
                code="template_exists",
                id=str(existing.pk) if existing else None,
            ) from None
        return Response(self.get_serializer(template).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        template = serializer.instance
        if template.property_id is None:
            self._require_organization_scope()
        fields = ("name", "subject", "body", "is_active", "wa_template_name", "wa_template_params")
        before = {field: getattr(template, field) for field in fields}
        with transaction.atomic():
            template = serializer.save(updated_by=self.request.user)
            changes = audit.diff(before, {field: getattr(template, field) for field in fields})
            if changes:
                self._audit(template, "messaging.template_updated", f"Editó la plantilla {template}", changes)

    def perform_destroy(self, instance):
        if instance.property_id is None:
            self._require_organization_scope()
        with transaction.atomic():
            self._audit(
                instance,
                "messaging.template_deleted",
                f"Restauró la plantilla heredada de {instance}",
                changes={"subject": instance.subject, "body": instance.body},
            )
            instance.delete()

    @extend_schema(request=s.PreviewRequestSerializer, responses=s.PreviewSerializer)
    @action(detail=False, methods=["post"])
    def preview(self, request):
        """Render a template (the effective one of `template_code`, or a draft `subject`/`body`) for a
        reservation, a conversation or a guest of this hotel, or with sample values when none is given."""
        serializer = s.PreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        reservation = _reservation_of(request, values.get("reservation_id"))
        guest = _guest_of(request, values.get("guest_id"))
        if conversation_id := values.get("conversation_id"):
            conversation = get_object_or_404(
                Conversation.objects.select_related("guest", "reservation"),
                pk=conversation_id,
                property=request.property,
            )
            guest = guest or conversation.guest
            reservation = reservation or conversation.reservation
        data = editor.preview(
            request.property,
            channel=values["channel"],
            language=values.get("language"),
            template_code=values["template_code"],
            subject=values.get("subject"),
            body=values.get("body"),
            guest=guest,
            reservation=reservation,
        )
        return Response(data)


class VariablesView(PropertyScopedAPIView):
    """The `{{variables}}` a template can use, with labels and examples (ES/EN)."""

    required_permissions = {"get": VIEW}

    @extend_schema(responses=s.VariableSerializer(many=True))
    def get(self, request):
        return Response(s.VariableSerializer(VARIABLES, many=True).data)


# --- lifecycle rules -----------------------------------------------------------------------------------


class LifecycleRuleViewSet(
    PropertyScopedMixin, mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    """The six automatic messages of the guest lifecycle for the active hotel (created with the defaults the
    first time they are read)."""

    queryset = LifecycleRule.objects.select_related("property")
    serializer_class = s.LifecycleRuleSerializer
    lookup_value_regex = UUID_REGEX
    required_permissions = {"list": VIEW, "update": TEMPLATES, "partial_update": TEMPLATES, "*": VIEW}

    def list(self, request, *args, **kwargs):
        return Response(self.get_serializer(ensure_rules(request.property), many=True).data)

    def perform_update(self, serializer):
        rule = serializer.instance
        fields = ("enabled", "days_offset", "channels", "template_code", "send_after")
        before = {field: getattr(rule, field) for field in fields}
        with transaction.atomic():
            rule = serializer.save()
            changes = audit.diff(before, {field: getattr(rule, field) for field in fields})
            if changes:
                audit.record(
                    action="messaging.lifecycle_rule_updated",
                    target=rule,
                    summary=f"Cambió el mensaje automático «{editor.code_label(rule.event)['es']}»",
                    actor=self.request.user,
                    changes=changes,
                    property=rule.property,
                )


# --- write to a guest ----------------------------------------------------------------------------------


class SendView(PropertyScopedAPIView):
    """Write to a guest from a reservation or a guest profile: a template or free text, by email or WhatsApp.
    It starts (or continues) the conversation of the guest's address on that channel."""

    required_permissions = {"post": SEND}

    @extend_schema(request=s.SendSerializer, responses={201: s.SendResultSerializer})
    def post(self, request):
        serializer = s.SendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        reservation = _reservation_of(request, values.get("reservation_id"))
        guest = _guest_of(request, values.get("guest_id"))
        message = inbox.send_to_guest(
            request.property,
            channel=values["channel"],
            author=request.user,
            guest=guest,
            reservation=reservation,
            to=values["to"] or None,
            template_code=values["template_code"],
            subject=values["subject"],
            body=values["body"],
        )
        data = {"message": s.MessageSerializer(message).data, "conversation_id": message.conversation_id}
        return Response(data, status=status.HTTP_201_CREATED)


class RecipientView(PropertyScopedAPIView):
    """Who a message goes to before writing it: the guest (the reservation's booker by default), the language
    of the templates and the address Housetel would use on each channel ('' = none: ask for one)."""

    required_permissions = {"get": SEND}

    @extend_schema(
        parameters=[
            OpenApiParameter("reservation", OpenApiTypes.UUID),
            OpenApiParameter("guest", OpenApiTypes.UUID),
        ],
        responses=s.RecipientSerializer,
    )
    def get(self, request):
        params = request.query_params
        reservation = _reservation_of(request, _uuid_param(params.get("reservation"), "reservation"))
        guest = _guest_of(request, _uuid_param(params.get("guest"), "guest"))
        guest = guest if guest is not None else getattr(reservation, "booker", None)
        return Response(
            {
                "guest": None
                if guest is None
                else {
                    "id": guest.pk,
                    "full_name": guest.full_name,
                    "email": guest.email,
                    "phone": guest.phone,
                    "language": guest.language,
                },
                "reservation": _reservation_ref(reservation),
                "language": message_language(request.property, guest, reservation),
                "addresses": {channel: guest_address(channel, guest) for channel in ("email", "whatsapp")},
            }
        )


# --- WhatsApp simulator --------------------------------------------------------------------------------


def _simulator_enabled(prop) -> bool:
    return integrations.get_setting(prop, "whatsapp").mode == "simulated"


def _simulator_phone(value) -> str:
    phone = whatsapp_address(value)
    if not phone:
        raise DomainError(
            "El número de teléfono no es válido", code="invalid_phone", fields={"phone": ["Inválido"]}
        )
    return phone


def _guest_ref(guest) -> dict | None:
    return (
        None if guest is None else {"id": guest.pk, "full_name": guest.full_name, "language": guest.language}
    )


def _reservation_ref(reservation) -> dict | None:
    if reservation is None:
        return None
    return {
        "id": reservation.pk,
        "code": reservation.code,
        "status": reservation.status,
        "checkin_date": reservation.checkin_date,
        "checkout_date": reservation.checkout_date,
    }


@require_simulations  # 404 where simulations are off (production)
class SimulatorInboundView(PropertyScopedAPIView):
    """Play the guest: a WhatsApp message from `phone` lands in the inbox exactly like a real one (the guest
    is found by phone in the organization, or created as a WhatsApp contact). Only while the hotel's WhatsApp
    is simulated: in real mode the replies would reach a real phone."""

    required_permissions = {"post": SEND}

    @extend_schema(request=s.SimulatorInboundSerializer, responses={201: s.SendResultSerializer})
    def post(self, request):
        if not _simulator_enabled(request.property):
            raise ConflictError(
                "El simulador solo funciona con WhatsApp en modo simulado", code="simulator_disabled"
            )
        serializer = s.SimulatorInboundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        message = receive_whatsapp(
            request.property,
            phone=_simulator_phone(values["phone"]),
            body=values["body"],
            profile_name=values["name"],
        )
        data = {"message": s.MessageSerializer(message).data, "conversation_id": message.conversation_id}
        return Response(data, status=status.HTTP_201_CREATED)


@require_simulations  # 404 where simulations are off (production)
class SimulatorThreadView(PropertyScopedAPIView):
    """What the guest's phone shows: the WhatsApp chat of `phone` with this hotel (internal notes
    excluded)."""

    required_permissions = {"get": SEND}

    @extend_schema(
        parameters=[OpenApiParameter("phone", OpenApiTypes.STR, required=True)],
        responses=s.SimulatorThreadSerializer,
    )
    def get(self, request):
        phone = _simulator_phone(request.query_params.get("phone"))
        conversation = (
            Conversation.objects.select_related("guest")
            .filter(
                property=request.property, channel=Conversation.Channel.WHATSAPP, external_thread_key=phone
            )
            .first()
        )
        messages = []
        guest = None
        if conversation is not None:
            guest = conversation.guest
            rows = list(
                conversation.messages.exclude(channel=Message.Channel.INTERNAL_NOTE)
                .select_related("sent_by")
                .order_by("-created_at", "-id")[:SIMULATOR_THREAD_LIMIT]
            )
            messages = list(reversed(rows))
        if guest is None:
            guest = find_guest(request.property, "whatsapp", phone)
        return Response(
            {
                "phone": phone,
                "simulator_enabled": _simulator_enabled(request.property),
                "conversation_id": conversation.pk if conversation is not None else None,
                "guest": _guest_ref(guest),
                "messages": s.MessageSerializer(messages, many=True).data,
            }
        )


@require_simulations  # 404 where simulations are off (production)
class SimulatorContactsView(PropertyScopedAPIView):
    """Guests with a phone to play in the simulator: arrivals of the next days and in-house guests first, or
    the ones matching `q` (name or phone digits)."""

    required_permissions = {"get": SEND}

    @extend_schema(
        parameters=[OpenApiParameter("q", OpenApiTypes.STR)],
        responses=s.SimulatorContactsSerializer,
    )
    def get(self, request):
        from datetime import timedelta

        from apps.bookings.models import Reservation
        from apps.guests.api.filters import search_q
        from apps.guests.models import Guest

        prop = request.property
        query = (request.query_params.get("q") or "").strip()
        guests = Guest.objects.filter(organization=prop.organization, merged_into__isnull=True).exclude(
            phone=""
        )
        relevant = (
            Reservation.objects.filter(property=prop, booker__in=guests)
            .filter(
                Q(status="checked_in")
                | Q(
                    status__in=["tentative", "confirmed"],
                    checkin_date__gte=prop.business_date,
                    checkin_date__lte=prop.business_date + timedelta(days=7),
                )
            )
            .select_related("booker")
            .annotate(
                in_house_first=Case(
                    When(status="checked_in", then=Value(0)), default=Value(1), output_field=IntegerField()
                )
            )
            .order_by("in_house_first", "checkin_date", "created_at")
        )
        if query:
            matches = list(
                guests.filter(search_q(query)).order_by("first_name", "last_name", "id")[:CONTACTS_LIMIT]
            )
            current = {}
            for reservation in relevant.filter(booker__in=matches):
                current.setdefault(reservation.booker_id, reservation)
            rows = [(guest, current.get(guest.pk)) for guest in matches]
        else:
            rows, seen = [], set()
            for reservation in relevant[: CONTACTS_LIMIT * 3]:
                if reservation.booker_id not in seen:
                    seen.add(reservation.booker_id)
                    rows.append((reservation.booker, reservation))
            if len(rows) < CONTACTS_LIMIT:
                others = guests.exclude(pk__in=seen).order_by("-updated_at", "id")[
                    : CONTACTS_LIMIT - len(rows)
                ]
                rows.extend((guest, None) for guest in others)
            rows = rows[:CONTACTS_LIMIT]
        results = [
            {
                "guest_id": guest.pk,
                "full_name": guest.full_name,
                "phone": guest.phone,
                "reservation": _reservation_ref(reservation),
            }
            for guest, reservation in rows
        ]
        return Response({"simulator_enabled": _simulator_enabled(prop), "results": results})
