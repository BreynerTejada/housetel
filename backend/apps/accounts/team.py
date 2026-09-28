"""Team management (B3): invitations, memberships and custom roles of an organization.

Two protections apply everywhere:
- nobody hands out what they do not have (`PermissionEscalation`, 403 `permission_escalation`): they
  cannot create, assign or edit a role — or edit a member — with permissions they lack
  (apps.accounts.catalog.covers), and a member restricted to some hotels only grants access to those hotels
  (never "all hotels") and only edits members whose access fits inside theirs (see `Grantor`). Pending
  invitations follow the same rule: only someone whose reach covers an invitation's role and hotels may
  resend, replace or revoke it;
- an organization always keeps at least one active owner (409 `last_owner`).
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, field

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.accounts.catalog import covers, unknown_permissions
from apps.accounts.models import Invitation, Membership, Role, User, _invitation_expiry, _invitation_token
from apps.accounts.services import add_member
from apps.core import audit
from apps.core.errors import ConflictError, DomainError, NotFoundError
from apps.core.runtime import public_base_url

logger = logging.getLogger("housetel.accounts")

OWNER_ROLE = "owner"


class PermissionEscalation(DomainError):
    code = "permission_escalation"
    status_code = 403


@dataclass(frozen=True)
class Grantor:
    """What the acting member may hand out: the permissions of their role and the hotels they reach."""

    permissions: tuple[str, ...] = ()
    all_properties: bool = True
    property_ids: frozenset = field(default_factory=frozenset)

    @classmethod
    def of(cls, membership: Membership | None) -> "Grantor":
        if membership is None:
            return cls(all_properties=False)  # grants nothing
        return cls(
            permissions=tuple(membership.role.permissions or []),
            all_properties=membership.all_properties,
            property_ids=frozenset()
            if membership.all_properties
            else frozenset(membership.properties.values_list("pk", flat=True)),
        )

    def covers_permissions(self, permissions) -> bool:
        return covers(list(self.permissions), list(permissions or []))

    def covers_hotels(self, all_properties: bool, property_ids) -> bool:
        """True when access to these hotels fits inside the grantor's ("all hotels" only fits in "all")."""
        if self.all_properties:
            return True
        return not all_properties and set(property_ids) <= self.property_ids

    def can_manage(self, access: Membership | Invitation) -> bool:
        """The role and hotels of a member (or of a pending invitation) fit inside the grantor's: they may
        edit that person (or resend, replace or revoke that invitation)."""
        return self.covers_permissions(access.role.permissions) and self.covers_hotels(
            access.all_properties, [p.pk for p in access.properties.all()]
        )


def _ensure_covers(grantor: Grantor, permissions, message: str) -> None:
    if not grantor.covers_permissions(permissions):
        raise PermissionEscalation(message)


def _ensure_covers_hotels(grantor: Grantor, all_properties: bool, properties, message: str) -> None:
    if not grantor.covers_hotels(all_properties, [p.pk for p in properties]):
        raise PermissionEscalation(message)


HOTELS_MESSAGE = "No puedes dar acceso a hoteles a los que tú no tienes acceso"


def _ensure_can_manage_invitation(grantor: Grantor, invitation: Invitation, message: str) -> None:
    """An invitation hands its role and hotels out: only someone whose reach covers them may resend,
    replace or revoke it (same rule as editing a member)."""
    _ensure_covers(grantor, invitation.role.permissions, message)
    _ensure_covers_hotels(grantor, invitation.all_properties, invitation.properties.all(), HOTELS_MESSAGE)


def is_owner_role(role: Role) -> bool:
    return role.is_system and role.code == OWNER_ROLE


def invitation_url(invitation: Invitation) -> str:
    return f"{public_base_url()}/invite/{invitation.token}"


def invitation_status(invitation: Invitation) -> str:
    if invitation.accepted_at:
        return "accepted"
    return "expired" if invitation.expires_at <= timezone.now() else "pending"


