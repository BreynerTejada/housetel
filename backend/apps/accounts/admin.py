from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import BaseUserCreationForm
from django.contrib.auth.forms import UserChangeForm as DjangoUserChangeForm

from apps.accounts.models import Invitation, Membership, Role, User


class UserCreationForm(BaseUserCreationForm):
    class Meta:
        model = User
        fields = ("email", "full_name")


class UserChangeForm(DjangoUserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


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
    list_display = ["email", "full_name", "is_platform_admin", "is_staff", "is_active", "last_login"]
    list_filter = ["is_platform_admin", "is_staff", "is_superuser", "is_active"]
    search_fields = ["email", "full_name"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Perfil", {"fields": ("full_name", "language", "phone")}),
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
