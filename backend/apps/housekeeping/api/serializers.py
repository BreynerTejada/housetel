"""Serializers of the housekeeping API.

OpenAPI note: choice fields named like other apps' ones (`kind`, `status`, `priority`) are exposed as enums
only in the response components `HousekeepingTask` and `MaintenanceTicket` (one component per choice set, so
drf-spectacular names them `HousekeepingTaskKindEnum`, … without warnings); request serializers take them as
validated strings.
"""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.housekeeping.models import (
    HousekeepingSettings,
    HousekeepingTask,
    MaintenanceTicket,
    Priority,
    TicketPhoto,
)
from apps.inventory.models import Room


def validate_choice(value: str, choices, message: str) -> str:
    if value not in choices:
        raise serializers.ValidationError(message)
    return value


# ---- References ------------------------------------------------------------------------------------------


class HkRoomTypeRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.JSONField()
    color = serializers.CharField()
    kind = serializers.CharField()


class HkRoomRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    number = serializers.CharField()
    name = serializers.CharField()
    floor = serializers.CharField()
    housekeeping_status = serializers.CharField()
    room_type = HkRoomTypeRefSerializer()


class HkBedRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    label = serializers.CharField()


class HkUserRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    email = serializers.EmailField()


class HkReservationRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()


class HkArrivalSerializer(serializers.Serializer):
    code = serializers.CharField()
    eta = serializers.CharField(allow_null=True)
    is_vip = serializers.BooleanField()


# ---- Tasks -------------------------------------------------------------------------------------------------


class HousekeepingTaskSerializer(serializers.ModelSerializer):
    """A task with what the housekeeper needs: the room (live status), who arrives today, whether the guest of
    a departure is still in the room. Context: `day` (a `DayIndex`) and `business_date`."""

    room = HkRoomRefSerializer(read_only=True)
    bed = HkBedRefSerializer(read_only=True, allow_null=True)
    assigned_to = HkUserRefSerializer(read_only=True, allow_null=True)
    finished_by = HkUserRefSerializer(read_only=True, allow_null=True)
    reservation = HkReservationRefSerializer(read_only=True, allow_null=True)
    waiting_for_checkout = serializers.SerializerMethodField()
    arrival_today = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()

    class Meta:
        model = HousekeepingTask
        fields = [
            "id",
            "room",
            "bed",
            "kind",
            "status",
            "priority",
            "business_date",
            "assigned_to",
            "estimated_minutes",
            "started_at",
            "finished_at",
            "finished_by",
            "notes",
            "reservation",
            "created_source",
            "waiting_for_checkout",
            "arrival_today",
            "overdue",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_waiting_for_checkout(self, task) -> bool:
        return self.context["day"].waiting_for_checkout(task)

    @extend_schema_field(HkArrivalSerializer(allow_null=True))
    def get_arrival_today(self, task):
        return self.context["day"].arrival(task.room_id)

    def get_overdue(self, task) -> bool:
        return task.business_date < self.context["business_date"]


class HousekeepingTaskCreateSerializer(serializers.Serializer):
    room_id = serializers.UUIDField()
    kind = serializers.CharField()
    priority = serializers.CharField(default=Priority.NORMAL)
    notes = serializers.CharField(allow_blank=True, default="", max_length=2000)
    assigned_to_id = serializers.UUIDField(allow_null=True, required=False)
    bed_id = serializers.UUIDField(allow_null=True, required=False)
    estimated_minutes = serializers.IntegerField(min_value=5, max_value=600, allow_null=True, required=False)

    def validate_kind(self, value):
        return validate_choice(value, HousekeepingTask.Kind.values, "Tipo de tarea inválido")

    def validate_priority(self, value):
        return validate_choice(value, Priority.values, "Prioridad inválida")


class HousekeepingTaskUpdateSerializer(serializers.Serializer):
    priority = serializers.CharField(required=False)
    notes = serializers.CharField(allow_blank=True, max_length=2000, required=False)
    estimated_minutes = serializers.IntegerField(min_value=5, max_value=600, required=False)

    def validate_priority(self, value):
        return validate_choice(value, Priority.values, "Prioridad inválida")


class HkFinishSerializer(serializers.Serializer):
    notes = serializers.CharField(allow_blank=True, default="", max_length=2000)


class HkInspectSerializer(serializers.Serializer):
    passed = serializers.BooleanField(default=True)
    notes = serializers.CharField(allow_blank=True, default="", max_length=2000)


class HkAssignSerializer(serializers.Serializer):
    user_id = serializers.UUIDField(allow_null=True)


class HkCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=True, default="", max_length=500)


