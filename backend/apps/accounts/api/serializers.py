from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import User


# Documentation-only shapes of `Me.memberships` (spec §3) and of the property context
# (apps.core.api.views.PropertyContextView); the payloads themselves are built by the *_payload() helpers.
class OrganizationRef(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    status = serializers.CharField()


class RoleRef(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    code = serializers.CharField()


class PropertyRef(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    property_type = serializers.CharField()
    timezone = serializers.CharField()
    currency = serializers.CharField()
    business_date = serializers.DateField()


class MembershipInfoSerializer(serializers.Serializer):
    organization = OrganizationRef()
    role = RoleRef()
    permissions = serializers.ListField(child=serializers.CharField())
    properties = PropertyRef(many=True)


def property_payload(prop) -> dict:
    return {
        "id": str(prop.pk),
        "name": prop.name,
        "slug": prop.slug,
        "property_type": prop.property_type,
        "timezone": prop.timezone,
        "currency": prop.currency,
        "business_date": prop.business_date.isoformat() if prop.business_date else None,
    }


def organization_payload(org) -> dict:
    return {"id": str(org.pk), "name": org.name, "slug": org.slug, "status": org.status}


def role_payload(role) -> dict:
    return {"id": str(role.pk), "name": role.name, "code": role.code}


def membership_payload(membership) -> dict:
    org = membership.organization
    properties = org.properties.all() if membership.all_properties else membership.properties.all()
    return {
        "organization": organization_payload(org),
        "role": role_payload(membership.role),
        # Stored as-is (patterns like "bookings.*" or "*" included); the frontend matches them with fnmatch.
        "permissions": list(membership.role.permissions or []),
        "properties": [
            property_payload(p) for p in sorted(properties, key=lambda p: (p.name.lower(), str(p.pk)))
        ],
    }


class MeSerializer(serializers.ModelSerializer):
    """`Me` (spec §3): {id, email, full_name, language, phone, is_platform_admin, memberships: [...]}.

    Additions to the spec shape: `phone` (PATCH /me/ writes it, A3) and `email_verified` +
    `email_verified_at` (P2: the app asks unverified users to confirm their address)."""

    memberships = serializers.SerializerMethodField()
    email_verified = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "full_name", "language", "phone", "is_platform_admin", "email_verified",
            "email_verified_at", "memberships",
        ]  # fmt: skip
        read_only_fields = fields

    @extend_schema_field(MembershipInfoSerializer(many=True))
    def get_memberships(self, user) -> list[dict]:
        memberships = (
            user.memberships.filter(is_active=True)
            .select_related("organization", "role")
            .prefetch_related("properties", "organization__properties")
        )
        return [
            membership_payload(m)
            for m in sorted(memberships, key=lambda m: (m.organization.name.lower(), str(m.organization.pk)))
        ]


class MeUpdateSerializer(serializers.ModelSerializer):
    """PATCH /me/: only `full_name`, `language` and `phone` are writable."""

    class Meta:
        model = User
        fields = ["full_name", "language", "phone"]


class LoginSerializer(serializers.Serializer):
    email = serializers.CharField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False)
