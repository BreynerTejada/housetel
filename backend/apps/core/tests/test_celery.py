"""Celery wiring: beat gets a static schedule generated from the automation registry (spec §2.1, §6)."""

from apps.core import automation


def celery_app():
    from config.celery import app

    app.finalize(auto=True)
    return app


def test_beat_has_one_entry_per_registered_automation():
    schedule = celery_app().conf.beat_schedule
    items = automation.all()
    assert items, "at least core.cleanup is registered"
    for item in items:
        entry = schedule[item.code]
        assert entry["task"] == "core.run_automation"
        assert tuple(entry["args"]) == (item.code,)
        assert entry["schedule"] == item.schedule


def test_worker_knows_the_fan_out_task_and_uses_bogota_time():
    app = celery_app()
    assert "core.run_automation" in app.tasks
    assert app.conf.timezone == "America/Bogota"
    assert app.conf.broker_url.startswith("redis://")
