"""Team API (B3): `/api/v1/accounts/users|invitations|roles|permissions/` (staff, scoped to the
organization of the `X-Property-Id` property) and `/api/v1/public/accounts/invitations/<token>/`."""

from django.contrib.auth import login
from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.api.serializers import MeSerializer
from apps.accounts.api.team_serializers import (
    AcceptInvitationSerializer,
    InvitationSentSerializer,
    InvitationSerializer,
    InviteSerializer,
    MemberSerializer,
    MemberUpdateSerializer,
    PermissionModuleSerializer,
    PublicInvitationSerializer,
    RoleSerializer,
    RoleWriteSerializer,
    grantor_of,
)
from apps.accounts.catalog import permission_catalog
from apps.accounts.models import Invitation, Membership, Role, User
from apps.accounts.team import (
    accept_invitation,
    create_role,
    delete_role,
    duplicate_role,
    find_invitation,
    invitation_status,
    invite_member,
    resend_invitation,
    revoke_invitation,
    send_invitation_email,
    update_membership,
    update_role,
)
from apps.core.api.authentication import enforce_csrf
from apps.core.errors import DomainError
from apps.core.models import Property
from apps.core.permissions import codes_match
from apps.core.tenancy import OrganizationScopedMixin, PropertyScopedAPIView


def _resolve_role(organization, role_id) -> Role:
    role = Role.objects.filter(pk=role_id, organization=organization).first() if role_id else None
    if role is None:
        raise DomainError(
            "Rol inválido", code="validation_error", fields={"role_id": ["Elige un rol de la lista"]}
        )
    return role


def _resolve_properties(organization, property_ids) -> list[Property]:
    ids = list(dict.fromkeys(property_ids or []))
    properties = list(Property.objects.filter(pk__in=ids, organization=organization))
    if len(properties) != len(ids):
        raise DomainError(
            "Hay hoteles que no son de la organización",
            code="validation_error",
            fields={"property_ids": ["Elige hoteles de tu organización"]},
        )
    return properties


def _sent(invitation, request, email_sent: bool):
    invitation.email_sent = email_sent
    return InvitationSentSerializer(invitation, context={"request": request}).data


