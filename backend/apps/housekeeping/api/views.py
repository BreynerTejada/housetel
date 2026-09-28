"""Staff housekeeping API (`/api/v1/housekeeping/`, header `X-Property-Id`).

Permissions (plan §D, "work: only her tasks · supervise: everything · maintenance: tickets"):
- `housekeeping.view`: read the board, the day summary, staff, settings, tasks and tickets. Someone who
  works (`housekeeping.work`) without supervising only ever sees her own tasks (list, detail, board).
- `housekeeping.work`: start / finish her tasks, report damage (tickets with photos), mark a room clean or
  dirty.
- `housekeeping.supervise`: every task (create, edit, assign, inspect, cancel, auto-assign, generate),
  settings, any room status, delete tickets.
- `housekeeping.maintenance`: work the tickets (edit, block, start, resolve, cancel).
"""

from datetime import date
from uuid import UUID

from django.db import transaction
from django.db.models import Case, IntegerField, Prefetch, Q, Value, When
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.models import User
from apps.core.errors import DomainError
from apps.core.permissions import codes_match
from apps.core.tenancy import PropertyScopedAPIView, PropertyScopedMixin
from apps.housekeeping import selectors
from apps.housekeeping.api import serializers as s
from apps.housekeeping.models import HousekeepingTask, MaintenanceTicket, Priority, TicketPhoto
from apps.housekeeping.services import rooms as rooms_svc
from apps.housekeeping.services import tasks as tasks_svc
from apps.housekeeping.services import tickets as tickets_svc
from apps.housekeeping.services.assignment import auto_assign, eligible_staff
from apps.housekeeping.services.config import get_settings, update_settings
from apps.housekeeping.services.generation import generate_daily_tasks
from apps.housekeeping.services.queries import day_filter
from apps.inventory.models import Bed, Room

VIEW = "housekeeping.view"
WORK = "housekeeping.work"
SUPERVISE = "housekeeping.supervise"
MAINTENANCE = "housekeeping.maintenance"
REPORT = (WORK, MAINTENANCE, SUPERVISE)  # report damage
REPAIR = (MAINTENANCE, SUPERVISE)  # work the tickets
UUID_REGEX = "[0-9a-fA-F-]{36}"
TRUE = {"1", "true", "True", "yes"}


# ---- Helpers ---------------------------------------------------------------------------------------------


class AnyOfPermissionsMixin:
    """`required_permissions` values may be a tuple: any of those codes grants the action (a refusal names
    the first one)."""

    def get_required_permission(self):
        code = super().get_required_permission()
        if isinstance(code, tuple):
            granted = self.request.membership.role.permissions
            return next((candidate for candidate in code if codes_match(granted, candidate)), code[0])
        return code


def granted(request, *codes: str) -> bool:
    permissions = request.membership.role.permissions
    return any(codes_match(permissions, code) for code in codes)


def sees_all_tasks(request) -> bool:
    """Supervisors and read-only roles (front desk, maintenance) see every task; housekeepers only theirs."""
    return granted(request, SUPERVISE) or not granted(request, WORK)


def denied(code: str) -> PermissionDenied:
    return PermissionDenied(
        {"detail": "No tienes permiso para esta acción", "code": "permission_denied", "permission": code}
    )