class HkAutoAssignSerializer(serializers.Serializer):
    user_ids = serializers.ListField(child=serializers.UUIDField(), required=False, allow_empty=False)


class HkStaffLoadSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    full_name = serializers.CharField()
    minutes = serializers.IntegerField()
    tasks = serializers.IntegerField()


class HkAutoAssignReportSerializer(serializers.Serializer):
    business_date = serializers.DateField()
    assigned = serializers.IntegerField()
    unassigned = serializers.IntegerField()
    staff = HkStaffLoadSerializer(many=True)
    overloaded = serializers.ListField(child=serializers.UUIDField())
    minutes_per_shift = serializers.IntegerField()


class HkGenerateReportSerializer(serializers.Serializer):
    created = serializers.IntegerField()
    stayovers = serializers.IntegerField()
    departures = serializers.IntegerField()
    dirty_rooms = serializers.IntegerField()
    rooms_marked_dirty = serializers.IntegerField()


# ---- Board, summary, staff, settings -----------------------------------------------------------------------


class HkInHouseSerializer(serializers.Serializer):
    code = serializers.CharField()
    checkout_date = serializers.DateField()
    departs_today = serializers.BooleanField()
    guests = serializers.IntegerField()
    is_vip = serializers.BooleanField()


class HkBlockSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    reason = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class HkBoardRoomSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    number = serializers.CharField()
    name = serializers.CharField()
    floor = serializers.CharField()
    housekeeping_status = serializers.CharField()
    room_type = HkRoomTypeRefSerializer()
    occupied = serializers.BooleanField()
    in_house = HkInHouseSerializer(allow_null=True)
    arrival_today = HkArrivalSerializer(allow_null=True)
    tasks = HousekeepingTaskSerializer(many=True)
    active_block = HkBlockSerializer(allow_null=True)
    open_tickets = serializers.IntegerField()


class HkBoardFloorSerializer(serializers.Serializer):
    floor = serializers.CharField()
    rooms = HkBoardRoomSerializer(many=True)


class HkRoomCountsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    clean = serializers.IntegerField()
    dirty = serializers.IntegerField()
    inspected = serializers.IntegerField()
    out_of_service = serializers.IntegerField()
    occupied = serializers.IntegerField()


class HkTaskCountsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    pending = serializers.IntegerField()
    in_progress = serializers.IntegerField()
    done = serializers.IntegerField()
    inspections_pending = serializers.IntegerField()
    unassigned = serializers.IntegerField()


class HkMinutesSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    done = serializers.IntegerField()


class HkTicketCountsSerializer(serializers.Serializer):
    open = serializers.IntegerField()
    blocking = serializers.IntegerField()


class HousekeepingSummarySerializer(serializers.Serializer):
    business_date = serializers.DateField()
    rooms = HkRoomCountsSerializer()
    tasks = HkTaskCountsSerializer()
    minutes = HkMinutesSerializer()
    tickets = HkTicketCountsSerializer()


class HkHousekeeperSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    email = serializers.EmailField()
    minutes = serializers.IntegerField()
    minutes_done = serializers.IntegerField()
    tasks = serializers.IntegerField()
    tasks_done = serializers.IntegerField()


class HkTechnicianSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    email = serializers.EmailField()
    open_tickets = serializers.IntegerField()


class HousekeepingStaffSerializer(serializers.Serializer):
    housekeepers = HkHousekeeperSerializer(many=True)
    maintenance = HkTechnicianSerializer(many=True)


class HousekeepingSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = HousekeepingSettings
        fields = ["stayover_frequency_days", "require_inspection", "auto_assign", "minutes_per_shift"]
        extra_kwargs = {
            "stayover_frequency_days": {"min_value": 0, "max_value": 30},
            "minutes_per_shift": {"min_value": 60, "max_value": 900},
        }


class HousekeepingBoardSerializer(serializers.Serializer):
    business_date = serializers.DateField()
    settings = HousekeepingSettingsSerializer()
    summary = HousekeepingSummarySerializer()
    staff = HkHousekeeperSerializer(many=True)
    floors = HkBoardFloorSerializer(many=True)


class HkRoomStatusSerializer(serializers.Serializer):
    # Same choices (values and labels) as inventory's Room.housekeeping_status → one shared OpenAPI enum.
    housekeeping_status = serializers.ChoiceField(choices=Room.HousekeepingStatus.choices)


class HkRoomStatusResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    number = serializers.CharField()
    housekeeping_status = serializers.CharField()


# ---- Tickets -----------------------------------------------------------------------------------------------


class HkTicketPhotoSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    uploaded_by = HkUserRefSerializer(read_only=True, allow_null=True)

    class Meta:
        model = TicketPhoto
        fields = ["id", "content_type", "size", "file_url", "uploaded_by", "created_at"]
        read_only_fields = fields

    def get_file_url(self, photo) -> str:
        return f"/api/v1/housekeeping/ticket-photos/{photo.pk}/file/"


class HkTicketBlockSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    released_at = serializers.DateTimeField(allow_null=True)


class MaintenanceTicketSerializer(serializers.ModelSerializer):
    room = HkRoomRefSerializer(read_only=True, allow_null=True)
    block = HkTicketBlockSerializer(read_only=True, allow_null=True)
    reported_by = HkUserRefSerializer(read_only=True, allow_null=True)
    assigned_to = HkUserRefSerializer(read_only=True, allow_null=True)
    resolved_by = HkUserRefSerializer(read_only=True, allow_null=True)
    photos = HkTicketPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = MaintenanceTicket
        fields = [
            "id",
            "room",
            "location",
            "title",
            "description",
            "priority",
            "status",
            "blocks_room",
            "blocked_until",
            "block",
            "reported_by",
            "assigned_to",
            "started_at",
            "resolved_at",
            "resolved_by",
            "resolution_notes",
            "photos",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class MaintenanceTicketCreateSerializer(serializers.Serializer):
    room_id = serializers.UUIDField(allow_null=True, required=False)
    location = serializers.CharField(allow_blank=True, default="", max_length=120)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(allow_blank=True, default="", max_length=4000)
    priority = serializers.CharField(default=Priority.NORMAL)
    blocks_room = serializers.BooleanField(default=False)
    blocked_until = serializers.DateField(allow_null=True, required=False)
    assigned_to_id = serializers.UUIDField(allow_null=True, required=False)
    force = serializers.BooleanField(default=False)
    photos = serializers.ListField(child=serializers.FileField(), required=False, max_length=6)

    def validate_priority(self, value):
        return validate_choice(value, Priority.values, "Prioridad inválida")


class MaintenanceTicketUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(allow_blank=True, max_length=4000, required=False)
    location = serializers.CharField(allow_blank=True, max_length=120, required=False)
    priority = serializers.CharField(required=False)
    blocks_room = serializers.BooleanField(required=False)
    blocked_until = serializers.DateField(allow_null=True, required=False)
    assigned_to_id = serializers.UUIDField(allow_null=True, required=False)
    force = serializers.BooleanField(default=False)

    def validate_priority(self, value):
        return validate_choice(value, Priority.values, "Prioridad inválida")


class HkResolveSerializer(serializers.Serializer):
    notes = serializers.CharField(allow_blank=True, default="", max_length=4000)


class HkPhotoUploadSerializer(serializers.Serializer):
    image = serializers.FileField()