def _validate_properties(organization, all_properties: bool, properties) -> list:
    properties = list(properties or [])
    if any(p.organization_id != organization.pk for p in properties):
        raise DomainError(
            "Hay hoteles que no son de la organización",
            code="validation_error",
            fields={"property_ids": ["Elige hoteles de tu organización"]},
        )
    if not all_properties and not properties:
        raise DomainError(
            "Elige al menos un hotel",
            code="validation_error",
            fields={"property_ids": ["Elige al menos un hotel o marca todos los hoteles"]},
        )
    return [] if all_properties else properties


def _validate_role(organization, role: Role) -> None:
    if role.organization_id != organization.pk:
        raise DomainError(
            "El rol no es de la organización", code="validation_error", fields={"role_id": ["Rol inválido"]}
        )


# ---- Invitations ----------------------------------------------------------------------------------------


def send_invitation_email(invitation: Invitation) -> bool:
    """Plain-text invitation (Spanish, English below). Returns False if the mail server failed: the
    invitation still exists and its link can be shared by hand."""
    organization, role = invitation.organization, invitation.role
    inviter = invitation.invited_by.full_name or invitation.invited_by.email if invitation.invited_by else ""
    url = invitation_url(invitation)
    expires = timezone.localtime(invitation.expires_at).strftime("%d/%m/%Y")
    who = f"{inviter} te invitó" if inviter else "Te invitaron"
    body = (
        f"Hola:\n\n{who} a unirte a {organization.name} en Housetel con el rol «{role.name}».\n\n"
        f"Acepta la invitación aquí (vence el {expires}):\n{url}\n\n"
        "Si no esperabas este correo, puedes ignorarlo.\n\n—\n"
        f"You have been invited to join {organization.name} on Housetel as “{role.name}”. "
        f"Accept the invitation (expires {expires}):\n{url}\n"
    )
    try:
        send_mail(f"Te invitaron a {organization.name} en Housetel", body, None, [invitation.email])
    except Exception:  # SMTP down, bad address…: the invitation stays valid
        logger.exception("Could not send invitation %s", invitation.pk)
        return False
    return True


def invite_member(
    organization,
    *,
    email: str,
    role: Role,
    all_properties: bool = True,
    properties=None,
    actor,
    grantor: Grantor,
) -> Invitation:
    """Create (or refresh, if one is pending for the email) an invitation. The caller sends the email.
    Refreshing replaces the pending invitation, so its current role and hotels must be within the grantor's
    reach too (nobody downgrades or redirects an invitation sent by someone with more access)."""
    email = (email or "").strip().lower()
    _validate_role(organization, role)
    _ensure_covers(grantor, role.permissions, "No puedes asignar un rol con permisos que no tienes")
    properties = _validate_properties(organization, all_properties, properties)
    _ensure_covers_hotels(grantor, all_properties, properties, HOTELS_MESSAGE)
    if Membership.objects.filter(
        organization=organization, user__email__iexact=email, is_active=True
    ).exists():
        raise ConflictError("Esa persona ya es parte del equipo", code="already_member")
    with transaction.atomic():
        invitation = (
            Invitation.objects.select_for_update()
            .select_related("role")
            .filter(organization=organization, email__iexact=email, accepted_at__isnull=True)
            .first()
        )
        if invitation is None:
            invitation = Invitation(organization=organization, email=email)
        else:
            _ensure_can_manage_invitation(
                grantor, invitation, "Ya hay una invitación pendiente con permisos que no tienes"
            )
        invitation.role = role
        invitation.all_properties = all_properties
        invitation.invited_by = actor
        invitation.token = _invitation_token()
        invitation.expires_at = _invitation_expiry()
        invitation.save()
        invitation.properties.set(properties)
        audit.record(
            action="accounts.member_invited",
            target=invitation,
            summary=f"Invitó a {email} como {role.name}",
            actor=actor,
            organization=organization,
            changes={"email": email, "role": role.code},
        )
    return invitation


