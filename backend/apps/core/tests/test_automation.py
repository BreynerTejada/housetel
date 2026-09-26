from datetime import timedelta

import pytest
from celery.schedules import crontab
from django.contrib.sessions.models import Session
from django.utils import timezone

from apps.core import automation
from apps.core.alerts import raise_alert
from apps.core.automation import Automation, AutomationNotFound, RunResult
from apps.core.models import Alert, AuditEvent, AutomationRun, AutomationSetting
from apps.core.tasks import run_automation_task
from apps.core.tests.factories import OrganizationFactory, PropertyFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def registry(monkeypatch):
    monkeypatch.setattr(automation, "_REGISTRY", {})
    return automation._REGISTRY


def make(code="tests.job", handler=None, **kwargs):
    return Automation(
        code=code,
        app="tests",
        name_es="Trabajo de prueba",
        name_en="Test job",
        description_es="Solo para pruebas",
        schedule=crontab(minute="*/5"),
        handler=handler or (lambda prop, params: RunResult(summary="ok")),
        **kwargs,
    )


class TestRegistry:
    def test_register_get_and_all_sorted_by_code(self, registry):
        a, b = make("tests.a"), make("tests.b")
        automation.register(b)
        automation.register(a)
        assert automation.get("tests.a") is a
        assert [item.code for item in automation.all()] == ["tests.a", "tests.b"]

    def test_unknown_code_raises_not_found(self, registry):
        with pytest.raises(AutomationNotFound) as exc:
            automation.get("tests.missing")
        assert exc.value.status_code == 404


class TestSettings:
    def test_is_enabled_uses_the_default_until_a_setting_exists(self, prop, registry):
        automation.register(make("tests.a", default_enabled=False))
        assert automation.is_enabled("tests.a", prop) is False
        AutomationSetting.objects.create(property=prop, code="tests.a", enabled=True)
        assert automation.is_enabled("tests.a", prop) is True

    def test_params_merge_defaults_with_the_property_setting(self, prop, registry):
        automation.register(make("tests.a", default_params={"days": 2, "channel": "email"}))
        AutomationSetting.objects.create(property=prop, code="tests.a", params={"days": 5})
        assert automation.params_for("tests.a", prop) == {"days": 5, "channel": "email"}


class TestRun:
    def test_success_is_recorded_audited_and_resolves_the_failure_alert(self, prop, owner, registry):
        received = {}

        def handler(p, params):
            received.update(prop=p, params=params)
            return RunResult(status="success", summary="3 tareas creadas", details={"created": 3})

        automation.register(make("tests.a", handler=handler, default_params={"x": 1}))
        raise_alert(
            property=prop,
            kind="automation_failed",
            severity="warning",
            title="t",
            message="m",
            dedupe_key="automation:tests.a",
        )

        run = automation.run("tests.a", prop, params={"y": 2}, triggered_by=owner)

        run.refresh_from_db()
        assert (run.status, run.summary, run.details) == ("success", "3 tareas creadas", {"created": 3})
        assert (run.property, run.triggered_by) == (prop, owner) and run.finished_at is not None
        assert received == {"prop": prop, "params": {"x": 1, "y": 2}}
        assert not Alert.objects.filter(dedupe_key="automation:tests.a", resolved_at__isnull=True).exists()
        event = AuditEvent.objects.get(action="automation.tests.a")
        assert (event.source, event.actor, event.property) == ("automation", owner, prop)

    def test_scheduled_runs_are_audited_with_the_automation_name(self, prop, registry):
        automation.register(make("tests.a"))
        automation.run("tests.a", prop)
        assert AuditEvent.objects.get(action="automation.tests.a").actor_label == "Trabajo de prueba"

    def test_failure_is_recorded_and_raises_an_alert(self, prop, registry):
        def handler(p, params):
            raise RuntimeError("proveedor caído")

        automation.register(make("tests.a", handler=handler))

        run = automation.run("tests.a", prop)

        assert run.status == "failed"
        assert "proveedor caído" in run.details["error"]
        alert = Alert.objects.get(property=prop, dedupe_key="automation:tests.a", resolved_at__isnull=True)
        assert alert.severity == "warning"

    def test_handler_changes_are_rolled_back_when_it_fails(self, prop, registry):
        def handler(p, params):
            Alert.objects.create(property=p, kind="x", title="trabajo parcial", dedupe_key="partial-work")
            raise RuntimeError("boom")

        automation.register(make("tests.a", handler=handler))
        assert automation.run("tests.a", prop).status == "failed"
        assert not Alert.objects.filter(dedupe_key="partial-work").exists()

    def test_partial_result_is_kept_and_none_means_success(self, prop, registry):
        automation.register(
            make("tests.p", handler=lambda p, params: RunResult(status="partial", summary="2/3"))
        )
        automation.register(make("tests.n", handler=lambda p, params: None))
        assert automation.run("tests.p", prop).status == "partial"
        assert automation.run("tests.n", prop).status == "success"

    def test_platform_automation_runs_without_property(self, registry):
        automation.register(make("tests.platform", scope="platform"))
        run = automation.run("tests.platform", None)
        assert (run.property, run.status) == (None, "success")


class TestBeatTask:
    def test_runs_for_active_properties_of_billable_organizations_where_enabled(self, organization, registry):
        automation.register(make("tests.a"))
        active = PropertyFactory(organization=organization)
        PropertyFactory(organization=organization, status="inactive")
        disabled = PropertyFactory(organization=organization)
        AutomationSetting.objects.create(property=disabled, code="tests.a", enabled=False)
        PropertyFactory(organization=OrganizationFactory(status="suspended"))
        trial = PropertyFactory(organization=OrganizationFactory(status="trial"))

        run_automation_task("tests.a")

        ran = set(AutomationRun.objects.filter(code="tests.a").values_list("property_id", flat=True))
        assert ran == {active.pk, trial.pk}

    def test_can_target_a_single_property(self, organization, registry):
        automation.register(make("tests.a"))
        _first, second = PropertyFactory.create_batch(2, organization=organization)
        run_automation_task("tests.a", str(second.pk))
        assert list(AutomationRun.objects.values_list("property_id", flat=True)) == [second.pk]

    def test_platform_automation_runs_once_without_property(self, prop, registry):
        automation.register(make("tests.platform", scope="platform"))
        run_automation_task("tests.platform")
        assert list(AutomationRun.objects.values_list("property_id", flat=True)) == [None]


class TestCoreCleanup:
    def test_is_discovered_as_a_platform_automation(self):
        assert automation.get("core.cleanup").scope == "platform"

    def test_deletes_old_runs_and_expired_sessions(self):
        old = AutomationRun.objects.create(code="x", status="success")
        AutomationRun.objects.filter(pk=old.pk).update(started_at=timezone.now() - timedelta(days=120))
        recent = AutomationRun.objects.create(code="x", status="success")
        Session.objects.create(
            session_key="expired", session_data="", expire_date=timezone.now() - timedelta(days=1)
        )
        Session.objects.create(
            session_key="valid", session_data="", expire_date=timezone.now() + timedelta(days=1)
        )

        run = automation.run("core.cleanup", None)

        assert run.status == "success"
        assert not AutomationRun.objects.filter(pk=old.pk).exists()
        assert AutomationRun.objects.filter(pk=recent.pk).exists()
        assert list(Session.objects.values_list("session_key", flat=True)) == ["valid"]
