from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied


class IsPlatformAdmin(permissions.BasePermission):
    """Platform super-admin endpoints (`/api/v1/saas/admin/…`): no `X-Property-Id`, `is_platform_admin`."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if not getattr(user, "is_platform_admin", False):
            raise PermissionDenied(
                {"detail": "Solo el equipo de Housetel puede ver esto", "code": "platform_admin_required"}
            )
        return True
