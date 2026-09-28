from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import BaseUserCreationForm
from django.contrib.auth.forms import UserChangeForm as DjangoUserChangeForm

from apps.accounts.models import Invitation, Membership, Role, User
from apps.accounts.verification import send_verification_on_commit


class UserCreationForm(BaseUserCreationForm):
    class Meta:
        model = User
        fields = ("email", "full_name")


class UserChangeForm(DjangoUserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


class EmailVerifiedFilter(admin.SimpleListFilter):
    """Support (P2): who has not confirmed their email yet."""

    title = "correo verificado"
    parameter_name = "email_verified"

    def lookups(self, request, model_admin):
        return [("yes", "Sí"), ("no", "No")]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(email_verified_at__isnull=False)
        if self.value() == "no":
            return queryset.filter(email_verified_at__isnull=True)
        return queryset


class MembershipInline(admin.TabularInline):
    model = Membership
    fk_name = "user"
    fields = ["organization", "role", "all_properties", "is_active"]
    extra = 0


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    ordering = ["email"]
    list_display = [
        "email", "full_name", "is_platform_admin", "is_staff", "is_active", "email_verified", "last_login",
    ]  # fmt: skip
    list_filter = ["is_platform_admin", "is_staff", "is_superuser", "is_active", EmailVerifiedFilter]
    search_fields = ["email", "full_name"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Perfil", {"fields": ("full_name", "language", "phone", "email_verified_at")}),
        (
            "Permisos",
            {
                "fields": (
                    "is_active",
                    "is_platform_admin",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Fechas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "full_name", "password1", "password2")}),
    )
    inlines = [MembershipInline]

    def get_inlines(self, request, obj):
        return self.inlines if obj is not None else []  # memberships are added once the user exists

    def save_model(self, request, obj, form, change):
        """A new address is not verified until its owner opens the link (P2): it gets one after saving.
        (New users get theirs from the post_save receiver.) Setting both fields at once is respected."""
        email_changed = change and "email" in form.changed_data
        if email_changed and "email_verified_at" not in form.changed_data:
            obj.email_verified_at = None
        super().save_model(request, obj, form, change)
        if email_changed and obj.email_verified_at is None:
            send_verification_on_commit(obj)

    @admin.display(boolean=True, description="Correo verificado", ordering="email_verified_at")
    def email_verified(self, obj):
        return obj.email_verified


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "organization", "is_system"]
    list_filter = ["is_system"]
    list_select_related = ["organization"]
    search_fields = ["name", "code"]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "organization", "role", "all_properties", "is_active"]
    list_filter = ["is_active", "all_properties"]
    list_select_related = ["user", "organization", "role"]
    search_fields = ["user__email", "organization__name"]
    raw_id_fields = ["user"]
    filter_horizontal = ["properties"]


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ["email", "organization", "role", "expires_at", "accepted_at"]
    list_select_related = ["organization", "role"]
    search_fields = ["email"]
    exclude = ["token"]
    raw_id_fields = ["invited_by"]
