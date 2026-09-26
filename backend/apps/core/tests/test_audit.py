import uuid
from datetime import date
from decimal import Decimal

import pytest

from apps.core import audit
from apps.core.audit import UndoError, diff, record, register_undo, undo
from apps.core.context import use_request_id
from apps.core.models import Alert, AuditEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def undo_handlers(monkeypatch):
    monkeypatch.setattr(audit, "_UNDO_HANDLERS", {})
    return audit._UNDO_HANDLERS


class TestRecord:
    def test_derives_organization_and_target_reference(self, prop, owner):
        event = record(
            action="inventory.profile_updated",
            target=prop,
            summary="Actualizó el perfil",
            actor=owner,
            property=prop,
            changes={"phone": ["", "+573001112233"]},
        )
        event.refresh_from_db()
        assert event.organization == prop.organization
        assert (event.target_type, event.target_id) == ("core.property", str(prop.pk))
        assert (event.actor, event.actor_label, event.source) == (owner, owner.email, "user")
        assert event.changes == {"phone": ["", "+573001112233"]}

    def test_takes_the_property_from_the_target_when_not_given(self, prop):
        alert = Alert.objects.create(property=prop, kind="x", title="t", dedupe_key="k")
        event = record(action="control.alert_resolved", target=alert)
        assert (event.property, event.organization) == (prop, prop.organization)

    def test_labels_actions_without_a_user_by_source(self, prop):
        assert record(action="x", property=prop, source="automation").actor_label == "Automatización"
        assert (
            record(action="x", property=prop, source="ai", actor_label="Copiloto").actor_label == "Copiloto"
        )

    def test_anonymous_actor_is_stored_as_no_actor(self, prop):
        from django.contrib.auth.models import AnonymousUser

        event = record(action="guestportal.checkin", property=prop, actor=AnonymousUser(), source="guest")
        assert event.actor is None and event.actor_label == "Huésped"

    def test_accepts_decimal_date_and_uuid_values(self, prop):
        row_id = uuid.uuid4()
        event = record(
            action="rates.bulk_update",
            property=prop,
            changes={"price": [Decimal("100"), Decimal("120")], "date": date(2026, 10, 1)},
            undo_data={"rows": [{"id": row_id}]},
        )
        event.refresh_from_db()
        assert event.changes == {"price": ["100", "120"], "date": "2026-10-01"}
        assert event.undo_data == {"rows": [{"id": str(row_id)}]}

    def test_stores_the_current_request_id(self, prop):
        with use_request_id("req-123"):
            assert record(action="x", property=prop).request_id == "req-123"
        assert record(action="x", property=prop).request_id == ""

    def test_platform_events_have_no_tenant(self):
        event = record(action="saas.billing_cycle", source="system")
        assert event.organization is None and event.property is None


def test_diff_lists_only_changed_keys():
    assert diff({"a": 1, "b": 2, "c": 3}, {"a": 1, "b": 5, "d": 4}) == {
        "b": [2, 5],
        "c": [3, None],
        "d": [None, 4],
    }


class TestUndo:
    def test_runs_the_handler_marks_the_event_and_records_core_undo(self, prop, owner, undo_handlers):
        reverted = []
        register_undo("tests.room_moved", lambda event: reverted.append(event.undo_data["old_room"]))
        event = record(
            action="tests.room_moved", property=prop, reversible=True, undo_data={"old_room": "101"}
        )

        result = undo(event, actor=owner)

        event.refresh_from_db()
        assert reverted == ["101"]
        assert event.undone_at is not None and event.undone_by == owner
        assert result.pk == event.pk and result.undone_at == event.undone_at
        follow_up = AuditEvent.objects.get(action="core.undo")
        assert (follow_up.target_type, follow_up.target_id) == ("core.auditevent", str(event.pk))
        assert (follow_up.actor, follow_up.property) == (owner, prop)

    def test_a_second_undo_is_a_409_conflict(self, prop, owner, undo_handlers):
        register_undo("tests.room_moved", lambda event: None)
        event = record(action="tests.room_moved", property=prop, reversible=True)
        undo(event, actor=owner)
        with pytest.raises(UndoError) as exc:
            undo(AuditEvent.objects.get(pk=event.pk), actor=owner)
        assert (exc.value.code, exc.value.status_code) == ("already_undone", 409)

    def test_non_reversible_events_are_rejected(self, prop, owner, undo_handlers):
        register_undo("tests.room_moved", lambda event: None)
        event = record(action="tests.room_moved", property=prop, reversible=False)
        with pytest.raises(UndoError) as exc:
            undo(event, actor=owner)
        assert exc.value.code == "not_reversible"

    def test_actions_without_a_registered_handler_are_rejected(self, prop, owner, undo_handlers):
        event = record(action="tests.unknown", property=prop, reversible=True)
        with pytest.raises(UndoError) as exc:
            undo(event, actor=owner)
        assert exc.value.code == "undo_not_supported"

    def test_a_failing_handler_leaves_the_event_untouched(self, prop, owner, undo_handlers):
        def explode(event):
            raise RuntimeError("cannot revert")

        register_undo("tests.fragile", explode)
        event = record(action="tests.fragile", property=prop, reversible=True)
        with pytest.raises(RuntimeError):
            undo(event, actor=owner)
        event.refresh_from_db()
        assert event.undone_at is None
        assert not AuditEvent.objects.filter(action="core.undo").exists()