def resend_invitation(invitation: Invitation, *, actor, grantor: Grantor) -> Invitation:
    """New link (the old one stops working) valid for 7 more days. The caller sends the email. Resending
    hands the access out again, so the invitation must fit inside what the grantor may give."""
    if invitation.accepted_at:
        raise ConflictError("La invitación ya fue aceptada", code="invitation_used")
    _ensure_can_manage_invitation(grantor, invitation, "No puedes reenviar un rol con permisos que no tienes")
    invitation.token = _invitation_token()
    invitation.expires_at = _invitation_expiry()
    invitation.save(update_fields=["token", "expires_at", "updated_at"])
    audit.record(
        action="accounts.invitation_resent",
        target=invitation,
        summary=f"Reenvió la invitación de {invitation.email}",
        actor=actor,
        organization=invitation.organization,
    )
    return invitation


def revoke_invitation(invitation: Invitation, *, actor, grantor: Grantor) -> None:
    _ensure_can_manage_invitation(grantor, invitation, "No puedes revocar un rol con permisos que no tienes")
    audit.record(
        action="accounts.invitation_revoked",
        target=invitation,
        summary=f"Revocó la invitación de {invitation.email}",
        actor=actor,
        organization=invitation.organization,
    )
    invitation.delete()


def find_invitation(token: str) -> Invitation:
    invitation = (
        Invitation.objects.select_related("organization", "role", "invited_by").filter(token=token).first()
        if token
        else None
    )
    if invitation is None:
        raise NotFoundError("Invitación no encontrada")
    return invitation


def accept_invitation(token: str, *, full_name: str = "", password: str = "") -> User:
    """Accept an invitation: a new user is created with `full_name` + `password`; an existing Housetel user
    proves it is them with their CURRENT password (an invitation never resets a password). Returns the user
    (the caller starts the session)."""
    with transaction.atomic():
        invitation = find_invitation(token)
        invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
        if invitation.accepted_at:
            raise ConflictError("Esta invitación ya fue usada", code="invitation_used")
        if invitation.expires_at <= timezone.now():
            raise ConflictError("La invitación venció; pide que te la reenvíen", code="invitation_expired")
        user = User.objects.filter(email__iexact=invitation.email).first()
        if user is not None:
            if not (user.is_active and user.check_password(password or "")):
                raise DomainError(
                    "La contraseña no coincide con tu cuenta de Housetel", code="invalid_credentials"
                )
            if Membership.objects.filter(
                user=user, organization=invitation.organization, is_active=True
            ).exists():  # an invitation never changes the role of someone already in the team
                raise ConflictError(
                    f"Ya eres parte de {invitation.organization.name}; inicia sesión", code="already_member"
                )
            fields = []
            if full_name.strip() and not user.full_name:
                user.full_name = full_name.strip()
                fields.append("full_name")
            if user.email_verified_at is None:  # the invitation link reached this address (P2)
                user.email_verified_at = timezone.now()
                fields.append("email_verified_at")
            if fields:
                user.save(update_fields=[*fields, "updated_at"])
        else:
            user = _create_invited_user(invitation.email, full_name, password)
        membership = add_member(
            invitation.organization,
            user,
            invitation.role.code,
            all_properties=invitation.all_properties,
            properties=list(invitation.properties.all()),
        )
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["accepted_at", "updated_at"])
        audit.record(
            action="accounts.invitation_accepted",
            target=membership,
            summary=f"{user.email} aceptó la invitación como {invitation.role.name}",
            actor=user,
            organization=invitation.organization,
        )
    return user


