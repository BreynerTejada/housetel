"""Automations owned by compliance (spec §6 + the TRA retries)."""

from celery.schedules import crontab

from apps.core.automation import Automation, RunResult, register


def issue_pending_invoices(property, params) -> RunResult:
    from apps.compliance.services.invoices import issue_pending_invoices as run

    report = run(property, lookback_days=int(params.get("lookback_days", 3)))
    if report.get("skipped"):
        return RunResult(status="skipped", summary=report["skipped"], details=report)
    summary = (
        f"{report['auto_issued']} facturas emitidas, {report['retried']} reintentos, "
        f"{report['refreshed']} consultas a la DIAN, {report['failed']} con error"
    )
    return RunResult(status="partial" if report["failed"] else "success", summary=summary, details=report)


def sire_daily_file(property, params) -> RunResult:
    from apps.compliance.services.sire import sire_daily_file as run

    report = run(property)
    if report["status"] == "skipped":
        reason = (
            "ya estaba generado"
            if report["reason"] == "already_generated"
            else "sin movimientos de extranjeros"
        )
        return RunResult(status="skipped", summary=f"SIRE del {report['date']}: {reason}", details=report)
    summary = (
        f"SIRE del {report['date']}: {report['records']} movimientos, {report['missing']} con datos faltantes"
    )
    return RunResult(status="partial" if report["missing"] else "success", summary=summary, details=report)


def tra_retry(property, params) -> RunResult:
    from apps.compliance.services.tra import retry_pending_tra

    report = retry_pending_tra(property)
    if report.get("skipped"):
        return RunResult(status="skipped", summary=report["skipped"], details=report)
    summary = (
        f"{report['retried']} registros TRA reintentados: {report['registered']} registrados, "
        f"{report['failed']} pendientes"
    )
    return RunResult(status="partial" if report["failed"] else "success", summary=summary, details=report)


register(
    Automation(
        code="compliance.issue_pending_invoices",
        app="compliance",
        name_es="Emitir facturas electrónicas pendientes",
        name_en="Issue pending electronic invoices",
        description_es=(
            "Reintenta las facturas con error técnico, consulta a la DIAN las que esperan validación y "
            "emite la "
            "factura de las salidas recientes que quedaron sin facturar."
        ),
        description_en=(
            "Retries invoices with technical errors, asks the DIAN about the ones waiting for validation and "
            "invoices recent departures left without an invoice."
        ),
        schedule=crontab(minute="*/15"),
        handler=issue_pending_invoices,
        default_params={"lookback_days": 3},
    )
)
register(
    Automation(
        code="compliance.sire_daily_file",
        app="compliance",
        name_es="Archivo SIRE del día anterior",
        name_en="Previous day's SIRE file",
        description_es=(
            "Genera el archivo de cargue masivo SIRE (Migración Colombia) con las entradas y salidas de "
            "extranjeros "
            "del día anterior y avisa si falta subirlo o si hay datos incompletos."
        ),
        description_en=(
            "Builds the SIRE bulk-upload file (Migración Colombia) with the previous day's foreign "
            "check-ins and "
            "check-outs, and warns when it is not uploaded yet or data is missing."
        ),
        schedule=crontab(hour=8, minute=0),
        handler=sire_daily_file,
    )
)
register(
    Automation(
        code="compliance.tra_retry",
        app="compliance",
        name_es="Reintentar registros TRA",
        name_en="Retry TRA registrations",
        description_es=(
            "Envía de nuevo a la TRA (MinCIT) los registros de la última semana que fallaron o esperaban "
            "datos."
        ),
        description_en="Sends again to the TRA (MinCIT) last week's registrations that failed or were "
        "waiting for data.",
        schedule=crontab(minute="*/15"),
        handler=tra_retry,
    )
)
