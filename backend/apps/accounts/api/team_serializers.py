from rest_framework import serializers

from apps.accounts.models import Invitation, Membership, Role
from apps.accounts.team import Grantor, invitation_status, invitation_url, is_owner_role


def grantor_of(request) -> Grantor:
    """What the requesting member may hand out (computed once per request; see apps.accounts.team)."""
    if request is None:
        return Grantor.of(None)
    grantor = getattr(request, "_team_grantor", None)
    if grantor is None:
        grantor = Grantor.of(getattr(request, "membership", None))
        request._team_grantor = grantor
    return grantor


class TeamRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "code", "name", "is_system"]
        read_only_fields = fields


class PropertyNameSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class MemberUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    full_name = serializers.CharField()
    phone = serializers.CharField()
    last_login = serializers.DateTimeField(allow_null=True)


class MemberSerializer(serializers.ModelSerializer):
    """A person of the team = their membership in the organization (`id` is the membership id)."""

    user = MemberUserSerializer(read_only=True)
    role = TeamRoleSerializer(read_only=True)
    properties = PropertyNameSerializer(many=True, read_only=True)
    is_owner = serializers.SerializerMethodField()
    is_self = serializers.SerializerMethodField()
    editable = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = [
            "id", "user", "role", "all_properties", "properties", "is_active", "is_owner", "is_self",
            "editable", "created_at",
        ]  # fmt: skip
        read_only_fields = fields

    def get_is_owner(self, membership) -> bool:
        return is_owner_role(membership.role)

    def get_is_self(self, membership) -> bool:
        request = self.context.get("request")
        return membership.user_id == getattr(getattr(request, "user", None), "pk", None)

    def get_editable(self, membership) -> bool:
        """The current user may change this person: their role and hotels fit inside the user's."""
        return grantor_of(self.context.get("request")).can_manage(membership)


class InviteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role_id = serializers.UUIDField()
    all_properties = serializers.BooleanField(default=True)
    property_ids = serializers.ListField(child=serializers.UUIDField(), default=list)


class MemberUpdateSerializer(serializers.Serializer):
    role_id = serializers.UUIDField(required=False)
    all_properties = serializers.BooleanField(required=False)
    property_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    is_active = serializers.BooleanField(required=False)


class InvitedBySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    email = serializers.EmailField()


class InvitationSerializer(serializers.ModelSerializer):
    """`editable`: the current user may resend, replace or revoke it (its role and hotels fit inside theirs).
    `invite_url` is shown only while the invitation is pending and only to someone who could have sent it:
    the link is a bearer secret (whoever opens it can create that account and join with that access)."""

    role = TeamRoleSerializer(read_only=True)
    properties = PropertyNameSerializer(many=True, read_only=True)
    invited_by = InvitedBySerializer(read_only=True, allow_null=True)
    status = serializers.SerializerMethodField()
    invite_url = serializers.SerializerMethodField()
    editable = serializers.SerializerMethodField()

    class Meta:
        model = Invitation
        fields = [
            "id", "email", "role", "all_properties", "properties", "status", "expires_at", "invited_by",
            "created_at", "invite_url", "editable",
        ]  # fmt: skip
        read_only_fields = fields

    def get_status(self, invitation) -> str:
        return invitation_status(invitation)

    def get_editable(self, invitation) -> bool:
        return grantor_of(self.context.get("request")).can_manage(invitation)

    def get_invite_url(self, invitation) -> str | None:
        if invitation_status(invitation) != "pending" or not self.get_editable(invitation):
            return None
        return invitation_url(invitation)


class InvitationSentSerializer(InvitationSerializer):
    email_sent = serializers.BooleanField(read_only=True)

    class Meta(InvitationSerializer.Meta):
        fields = [*InvitationSerializer.Meta.fields, "email_sent"]
        read_only_fields = fields


class RoleSerializer(serializers.ModelSerializer):
    members_count = serializers.IntegerField(read_only=True)
    assignable = serializers.SerializerMethodField()
    editable = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            "id", "code", "name", "description", "is_system", "permissions", "members_count", "assignable",
            "editable", "created_at",
        ]  # fmt: skip
        read_only_fields = fields

    def get_assignable(self, role) -> bool:
        """The current user may assign this role (or invite with it)."""
        return grantor_of(self.context.get("request")).covers_permissions(role.permissions)

    def get_editable(self, role) -> bool:
        return not role.is_system and grantor_of(self.context.get("request")).covers_permissions(
            role.permissions
        )


class RoleWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    permissions = serializers.ListField(child=serializers.CharField(max_length=100), default=list)


class PermissionItemSerializer(serializers.Serializer):
    code = serializers.CharField()
    label_es = serializers.CharField()
    label_en = serializers.CharField()


class PermissionModuleSerializer(serializers.Serializer):
    code = serializers.CharField()
    label_es = serializers.CharField()
    label_en = serializers.CharField()
    permissions = PermissionItemSerializer(many=True)


class PublicInvitationSerializer(serializers.Serializer):
    """What the invitee sees on `/invite/<token>` (no token, no internal ids)."""

    email = serializers.EmailField()
    organization = serializers.DictField()
    role = serializers.DictField()
    properties = serializers.ListField(child=serializers.CharField())
    all_properties = serializers.BooleanField()
    invited_by = serializers.CharField(allow_blank=True)
    expires_at = serializers.DateTimeField()
    status = serializers.ChoiceField(choices=["pending", "expired", "accepted"])
    user_exists = serializers.BooleanField()


class AcceptInvitationSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    password = serializers.CharField(max_length=128, trim_whitespace=False)