def _create_invited_user(email: str, full_name: str, password: str) -> User:
    errors = {}
    if not full_name.strip():
        errors["full_name"] = ["Escribe tu nombre"]
    try:
        validate_password(password or "", user=User(email=email, full_name=full_name.strip()))
    except DjangoValidationError as exc:
        errors["password"] = list(exc.messages)
    if errors:
        raise DomainError(next(iter(errors.values()))[0], code="validation_error", fields=errors)
    # Born verified (P2): the invitation was emailed to this address, so no verification email follows.
    return User.objects.create_user(
        email, password, full_name=full_name.strip(), email_verified_at=timezone.now()
    )


# ---- Memberships ----------------------------------------------------------------------------------------


def update_membership(
    membership: Membership,
    *,
    actor,
    grantor: Grantor,
    role: Role | None = None,
    all_properties: bool | None = None,
    properties=None,
    is_active: bool | None = None,
) -> Membership:
    organization = membership.organization
    _ensure_covers(
        grantor, membership.role.permissions, "No puedes modificar a alguien con más permisos que tú"
    )
    _ensure_covers_hotels(
        grantor,
        membership.all_properties,
        membership.properties.all(),
        "No puedes modificar a alguien con acceso a hoteles que tú no tienes",
    )
    if role is not None:
        _validate_role(organization, role)
        _ensure_covers(grantor, role.permissions, "No puedes asignar un rol con permisos que no tienes")
    if is_active is False and membership.user_id == getattr(actor, "pk", None):
        raise DomainError("No puedes desactivar tu propio usuario", code="cannot_deactivate_self")
    with transaction.atomic():
        membership = Membership.objects.select_for_update().select_related("role").get(pk=membership.pk)
        before = {
            "role": membership.role.code,
            "all_properties": membership.all_properties,
            "properties": sorted(str(p) for p in membership.properties.values_list("pk", flat=True)),
            "is_active": membership.is_active,
        }
        new_role = role or membership.role
        new_active = membership.is_active if is_active is None else is_active
        _protect_last_owner(membership, new_role=new_role, new_active=new_active)
        membership.role = new_role
        membership.is_active = new_active
        if all_properties is not None or properties is not None:
            all_props = membership.all_properties if all_properties is None else all_properties
            chosen = _validate_properties(
                organization, all_props, properties if properties is not None else membership.properties.all()
            )
            _ensure_covers_hotels(grantor, all_props, chosen, HOTELS_MESSAGE)
            membership.all_properties = all_props
            membership.properties.set(chosen)
        membership.save()
        after = {
            "role": membership.role.code,
            "all_properties": membership.all_properties,
            "properties": sorted(str(p) for p in membership.properties.values_list("pk", flat=True)),
            "is_active": membership.is_active,
        }
        changes = audit.diff(before, after)
        if changes:
            audit.record(
                action="accounts.member_updated",
                target=membership,
                summary=f"Actualizó el acceso de {membership.user.email}",
                actor=actor,
                organization=organization,
                changes=changes,
            )
    return membership


def _protect_last_owner(membership: Membership, *, new_role: Role, new_active: bool) -> None:
    if not (membership.is_active and is_owner_role(membership.role)):
        return
    if new_active and is_owner_role(new_role):
        return
    other_owners = list(
        Membership.objects.select_for_update()
        .filter(
            organization=membership.organization, is_active=True, role__code=OWNER_ROLE, role__is_system=True
        )
        .exclude(pk=membership.pk)
        .values_list("pk", flat=True)
    )
    if not other_owners:
        raise ConflictError(
            "La organización necesita al menos un dueño activo; nombra otro dueño primero", code="last_owner"
        )


# ---- Roles ----------------------------------------------------------------------------------------------


def _clean_permissions(permissions) -> list[str]:
    cleaned = sorted({str(p).strip() for p in permissions or [] if str(p).strip()})
    unknown = unknown_permissions(cleaned)
    if unknown:
        raise DomainError("Hay permisos que no existen", code="invalid_permissions", unknown=unknown)
    return cleaned


