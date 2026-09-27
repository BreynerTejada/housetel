"""Automations owned by finance (spec §6)."""

from celery.schedules import crontab

from apps.core.automation import Automation, RunResult, register


def sync_pending_intents(property, params) -> RunResult:
    from apps.finance.services import sync_open_intents

    report = sync_open_intents(property)
    return RunResult(
        summary=(
            f"{report['checked']} links de pago verificados: {report['approved']} pagados, "
            f"{report['expired']} vencidos"
        ),
        details=report,
    )


register(
    Automation(
        code="finance.sync_pending_intents",
        app="finance",
        name_es="Verificar pagos en línea",
        name_en="Verify online payments",
        description_es=(
            "Consulta al proveedor de pagos los links pendientes, registra los pagos aprobados que no "
            "llegaron por webhook y vence los links que pasaron su fecha límite."
        ),
        description_en=(
            "Asks the payment provider about pending links, records approved payments whose webhook never "
            "arrived and expires links past their deadline."
        ),
        schedule=crontab(minute="*/5"),
        handler=sync_pending_intents,
    )
)
