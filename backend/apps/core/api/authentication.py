from rest_framework import authentication, exceptions


def enforce_csrf(request) -> None:
    """Explicit CSRF check for views without authentication classes (e.g. login). Raises 403 `csrf_failed`."""
    SessionAuthentication().enforce_csrf(request)


class SessionAuthentication(authentication.SessionAuthentication):
    """DRF session auth adjusted for the SPA.

    - Anonymous requests to protected endpoints get **401** (not DRF's default 403), so the frontend can
      tell "not logged in" (→ redirect to /login) from "no permission". The scheme is not `Basic`, so
      browsers never show a credentials popup.
    - A missing/invalid CSRF token gets the stable code `csrf_failed` (the SPA can refresh the cookie and
      retry).
    """

    def authenticate_header(self, request):
        return 'Session realm="api"'

    def enforce_csrf(self, request):
        try:
            super().enforce_csrf(request)
        except exceptions.PermissionDenied as exc:
            raise exceptions.PermissionDenied(
                {
                    "detail": "Token CSRF inválido o ausente. Recarga la página e intenta de nuevo.",
                    "code": "csrf_failed",
                    "reason": str(exc.detail),
                }
            ) from exc
