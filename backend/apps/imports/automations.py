"""Automations of imports (registered in the core registry; beat schedule is static)."""

from celery.schedules import crontab

from apps.core.automation import Automation, RunResult, register


def purge_data(property, params) -> RunResult:
    from apps.imports.retention import purge

    result = purge(
        retention_days=int(params.get("retention_days", 30)),
        abandoned_days=int(params.get("abandoned_days", 14)),
    )
    return RunResult(
        summary=(
            f"{result['jobs_purged']} importaciones sin datos del archivo · "
            f"{result['abandoned_deleted']} importaciones abandonadas eliminadas"
        ),
        details=result,
    )


register(
    Automation(
        code="imports.purge_data",
        app="imports",
        name_es="Borrar datos de archivos importados",
        name_en="Erase imported file data",
        description_es=(
            "Habeas Data: borra las celdas de los archivos importados 30 días después de terminar "
            "(el resultado "
            "queda) y elimina las importaciones que nunca se ejecutaron."
        ),
        description_en=(
            "Habeas Data: erases the cells of imported files 30 days after they finished "
            "(the result stays) and "
            "deletes imports that never ran."
        ),
        schedule=crontab(hour=4, minute=45),
        handler=purge_data,
        scope="platform",
        default_params={"retention_days": 30, "abandoned_days": 14},
    )
)
