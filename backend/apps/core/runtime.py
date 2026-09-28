"""Runtime facts of this installation (plan P, contract of P1): environment, simulations, public URL, support.

- `environment()` is "production" only when `DJANGO_ENV=production`; anything else is "development".
- Simulations (simulated payment gateway, OTA and WhatsApp simulators, simulated providers) are on in
  development and off in production. `HOUSETEL_ALLOW_SIMULATIONS` overrides both ways: `1` turns them on in
  production (a demo server) and `0` turns them off in development (to try the real providers locally, e.g.
  through a tunnel).
- `public_base_url()` is where the outside world reaches this installation (webhooks, links sent to guests):
  `PUBLIC_BASE_URL` (e.g. a cloudflared tunnel) or `FRONTEND_URL`.

Everything reads `django.conf.settings` on each call, so tests can use `settings` overrides.
"""

from __future__ import annotations

import functools
import inspect

from django.conf import settings
from django.http import JsonResponse
from django.utils.translation import gettext as _

PRODUCTION = "production"
DEVELOPMENT = "development"


def environment() -> str:
    """ "development" | "production" (env `DJANGO_ENV`)."""
    return PRODUCTION if getattr(settings, "DJANGO_ENV", DEVELOPMENT) == PRODUCTION else DEVELOPMENT


def simulations_enabled() -> bool:
    """False in production unless `HOUSETEL_ALLOW_SIMULATIONS=1`; True in development unless it is `0`."""
    override = getattr(settings, "HOUSETEL_ALLOW_SIMULATIONS", None)
    if override is not None:
        return bool(override)
    return environment() != PRODUCTION


def _not_found() -> JsonResponse:
    # Same shape as every API error (`apps.core.api.exceptions`), translated like DRF's own NotFound.
    return JsonResponse({"detail": _("Not found."), "code": "not_found"}, status=404)


def require_simulations(view_func):
    """Decorator: the view answers 404 while `simulations_enabled()` is False.

    Works on function views (`@api_view` included), on view classes (`@require_simulations` above an APIView:
    wraps `dispatch`), on the result of `SomeView.as_view()` in `urls.py` and on handler methods
    (`def post(self, request)`). The check runs on every request, so it follows settings changes.
    """
    if inspect.isclass(view_func):
        original_dispatch = view_func.dispatch

        @functools.wraps(original_dispatch)
        def dispatch(self, request, *args, **kwargs):
            if not simulations_enabled():
                return _not_found()
            return original_dispatch(self, request, *args, **kwargs)

        view_func.dispatch = dispatch
        return view_func

    @functools.wraps(view_func)
    def wrapper(*args, **kwargs):
        if not simulations_enabled():
            return _not_found()
        return view_func(*args, **kwargs)

    return wrapper


def public_base_url() -> str:
    """Env `PUBLIC_BASE_URL` (e.g. a cloudflared tunnel) or `FRONTEND_URL`, without the trailing slash."""
    return (getattr(settings, "PUBLIC_BASE_URL", "") or getattr(settings, "FRONTEND_URL", "")).rstrip("/")


def support_contact() -> dict:
    """`{"whatsapp": str, "email": str, "docs_url": str}` from the environment (`SUPPORT_*`); "" = not
    offered."""
    return {
        "whatsapp": getattr(settings, "SUPPORT_WHATSAPP", "") or "",
        "email": getattr(settings, "SUPPORT_EMAIL", "") or "",
        "docs_url": getattr(settings, "SUPPORT_DOCS_URL", "") or "",
    }


def public_config() -> dict:
    """Body of `GET /api/v1/public/core/config/` (read by the SPA as `useRuntimeConfig()`)."""
    return {
        "environment": environment(),
        "simulations_enabled": simulations_enabled(),
        "public_base_url": public_base_url(),
        "support": support_contact(),
    }
