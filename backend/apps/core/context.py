"""Per-request context (set by apps.core.middleware.RequestIdMiddleware)."""

from contextlib import contextmanager
from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("housetel_request_id", default="")


def current_request_id() -> str:
    return _request_id.get()


@contextmanager
def use_request_id(value: str):
    token = _request_id.set(value)
    try:
        yield
    finally:
        _request_id.reset(token)
