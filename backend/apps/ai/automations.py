"""Automations of `ai` (spec §6 + plan C9). Registered on import (auto-discovered by the core)."""

from celery.schedules import crontab

from apps.core.automation import Automation, RunResult, register


def anomaly_scan(property, params) -> RunResult:
    from apps.ai.anomalies import scan_anomalies

    result = scan_anomalies(property)
    summary = f"{result['raised']} anomalías abiertas, {result['resolved']} resueltas solas"
    status = "partial" if result["failed_rules"] else "success"
    return RunResult(status=status, summary=summary, details=result)


def daily_brief(property, params) -> RunResult:
    from apps.ai.anomalies import daily_brief as build

    alert = build(property)
    simulated = alert.data.get("simulated")
    return RunResult(
        summary="Resumen del día publicado" + (" (asistente simulado)" if simulated else ""),
        details={"alert_id": str(alert.pk), "simulated": simulated},
    )


register(
    Automation(
        code="ai.anomaly_scan",
        app="ai",
        name_es="Detección de anomalías",
        name_en="Anomaly detection",
        description_es=(
            "Cada hora revisa llegadas sin garantía, pagos duplicados, tarifas fuera de rango, noches sin "
            "cargo, VIP con habitación sin preparar, TRA y facturas pendientes, diferencias de caja y "
            "sobreventa; crea alertas y las resuelve cuando el problema desaparece."
        ),
        description_en=(
            "Every hour checks unguaranteed arrivals, duplicate payments, out-of-range rates, unposted "
            "nights, VIPs with unready rooms, pending TRA and invoices, cash differences and overbooking; "
            "raises alerts and resolves them when the problem is gone."
        ),
        schedule=crontab(minute=0),
        handler=anomaly_scan,
    )
)
register(
    Automation(
        code="ai.daily_brief",
        app="ai",
        name_es="Resumen del día con IA",
        name_en="AI daily brief",
        description_es="A las 07:30 publica como alerta informativa un resumen del día escrito por la IA.",
        description_en="At 07:30 posts an AI-written summary of the day as an info alert.",
        schedule=crontab(hour=7, minute=30),
        handler=daily_brief,
    )
)
