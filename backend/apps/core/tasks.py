from celery import shared_task


@shared_task(name="core.run_automation")
def run_automation_task(code: str, property_id: str | None = None):
    """Beat entry point: runs `code` for every eligible property (or once, for platform automations)."""
    from apps.core import automation
    from apps.core.models import Property

    item = automation.get(code)
    if item.scope == "platform":
        automation.run(code, None)
        return
    qs = Property.objects.filter(status="active", organization__status__in=["trial", "active", "past_due"])
    if property_id:
        qs = qs.filter(pk=property_id)
    for prop in qs:
        if automation.is_enabled(code, prop):
            automation.run(code, prop)
