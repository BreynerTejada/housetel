"""SaaS automations (platform scope, spec §6): `saas.billing_cycle` (daily 03:00) and
`saas.commission_settlement` (day 1 of the month, 04:00)."""

from celery.schedules import crontab

from apps.core.automation import Automation, RunResult, register


def _billing_cycle(property, params) -> RunResult:
    from apps.saas.services.billing import run_billing_cycle

    report = run_billing_cycle()
    details = report.as_dict()
    if report.skipped:  # production without the platform's Wompi keys: nobody is charged nor suspended
        return RunResult(status="skipped", summary=report.skipped, details=details)
    summary = (
        f"Pruebas convertidas {report.trials_converted} · renovaciones {report.renewed} · "
        f"pagos {report.paid} · "
        f"fallidos {report.failed} · en mora {report.past_due} · suspendidas {report.suspended} · "
        f"recuperadas {report.recovered}"
    )
    return RunResult(status="partial" if report.errors else "success", summary=summary, details=details)


def _commission_settlement(property, params) -> RunResult:
    from apps.saas.services.commissions import previous_month, settle_month

    year, month = params.get("year"), params.get("month")
    if not (year and month):
        year, month = previous_month()
    settlements = settle_month(int(year), int(month))
    total = sum((s.total for s in settlements), 0)
    return RunResult(
        status="success",
        summary=f"{len(settlements)} liquidaciones de {int(year)}-{int(month):02d} por {total}",
        details={"period": f"{int(year)}-{int(month):02d}", "settlements": [str(s.pk) for s in settlements]},
    )


register(
    Automation(
        code="saas.billing_cycle",
        app="saas",
        name_es="Ciclo de cobro de suscripciones",
        name_en="Subscription billing cycle",
        description_es=(
            "Convierte pruebas vencidas, factura las renovaciones (plan + IVA), cobra, reintenta los días "
            "1, 3 y 7 "
            "y suspende por mora."
        ),
        description_en=(
            "Converts expired trials, invoices renewals (plan + VAT), charges, retries on days 1, 3 and 7 "
            "and "
            "suspends for non-payment."
        ),
        schedule=crontab(hour=3, minute=0),
        handler=_billing_cycle,
        scope="platform",
    )
)

register(
    Automation(
        code="saas.commission_settlement",
        app="saas",
        name_es="Liquidación mensual de comisiones",
        name_en="Monthly commission settlement",
        description_es=(
            "Liquida las comisiones del marketplace del mes anterior por organización y las factura."
        ),
        description_en="Settles last month's marketplace commissions per organization and invoices them.",
        schedule=crontab(day_of_month=1, hour=4, minute=0),
        handler=_commission_settlement,
        scope="platform",
    )
)
