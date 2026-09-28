"""Run every registered automation once per demo property (and once for the platform ones) inside a
transaction that is rolled back (C-INT): each handler runs on the seeded data without leaving any trace.

The LLM integration is switched to `simulated` inside the transaction, so the check never spends the Gemini
quota; nothing else is faked (the providers of the demo already run simulated). On-commit work (Celery
debounces, background AI summaries) never fires because nothing commits.

    docker compose exec -T backend python manage.py shell \
        -c "exec(open('scripts/automations_check.py').read())"   # make check-automations
"""

import time

from django.db import transaction

from apps.core import automation
from apps.core.models import IntegrationSetting, Property

rows = []


class Rollback(Exception):
    pass


try:
    with transaction.atomic():
        properties = list(Property.objects.filter(status="active").order_by("name"))
        for prop in properties:
            IntegrationSetting.objects.update_or_create(
                property=prop, kind="llm", defaults={"mode": IntegrationSetting.Mode.SIMULATED}
            )
        for item in automation.all():
            targets = [None] if item.scope == "platform" else properties
            for prop in targets:
                started = time.monotonic()
                run = automation.run(item.code, prop)
                elapsed = time.monotonic() - started
                rows.append(
                    (item.code, prop.name if prop else "(plataforma)", run.status, elapsed, run.summary)
                )
        # The scheduled night audit skips a day that has not ended yet: also close today by hand (the front
        # desk button, `mode=manual`) to walk the whole audit on the seeded data.
        for prop in properties:
            started = time.monotonic()
            run = automation.run("frontdesk.night_audit", prop, params={"mode": "manual"})
            rows.append(
                (
                    "frontdesk.night_audit (manual)",
                    prop.name,
                    run.status,
                    time.monotonic() - started,
                    run.summary,
                )
            )
        raise Rollback
except Rollback:
    pass

failed = [row for row in rows if row[2] == "failed"]
for code, where, status, elapsed, summary in rows:
    mark = "ERR" if status == "failed" else "ok "
    print(f"{mark} {code:38s} {where:22s} {status:8s} {elapsed:5.1f}s  {summary[:110]}")
print(f"\n{len(rows)} runs · {len(failed)} failed · rolled back")
