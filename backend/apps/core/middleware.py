import re
import uuid

from apps.core.context import use_request_id

_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


class RequestIdMiddleware:
    """Gives every request an id (incoming `X-Request-ID` if well-formed, else a new uuid4 hex).

    The id is exposed as `request.request_id`, via `apps.core.context.current_request_id()` (used by
    `apps.core.audit.record` to fill `AuditEvent.request_id`) and echoed in the `X-Request-ID`
    response header.
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