def _role_code(organization, name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_")[:40] or "rol"
    code, n = base, 2
    while Role.objects.filter(organization=organization, code=code).exists():
        code, n = f"{base}_{n}", n + 1
    return code


def _check_name(organization, name: str, *, exclude: Role | None = None) -> str:
    name = (name or "").strip()
    if not name:
        raise DomainError(
            "Escribe un nombre", code="validation_error", fields={"name": ["Escribe un nombre"]}
        )
    clash = Role.objects.filter(organization=organization, name__iexact=name)
    if exclude is not None:
        clash = clash.exclude(pk=exclude.pk)
    if clash.exists():
        raise DomainError(
            "Ya existe un rol con ese nombre",
            code="validation_error",
            fields={"name": ["Ya existe un rol con ese nombre"]},
        )
    return name


def _ensure_custom(role: Role) -> None:
    if role.is_system:
        raise ConflictError(
            "Los roles del sistema no se pueden modificar; duplícalo para editarlo", code="system_role"
        )


def create_role(
    organization, *, name: str, description: str = "", permissions, actor, grantor: Grantor
) -> Role:
    permissions = _clean_permissions(permissions)
    _ensure_covers(grantor, permissions, "No puedes crear un rol con permisos que no tienes")
    name = _check_name(organization, name)
    role = Role.objects.create(
        organization=organization,
        code=_role_code(organization, name),
        name=name,
        description=(description or "").strip(),
        permissions=permissions,
        is_system=False,
    )
    audit.record(
        action="accounts.role_created",
        target=role,
        summary=f"Creó el rol {role.name}",
        actor=actor,
        organization=organization,
        changes={"permissions": permissions},
    )
    return role


def update_role(
    role: Role, *, actor, grantor: Grantor, name=None, description=None, permissions=None
) -> Role:
    _ensure_custom(role)
    _ensure_covers(grantor, role.permissions, "No puedes modificar un rol con permisos que no tienes")
    before = {"name": role.name, "description": role.description, "permissions": role.permissions}
    if permissions is not None:
        permissions = _clean_permissions(permissions)
        _ensure_covers(grantor, permissions, "No puedes otorgar permisos que no tienes")
        role.permissions = permissions
    if name is not None:
        role.name = _check_name(role.organization, name, exclude=role)
    if description is not None:
        role.description = description.strip()
    role.save()
    changes = audit.diff(
        before, {"name": role.name, "description": role.description, "permissions": role.permissions}
    )
    if changes:
        audit.record(
            action="accounts.role_updated",
            target=role,
            summary=f"Actualizó el rol {role.name}",
            actor=actor,
            organization=role.organization,
            changes=changes,
        )
    return role


def delete_role(role: Role, *, actor, grantor: Grantor) -> None:
    _ensure_custom(role)
    _ensure_covers(grantor, role.permissions, "No puedes eliminar un rol con permisos que no tienes")
    if role.memberships.exists() or role.invitations.filter(accepted_at__isnull=True).exists():
        raise ConflictError("El rol está asignado a personas o invitaciones", code="role_in_use")
    audit.record(
        action="accounts.role_deleted",
        target=role,
        summary=f"Eliminó el rol {role.name}",
        actor=actor,
        organization=role.organization,
    )
    role.delete()


def duplicate_role(role: Role, *, actor, grantor: Grantor) -> Role:
    """Editable copy ("Copia de Recepción", then "Copia de Recepción (2)", …) with the same permissions."""
    _ensure_covers(grantor, role.permissions, "No puedes copiar un rol con permisos que no tienes")
    organization = role.organization
    base = f"Copia de {role.name}"
    name, n = base, 2
    while Role.objects.filter(organization=organization, name__iexact=name).exists():
        name, n = f"{base} ({n})", n + 1
    return create_role(
        organization,
        name=name,
        description=role.description,
        permissions=role.permissions,
        actor=actor,
        grantor=grantor,
    )