def validated(serializer_class, data) -> dict:
    serializer = serializer_class(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def date_param(request, name: str, default):
    value = request.query_params.get(name)
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError({name: ["Fecha inválida (AAAA-MM-DD)"]}) from None


def choices_param(request, name: str, allowed) -> list[str]:
    values = [value for value in request.query_params.getlist(name) if value]
    unknown = [value for value in values if value not in allowed]
    if unknown:
        raise ValidationError({name: [f"Valor inválido: {', '.join(unknown)}"]})
    return values


def uuid_param(request, name: str) -> UUID | None:
    value = request.query_params.get(name)
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        raise ValidationError({name: ["UUID inválido"]}) from None


def assignee_filter(request, field: str = "assigned_to") -> Q | None:
    """`assignee=none` (unassigned) · `me` · `<user uuid>`."""
    value = request.query_params.get("assignee")
    if not value:
        return None
    if value == "none":
        return Q(**{f"{field}__isnull": True})
    if value == "me":
        return Q(**{field: request.user})
    return Q(**{f"{field}_id": uuid_param(request, "assignee")})


def user_or_error(user_id, *, field: str, message: str) -> User | None:
    """A user by id (None → None); an unknown id is the same error as someone without the permission."""
    if user_id is None:
        return None
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        raise DomainError(message, code="invalid_assignee", fields={field: [message]})
    return user


# ---- Tasks -------------------------------------------------------------------------------------------------

TASK_LIST_PARAMETERS = [
    OpenApiParameter("date", OpenApiTypes.DATE, description="Fecha de negocio (por defecto, la actual)"),
    OpenApiParameter("status", OpenApiTypes.STR, many=True, enum=HousekeepingTask.Status.values),
    OpenApiParameter("kind", OpenApiTypes.STR, many=True, enum=HousekeepingTask.Kind.values),
    OpenApiParameter("floor", OpenApiTypes.STR),
    OpenApiParameter("assignee", OpenApiTypes.STR, description="`none`, `me` o el id de la persona"),
    OpenApiParameter("mine", OpenApiTypes.BOOL, description="Solo las tareas asignadas a quien consulta"),
]


class TaskViewSet(
    AnyOfPermissionsMixin,
    PropertyScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Cleaning / inspection tasks. `GET tasks/` = the business date (plus what is still open from earlier
    days), open work first by priority."""

    queryset = HousekeepingTask.objects.select_related(*selectors.TASK_RELATED)
    serializer_class = s.HousekeepingTaskSerializer
    filter_backends: list = []
    lookup_value_regex = UUID_REGEX
    http_method_names = ["get", "post", "patch", "head", "options"]
    required_permissions = {
        "list": VIEW,
        "retrieve": VIEW,
        "start": WORK,
        "finish": WORK,
        "create": SUPERVISE,
        "partial_update": SUPERVISE,
        "inspect": SUPERVISE,
        "assign": SUPERVISE,
        "cancel": SUPERVISE,
        "auto_assign": SUPERVISE,
        "generate": SUPERVISE,
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        if not sees_all_tasks(self.request):
            queryset = queryset.filter(assigned_to=self.request.user)
        return queryset

    def payload(self, task) -> dict:
        task = HousekeepingTask.objects.select_related(*selectors.TASK_RELATED).get(pk=task.pk)
        return s.HousekeepingTaskSerializer(
            task, context=selectors.task_context(self.request.property, [task])
        ).data

    @extend_schema(parameters=TASK_LIST_PARAMETERS)
    def list(self, request, *args, **kwargs):
        prop = request.property
        queryset = self.get_queryset().filter(
            day_filter(prop, date_param(request, "date", prop.business_date))
        )
        if statuses := choices_param(request, "status", HousekeepingTask.Status.values):
            queryset = queryset.filter(status__in=statuses)
        if kinds := choices_param(request, "kind", HousekeepingTask.Kind.values):
            queryset = queryset.filter(kind__in=kinds)
        if floor := request.query_params.get("floor"):
            queryset = queryset.filter(room__floor=floor)
        if (condition := assignee_filter(request)) is not None:
            queryset = queryset.filter(condition)
        if request.query_params.get("mine") in TRUE:
            queryset = queryset.filter(assigned_to=request.user)
        queryset = selectors.ordered_tasks(queryset)
        page = self.paginate_queryset(queryset)
        tasks = list(page if page is not None else queryset)
        data = s.HousekeepingTaskSerializer(
            tasks, many=True, context=selectors.task_context(prop, tasks)
        ).data
        return self.get_paginated_response(data) if page is not None else Response(data)

    def retrieve(self, request, *args, **kwargs):
        return Response(self.payload(self.get_object()))

    @extend_schema(request=s.HousekeepingTaskCreateSerializer, responses={201: s.HousekeepingTaskSerializer})
    def create(self, request, *args, **kwargs):
        """A task created by a supervisor (deep clean, turndown, other…) for the business date."""
        data = validated(s.HousekeepingTaskCreateSerializer, request.data)
        prop = request.property
        room = (
            Room.objects.select_related("room_type", "property")
            .filter(pk=data["room_id"], property=prop)
            .first()
        )
        if room is None:
            raise ValidationError({"room_id": ["La habitación no pertenece a este hotel"]})
        bed = None
        if data.get("bed_id"):
            bed = Bed.objects.filter(pk=data["bed_id"], room=room).first()
            if bed is None:
                raise ValidationError({"bed_id": ["La cama no pertenece a esta habitación"]})
        assignee = user_or_error(
            data.get("assigned_to_id"),
            field="assigned_to_id",
            message="Esa persona no hace limpieza en este hotel",
        )
        task = tasks_svc.create_task(
            prop,
            room=room,
            kind=data["kind"],
            priority=data["priority"],
            notes=data["notes"],
            assigned_to=assignee,
            bed=bed,
            minutes=data.get("estimated_minutes"),
            actor=request.user,
        )
        return Response(self.payload(task), status=status.HTTP_201_CREATED)

    @extend_schema(request=s.HousekeepingTaskUpdateSerializer, responses=s.HousekeepingTaskSerializer)
    def partial_update(self, request, *args, **kwargs):
        data = validated(s.HousekeepingTaskUpdateSerializer, request.data)
        return Response(self.payload(tasks_svc.update_task(self.get_object(), data, actor=request.user)))

    @extend_schema(request=None, responses=s.HousekeepingTaskSerializer)
    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """pending → in_progress (an unassigned task is taken by whoever starts it). A departure clean waits
        for the check-out (409 `guest_in_room`)."""
        return Response(self.payload(tasks_svc.start_task(self.get_object(), actor=request.user)))

    @extend_schema(request=s.HkFinishSerializer, responses=s.HousekeepingTaskSerializer)
    @action(detail=True, methods=["post"])
    def finish(self, request, pk=None):
        """→ done. A clean leaves the room `clean` (and creates the inspection if the hotel requires it)."""
        data = validated(s.HkFinishSerializer, request.data)
        task = tasks_svc.finish_task(self.get_object(), actor=request.user, notes=data["notes"])
        return Response(self.payload(task))

    @extend_schema(request=s.HkInspectSerializer, responses=s.HousekeepingTaskSerializer)
    @action(detail=True, methods=["post"])
    def inspect(self, request, pk=None):
        """Passed → room `inspected`; failed → room `dirty` and a high-priority clean for who cleaned it."""
        data = validated(s.HkInspectSerializer, request.data)
        task = tasks_svc.inspect_task(
            self.get_object(), actor=request.user, passed=data["passed"], notes=data["notes"]
        )
        return Response(self.payload(task))

    @extend_schema(request=s.HkAssignSerializer, responses=s.HousekeepingTaskSerializer)
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """`{user_id}` = someone who cleans in this hotel (`housekeeping.work`), or null to unassign."""
        data = validated(s.HkAssignSerializer, request.data)
        user = user_or_error(
            data["user_id"], field="user_id", message="Esa persona no hace limpieza en este hotel"
        )
        return Response(self.payload(tasks_svc.assign_task(self.get_object(), user=user, actor=request.user)))

    @extend_schema(request=s.HkCancelSerializer, responses=s.HousekeepingTaskSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        data = validated(s.HkCancelSerializer, request.data)
        return Response(
            self.payload(tasks_svc.cancel_task(self.get_object(), actor=request.user, reason=data["reason"]))
        )

    @extend_schema(request=s.HkAutoAssignSerializer, responses=s.HkAutoAssignReportSerializer)
    @action(detail=False, methods=["post"], url_path="auto-assign")
    def auto_assign(self, request):
        """Share the day's unassigned pending tasks, balancing minutes and grouping floors, among every
        housekeeper of the hotel or the `user_ids` chosen for today."""
        data = validated(s.HkAutoAssignSerializer, request.data)
        staff = None
        if "user_ids" in data:
            eligible = {user.pk: user for user in eligible_staff(request.property)}
            unknown = [str(user_id) for user_id in data["user_ids"] if user_id not in eligible]
            if unknown:
                message = "Estas personas no hacen limpieza en este hotel"
                raise DomainError(
                    message, code="invalid_assignee", fields={"user_ids": [message]}, user_ids=unknown
                )
            staff = [eligible[user_id] for user_id in dict.fromkeys(data["user_ids"])]
        return Response(auto_assign(request.property, actor=request.user, staff=staff))

    @extend_schema(request=None, responses=s.HkGenerateReportSerializer)
    @action(detail=False, methods=["post"])
    def generate(self, request):
        """Run the daily generation now (departures, stayovers by frequency, dirty rooms). Idempotent."""
        return Response(generate_daily_tasks(request.property, actor=request.user))


# ---- Board, summary, staff, settings, room status ----------------------------------------------------------


class BoardView(PropertyScopedAPIView):
    """`GET board/`: rooms by floor with status, occupancy, arrival today, tasks, blocks and tickets."""

    required_permissions = {"get": VIEW}

    @extend_schema(responses=s.HousekeepingBoardSerializer)
    def get(self, request):
        only = None if sees_all_tasks(request) else request.user
        return Response(selectors.board(request.property, only_assignee=only))


class SummaryView(PropertyScopedAPIView):
    """`GET summary/`: progress of the day (rooms by status, tasks, minutes, open tickets)."""

    required_permissions = {"get": VIEW}

    @extend_schema(responses=s.HousekeepingSummarySerializer)
    def get(self, request):
        return Response(selectors.summary(request.property))


class StaffView(PropertyScopedAPIView):
    """`GET staff/`: housekeepers with today's load and maintenance technicians with their open tickets."""

    required_permissions = {"get": VIEW}

    @extend_schema(responses=s.HousekeepingStaffSerializer)
    def get(self, request):
        return Response(selectors.staff(request.property))


class SettingsView(PropertyScopedAPIView):
    required_permissions = {"get": VIEW, "patch": SUPERVISE}

    @extend_schema(responses=s.HousekeepingSettingsSerializer)
    def get(self, request):
        return Response(s.HousekeepingSettingsSerializer(get_settings(request.property)).data)

    @extend_schema(request=s.HousekeepingSettingsSerializer, responses=s.HousekeepingSettingsSerializer)
    def patch(self, request):
        serializer = s.HousekeepingSettingsSerializer(
            get_settings(request.property), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        settings = update_settings(request.property, serializer.validated_data, actor=request.user)
        return Response(s.HousekeepingSettingsSerializer(settings).data)


class RoomStatusView(AnyOfPermissionsMixin, PropertyScopedAPIView):
    """`POST rooms/{id}/status/` `{housekeeping_status}`: housekeepers mark clean or dirty; supervisors also
    inspected or out of service. A room held by a blocking maintenance ticket → 409 `room_blocked`."""

    required_permissions = {"post": (WORK, SUPERVISE)}

    @extend_schema(request=s.HkRoomStatusSerializer, responses=s.HkRoomStatusResultSerializer)
    def post(self, request, pk):
        room = (
            Room.objects.select_related("property", "room_type")
            .filter(pk=pk, property=request.property)
            .first()
        )
        if room is None:
            raise NotFound("Habitación no encontrada")
        new_status = validated(s.HkRoomStatusSerializer, request.data)["housekeeping_status"]
        basic = (Room.HousekeepingStatus.CLEAN, Room.HousekeepingStatus.DIRTY)
        if new_status not in basic and not granted(request, SUPERVISE):
            raise denied(SUPERVISE)
        room = rooms_svc.set_room_status(room, new_status, actor=request.user)
        return Response(
            {"id": room.pk, "number": room.number, "housekeeping_status": room.housekeeping_status}
        )


# ---- Tickets -----------------------------------------------------------------------------------------------

TICKET_STATUS_ORDER = Case(
    When(status=MaintenanceTicket.Status.IN_PROGRESS, then=Value(0)),
    When(status=MaintenanceTicket.Status.OPEN, then=Value(1)),
    When(status=MaintenanceTicket.Status.RESOLVED, then=Value(2)),
    default=Value(3),
    output_field=IntegerField(),
)

TICKET_LIST_PARAMETERS = [
    OpenApiParameter("status", OpenApiTypes.STR, many=True, enum=MaintenanceTicket.Status.values),
    OpenApiParameter("priority", OpenApiTypes.STR, many=True, enum=Priority.values),
    OpenApiParameter("room", OpenApiTypes.UUID),
    OpenApiParameter("assignee", OpenApiTypes.STR, description="`none`, `me` o el id de la persona"),
    OpenApiParameter("blocking", OpenApiTypes.BOOL, description="Solo los que bloquean (o no) su habitación"),
    OpenApiParameter("mine", OpenApiTypes.BOOL, description="Reportados por mí o asignados a mí"),
    OpenApiParameter(
        "q", OpenApiTypes.STR, description="Título, descripción, ubicación o número de habitación"
    ),
]


class TicketViewSet(
    AnyOfPermissionsMixin,
    PropertyScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Maintenance tickets. Created with JSON or multipart (`photos` = several image files)."""

    queryset = MaintenanceTicket.objects.select_related(
        "room__room_type", "block", "reported_by", "assigned_to", "resolved_by"
    ).prefetch_related(Prefetch("photos", queryset=TicketPhoto.objects.select_related("uploaded_by")))
    serializer_class = s.MaintenanceTicketSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends: list = []
    lookup_value_regex = UUID_REGEX
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    required_permissions = {
        "list": VIEW,
        "retrieve": VIEW,
        "create": REPORT,
        "photos": REPORT,
        "delete_photo": REPORT,
        "partial_update": REPAIR,
        "start": REPAIR,
        "resolve": REPAIR,
        "cancel": REPAIR,
        "destroy": SUPERVISE,
    }

    def payload(self, ticket) -> dict:
        return s.MaintenanceTicketSerializer(self.get_queryset().get(pk=ticket.pk)).data

    @extend_schema(parameters=TICKET_LIST_PARAMETERS)
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if statuses := choices_param(request, "status", MaintenanceTicket.Status.values):
            queryset = queryset.filter(status__in=statuses)
        if priorities := choices_param(request, "priority", Priority.values):
            queryset = queryset.filter(priority__in=priorities)
        if room_id := uuid_param(request, "room"):
            queryset = queryset.filter(room_id=room_id)
        if (condition := assignee_filter(request)) is not None:
            queryset = queryset.filter(condition)
        if (blocking := request.query_params.get("blocking")) is not None and blocking != "":
            queryset = queryset.filter(blocks_room=blocking in TRUE)
        if request.query_params.get("mine") in TRUE:
            queryset = queryset.filter(Q(reported_by=request.user) | Q(assigned_to=request.user))
        if text := request.query_params.get("q", "").strip():
            queryset = queryset.filter(
                Q(title__icontains=text)
                | Q(description__icontains=text)
                | Q(location__icontains=text)
                | Q(room__number__iexact=text)
            )
        queryset = queryset.annotate(
            _status_order=TICKET_STATUS_ORDER, _priority_order=selectors.PRIORITY_ORDER
        ).order_by("_status_order", "_priority_order", "-created_at")
        page = self.paginate_queryset(queryset)
        data = s.MaintenanceTicketSerializer(page if page is not None else queryset, many=True).data
        return self.get_paginated_response(data) if page is not None else Response(data)

    @extend_schema(
        request=s.MaintenanceTicketCreateSerializer, responses={201: s.MaintenanceTicketSerializer}
    )
    def create(self, request, *args, **kwargs):
        """Report a problem. `blocks_room` takes the room out of service from today until `blocked_until`
        (exclusive; tomorrow by default); over bookings → 409 `room_has_reservations` unless `force`
        (maintenance / supervisors)."""
        data = validated(s.MaintenanceTicketCreateSerializer, request.data)
        prop = request.property
        if data["force"] and not granted(request, *REPAIR):
            raise denied(MAINTENANCE)
        room = None
        if data.get("room_id"):
            room = Room.objects.select_related("property").filter(pk=data["room_id"], property=prop).first()
            if room is None:
                raise ValidationError({"room_id": ["La habitación no pertenece a este hotel"]})
        assignee = user_or_error(
            data.get("assigned_to_id"),
            field="assigned_to_id",
            message="Esa persona no atiende mantenimiento en este hotel",
        )
        photos = data.get("photos") or []
        tickets_svc.check_photos(photos)  # before writing anything
        with transaction.atomic():
            ticket = tickets_svc.create_ticket(
                prop,
                title=data["title"],
                room=room,
                description=data["description"],
                location=data["location"],
                priority=data["priority"],
                blocks_room=data["blocks_room"],
                blocked_until=data.get("blocked_until"),
                assigned_to=assignee,
                actor=request.user,
                force=data["force"],
            )
            for photo in photos:
                tickets_svc.add_photo(ticket, file=photo, actor=request.user)
        return Response(self.payload(ticket), status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        return Response(s.MaintenanceTicketSerializer(self.get_object()).data)

    @extend_schema(request=s.MaintenanceTicketUpdateSerializer, responses=s.MaintenanceTicketSerializer)
    def partial_update(self, request, *args, **kwargs):
        """Edit an open ticket; turning `blocks_room` on/off blocks or releases the room, a new
        `blocked_until` replaces the block."""
        data = dict(validated(s.MaintenanceTicketUpdateSerializer, request.data))
        force = data.pop("force")
        if "assigned_to_id" in data:
            data["assigned_to"] = user_or_error(
                data.pop("assigned_to_id"),
                field="assigned_to_id",
                message="Esa persona no atiende mantenimiento en este hotel",
            )
        ticket = tickets_svc.update_ticket(self.get_object(), data, actor=request.user, force=force)
        return Response(self.payload(ticket))

    def destroy(self, request, *args, **kwargs):
        tickets_svc.delete_ticket(self.get_object(), actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=None, responses=s.MaintenanceTicketSerializer)
    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        return Response(self.payload(tickets_svc.start_ticket(self.get_object(), actor=request.user)))

    @extend_schema(request=s.HkResolveSerializer, responses=s.MaintenanceTicketSerializer)
    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """Resolved: the block is released and the room goes to cleaning (`dirty` → its clean is created)."""
        data = validated(s.HkResolveSerializer, request.data)
        ticket = tickets_svc.resolve_ticket(self.get_object(), actor=request.user, notes=data["notes"])
        return Response(self.payload(ticket))

    @extend_schema(request=s.HkCancelSerializer, responses=s.MaintenanceTicketSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancelled: the block is released and the room gets back the status it had before the ticket."""
        data = validated(s.HkCancelSerializer, request.data)
        ticket = tickets_svc.cancel_ticket(self.get_object(), actor=request.user, reason=data["reason"])
        return Response(self.payload(ticket))

    def check_photo_rights(self, *, owner_id) -> None:
        """Maintenance and supervisors handle every photo; whoever reported / uploaded, their own."""
        if not (granted(self.request, *REPAIR) or owner_id == self.request.user.pk):
            raise denied(MAINTENANCE)

    @extend_schema(
        request={"multipart/form-data": s.HkPhotoUploadSerializer}, responses={201: s.HkTicketPhotoSerializer}
    )
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def photos(self, request, pk=None):
        """Add a photo (`image`: JPG, PNG, WebP or HEIC by content, ≤ 10 MB, 6 per ticket)."""
        ticket = self.get_object()
        self.check_photo_rights(owner_id=ticket.reported_by_id)
        image = validated(s.HkPhotoUploadSerializer, request.data)["image"]
        photo = tickets_svc.add_photo(ticket, file=image, actor=request.user)
        return Response(s.HkTicketPhotoSerializer(photo).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["delete"], url_path=rf"photos/(?P<photo_id>{UUID_REGEX})")
    def delete_photo(self, request, pk=None, photo_id=None):
        ticket = self.get_object()
        photo = TicketPhoto.objects.filter(pk=photo_id, ticket=ticket).first()
        if photo is None:
            raise NotFound("Foto no encontrada")
        self.check_photo_rights(owner_id=photo.uploaded_by_id)
        tickets_svc.delete_photo(photo, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TicketPhotoFileView(PropertyScopedAPIView):
    """`GET ticket-photos/<id>/file/` → the photo, streamed. The only way to read it (never under /media/);
    never cached, never content-sniffed."""

    required_permissions = {"get": VIEW}

    @extend_schema(responses={(200, "image/*"): OpenApiTypes.BINARY})
    def get(self, request, pk):
        photo = TicketPhoto.objects.filter(pk=pk, ticket__property=request.property).first()
        if photo is None:
            raise NotFound("Foto no encontrada")
        try:
            handle = photo.image.open("rb")
        except FileNotFoundError:
            raise NotFound("El archivo de la foto no está disponible") from None
        response = FileResponse(handle, content_type=photo.content_type)
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response
