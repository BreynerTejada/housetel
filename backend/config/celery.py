import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("housetel")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.on_after_finalize.connect
def register_automation_schedules(sender, **kwargs):
    """Static beat schedule generated from the automation registry (apps/<app>/automations.py)."""
    from django.apps import apps as django_apps

    if not django_apps.ready:  # celery worker/beat processes; Django is already set up under runserver/pytest
        import django

        django.setup()
    from apps.core import automation
    from apps.core.tasks import run_automation_task

    for item in automation.all():
        sender.add_periodic_task(item.schedule, run_automation_task.s(item.code), name=item.code)
