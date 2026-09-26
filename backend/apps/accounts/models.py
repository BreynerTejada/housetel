import secrets
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from apps.core.fields import json_field
from apps.core.models import BaseModel, Organization, Property


class UserManager(BaseUserManager):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        """Emails are stored trimmed and fully lowercased (login is case-insensitive)."""
        return (email or "").strip().lower()

    def get_by_natural_key(self, username):
        return self.get(**{f"{self.model.USERNAME_FIELD}__iexact": username})

    def create_user(self, email, password=None, **extra_fields):
        email = self.normalize_email(email)
        if not email:
            raise ValueError("El email es obligatorio")
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    """Custom user: login by email. Platform super-admins have `is_platform_admin`."""

    class Language(models.TextChoices):
        ES = "es", "Español"
        EN = "en", "English"

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=200, blank=True)
    language = models.CharField(max_length=5, choices=Language.choices, default=Language.ES)
    phone = models.CharField(max_length=32, blank=True)
    is_platform_admin = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        ordering = ["email"]
        constraints = [models.UniqueConstraint(Lower("email"), name="user_email_ci_unique")]

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs):
        # Normalize on every save path (forms, admin, objects.create), not only in create_user.
        self.email = UserManager.normalize_email(self.email)
        super().save(*args, **kwargs)


class Role(BaseModel):
    """Permission set. `organization=None` = template; system roles are per-organization copies."""

    organization = models.ForeignKey(
        Organization, null=True, blank=True, on_delete=models.CASCADE, related_name="roles"
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False)
    permissions = json_field(default=list)  # codes or fnmatch patterns: ["bookings.*", "finance.view"]

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"], nulls_distinct=False, name="role_code_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class Membership(BaseModel):
    """A user's role inside an organization, for all or some of its properties."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    role = models.ForeignKey(Role, on_delete=models.RESTRICT, related_name="memberships")
    all_properties = models.BooleanField(default=True)
    properties = models.ManyToManyField(Property, blank=True, related_name="memberships")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["organization__name", "user__email"]
        constraints = [
            models.UniqueConstraint(fields=["user", "organization"], name="membership_user_org_unique")
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.organization} ({self.role.code})"


def _invitation_token() -> str:
    return secrets.token_urlsafe(32)


def _invitation_expiry():
    return timezone.now() + timedelta(days=7)


class Invitation(BaseModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="invitations")
    all_properties = models.BooleanField(default=True)
    properties = models.ManyToManyField(Property, blank=True, related_name="invitations")
    token = models.CharField(max_length=64, unique=True, default=_invitation_token)
    expires_at = models.DateTimeField(default=_invitation_expiry)
    accepted_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.email} → {self.organization}"