@extend_schema_view(
    list=extend_schema(responses=MemberSerializer(many=True)),
    create=extend_schema(request=InviteSerializer, responses={201: InvitationSentSerializer}),
    partial_update=extend_schema(request=MemberUpdateSerializer, responses=MemberSerializer),
)
class MemberViewSet(
    OrganizationScopedMixin, mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    """`GET users/` (team), `POST users/` (invite by email), `PATCH users/<membership_id>/` (role, hotels,
    active). Permission `accounts.users_manage`."""

    queryset = Membership.objects.select_related("user", "role").prefetch_related("properties")
    serializer_class = MemberSerializer
    required_permissions = {"*": "accounts.users_manage"}
    allow_suspended = True  # spec §3: accounts stays reachable while the organization is suspended
    http_method_names = ["get", "post", "patch", "head", "options"]
    filter_backends: list = []

    def get_queryset(self):
        return super().get_queryset().order_by("-is_active", "user__full_name", "user__email")

    def create(self, request, *args, **kwargs):
        serializer = InviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        organization = request.organization
        invitation = invite_member(
            organization,
            email=data["email"],
            role=_resolve_role(organization, data["role_id"]),
            all_properties=data["all_properties"],
            properties=_resolve_properties(organization, data["property_ids"]),
            actor=request.user,
            grantor=grantor_of(request),
        )
        email_sent = send_invitation_email(invitation)
        return Response(_sent(invitation, request, email_sent), status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        membership = self.get_object()
        serializer = MemberUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        organization = request.organization
        updated = update_membership(
            membership,
            actor=request.user,
            grantor=grantor_of(request),
            role=_resolve_role(organization, data["role_id"]) if "role_id" in data else None,
            all_properties=data.get("all_properties"),
            properties=_resolve_properties(organization, data["property_ids"])
            if "property_ids" in data
            else None,
            is_active=data.get("is_active"),
        )
        updated = self.get_queryset().get(pk=updated.pk)
        return Response(MemberSerializer(updated, context=self.get_serializer_context()).data)


@extend_schema_view(
    list=extend_schema(responses=InvitationSerializer(many=True)),
    destroy=extend_schema(responses={204: None}),
)
class InvitationViewSet(
    OrganizationScopedMixin, mixins.ListModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    """Invitations not accepted yet (pending or expired): list, `POST <id>/resend/`, `DELETE <id>/`."""

    queryset = Invitation.objects.select_related("role", "invited_by").prefetch_related("properties")
    serializer_class = InvitationSerializer
    required_permissions = {"*": "accounts.users_manage"}
    allow_suspended = True
    pagination_class = None
    filter_backends: list = []

    def get_queryset(self):
        return super().get_queryset().filter(accepted_at__isnull=True).order_by("-created_at")

    def perform_destroy(self, instance):
        revoke_invitation(instance, actor=self.request.user, grantor=grantor_of(self.request))

    @extend_schema(request=None, responses=InvitationSentSerializer)
    @action(detail=True, methods=["post"])
    def resend(self, request, pk=None):
        invitation = resend_invitation(self.get_object(), actor=request.user, grantor=grantor_of(request))
        return Response(_sent(invitation, request, send_invitation_email(invitation)))


@extend_schema_view(
    create=extend_schema(request=RoleWriteSerializer, responses={201: RoleSerializer}),
    update=extend_schema(request=RoleWriteSerializer, responses=RoleSerializer),
    partial_update=extend_schema(request=RoleWriteSerializer, responses=RoleSerializer),
)
class RoleViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    """Roles of the organization. Reading needs `accounts.roles_manage` or `accounts.users_manage` (to assign
    them); writing needs `accounts.roles_manage`. System roles are read-only; `POST <id>/duplicate/`."""

    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    required_permissions = {"list": None, "retrieve": None, "*": "accounts.roles_manage"}
    allow_suspended = True
    pagination_class = None
    filter_backends: list = []

    def get_required_permission(self):
        if self.action in ("list", "retrieve"):
            return None  # checked in `initial`: either accounts permission may read
        return super().get_required_permission()

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if self.action in ("list", "retrieve"):
            granted = list(request.membership.role.permissions or [])
            if not any(
                codes_match(granted, code) for code in ("accounts.roles_manage", "accounts.users_manage")
            ):
                raise PermissionDenied(
                    {"detail": "No tienes permiso para esta acción", "code": "permission_denied",
                     "permission": "accounts.roles_manage"}
                )  # fmt: skip

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(members_count=Count("memberships", filter=Q(memberships__is_active=True)))
            .order_by("-is_system", "name")
        )

    def create(self, request, *args, **kwargs):
        serializer = RoleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = create_role(
            request.organization,
            actor=request.user,
            grantor=grantor_of(request),
            **serializer.validated_data,
        )
        return Response(self._render(role), status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        role = self.get_object()
        serializer = RoleWriteSerializer(data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)  # partial: only the fields sent (no defaults)
        role = update_role(role, actor=request.user, grantor=grantor_of(request), **serializer.validated_data)
        return Response(self._render(role))

    def destroy(self, request, *args, **kwargs):
        delete_role(self.get_object(), actor=request.user, grantor=grantor_of(request))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=None, responses={201: RoleSerializer})
    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        role = duplicate_role(self.get_object(), actor=request.user, grantor=grantor_of(request))
        return Response(self._render(role), status=status.HTTP_201_CREATED)

    def _render(self, role):
        return RoleSerializer(self.get_queryset().get(pk=role.pk), context=self.get_serializer_context()).data


class PermissionCatalogView(PropertyScopedAPIView):
    """`GET permissions/` → the permission catalog grouped by module (any member)."""

    required_permissions: dict = {}
    allow_suspended = True

    @extend_schema(responses=PermissionModuleSerializer(many=True))
    def get(self, request):
        return Response(permission_catalog())


def _public_payload(invitation) -> dict:
    inviter = invitation.invited_by
    return {
        "email": invitation.email,
        "organization": {"name": invitation.organization.name},
        "role": {"name": invitation.role.name, "code": invitation.role.code},
        "properties": sorted(p.name for p in invitation.properties.all()),
        "all_properties": invitation.all_properties,
        "invited_by": (inviter.full_name or inviter.email) if inviter else "",
        "expires_at": invitation.expires_at,
        "status": invitation_status(invitation),
        "user_exists": User.objects.filter(email__iexact=invitation.email).exists(),
    }


class PublicInvitationView(APIView):
    """`GET /api/v1/public/accounts/invitations/<token>/` → what the invitee accepts (404 unknown link)."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(responses=PublicInvitationSerializer, auth=[])
    def get(self, request, token):
        return Response(PublicInvitationSerializer(_public_payload(find_invitation(token))).data)


class AcceptInvitationView(APIView):
    """`POST .../invitations/<token>/accept/` `{full_name, password}` → `Me` and a new session.

    A new user sets their name and password; an existing Housetel user confirms with their current password.
    CSRF is required (like login) and attempts are throttled with the login rate."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(request=AcceptInvitationSerializer, responses=MeSerializer, auth=[])
    def post(self, request, token):
        enforce_csrf(request)
        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = accept_invitation(token, **serializer.validated_data)
        login(request._request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(MeSerializer(user).data)
