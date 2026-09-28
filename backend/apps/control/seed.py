"""Demo data of the control center (plan C12). The app owns no models: it seeds the *derived* state a hotel
that has been running shows in its control center, using the real mechanisms (no fabricated history):

1. **Integrations**: every integration of each demo property gets its row and, when it runs in simulated mode,
   a connection test (status "OK" + last check), like pressing "Probar conexión". Real-mode ones (e.g. email
   over SMTP, Gemini) are left untested: the seed never calls external services.
2. **Automations**: the read-mostly automations that are safe to replay run once per property through
   `core.automation.run` (real `AutomationRun` + audit): the inventory reconciliation and the anomaly scan,
   which raises the real alerts of the demo data (unguaranteed arrivals, VIP rooms not ready…). Automations
   with side effects (night audit, messages, tentative releases, payment sync…) are never run by the seed.

Idempotent: integrations already checked and automations that already ran in a property are skipped.
"""

import logging

from django.utils import timezone

from apps.control.services.integrations import property_kinds
from apps.core import automation, integrations
from apps.core.errors import DomainError
from apps.core.models import AutomationRun, IntegrationSetting

logger = logging.getLogger("housetel.control")

SAFE_AUTOMATIONS = ["bookings.inventory_reconcile", "ai.anomaly_scan"]


def seed(ctx) -> None:
    for key, prop in ctx.properties.items():
        tested = _check_integrations(prop)
        ran = _run_safe_automations(prop)
        ctx.log(
            f"  {key}: {tested} integraciones simuladas probadas; automatizaciones: {', '.join(ran) or '—'}"
        )


def _check_integrations(prop) -> int:
    tested = 0
    for kind in property_kinds():
        setting = integrations.get_setting(prop, kind)
        if setting.mode != IntegrationSetting.Mode.SIMULATED or setting.last_checked_at is not None:
            continue
        try:
            ok, message = integrations.get_provider(prop, kind).test_connection()
        except DomainError as exc:
            ok, message = False, exc.message
        except Exception as exc:  # noqa: BLE001 - one broken provider must not stop the demo seed
            logger.warning("Seed: test of %s failed in %s: %s", kind, prop.slug, exc)
            ok, message = False, f"Error inesperado del proveedor: {type(exc).__name__}"
        setting.status = IntegrationSetting.Status.OK if ok else IntegrationSetting.Status.ERROR
        setting.status_message = str(message or "")[:2000]
        setting.last_checked_at = timezone.now()
        setting.save(update_fields=["status", "status_message", "last_checked_at", "updated_at"])
        tested += 1
    return tested


def _run_safe_automations(prop) -> list[str]:
    ran = []
    for code in SAFE_AUTOMATIONS:
        try:
            automation.get(code)
        except automation.AutomationNotFound:
            continue
        if AutomationRun.objects.filter(property=prop, code=code).exists():
            continue
        if not automation.is_enabled(code, prop):
            continue
        run = automation.run(code, prop)
        ran.append(f"{code} ({run.status})")
    return ran
