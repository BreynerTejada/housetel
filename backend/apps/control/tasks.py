from celery import shared_task


@shared_task(name="control.run_automation_now")
def run_automation_now(code: str, property_id: str, user_id: str | None = None) -> str | None:
    """ "Run now" of the control center for automations that usually take ≥ 10 s (see
    apps.control.services.automations.run_now). Unlike the beat entry point (`core.run_automation`) it runs
    even when the automation is disabled in the property and records who asked for it."""
    from apps.accounts.models import User
    from apps.core import automation
    from apps.core.models import Property

    prop = Property.objects.filter(pk=property_id).first()
    if prop is None:
        return None
    user = User.objects.filter(pk=user_id).first() if user_id else None
    run = automation.run(code, prop, triggered_by=user)
    return str(run.pk)
