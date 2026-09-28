import re
import uuid

from django.conf import settings
from django.http import HttpResponseNotFound
from django.utils import translation

from apps.core.context import use_request_id

_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_ADMIN_PREFIX = "/django-admin/"


class RequestIdMiddleware:
    """Gives every request an id (incoming `X-Request-ID` if well-formed, else a new uuid4 hex).

    The id is exposed as `request.request_id`, via `apps.core.context.current_request_id()` (used by
    `apps.core.audit.record` to fill `AuditEvent.request_id` and by the JSON log formatter) and echoed in the
    `X-Request-ID` response header. In production nginx sends its own `$request_id`, so its access log and
    Django's logs share the id.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if _VALID_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        request.request_id = request_id
        with use_request_id(request_id):
            response = self.get_response(request)
        response["X-Request-ID"] = request_id
        return response


class UserLanguageMiddleware:
    """API errors in the signed-in user's language (`User.language`), which wins over `Accept-Language`.

    Runs after Django's `LocaleMiddleware` (Accept-Language → language, `es` by default) and
    `AuthenticationMiddleware`; anonymous requests keep what LocaleMiddleware chose. The SPA sends its UI
    language as `Accept-Language`, so public pages get their errors in the language on screen.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language = self._user_language(request)
        if language:
            translation.activate(language)
            request.LANGUAGE_CODE = translation.get_language()
        return self.get_response(request)

    @staticmethod
    def _user_language(request) -> str | None:
        if not request.COOKIES.get(settings.SESSION_COOKIE_NAME):
            return None  # no session: skip the user lookup entirely
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        language = (getattr(user, "language", "") or "").split("-")[0]
        return language if language in dict(settings.LANGUAGES) else None


class AdminGateMiddleware:
    """`/django-admin/` hardening (plan P1).

    - `ADMIN_ENABLED=0` (production default): the admin does not exist (404).
    - `ADMIN_STAFF_ONLY=1` (production default): only signed-in staff users reach it; everyone else gets the
      same 404 as an unknown URL, so the admin login form is never exposed. Staff sign in through the app's
      `/login` (same session cookie) and then open `/django-admin/`.
    Development keeps the stock behaviour (admin with its own login page).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(_ADMIN_PREFIX) and not self._allowed(request):
            return HttpResponseNotFound("Not Found", content_type="text/plain; charset=utf-8")
        return self.get_response(request)

    @staticmethod
    def _allowed(request) -> bool:
        if not getattr(settings, "ADMIN_ENABLED", True):
            return False
        if not getattr(settings, "ADMIN_STAFF_ONLY", False):
            return True
        user = getattr(request, "user", None)
        return bool(user is not None and user.is_authenticated and user.is_active and user.is_staff)
