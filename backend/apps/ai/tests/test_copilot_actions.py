"""Confirming a copilot proposal: the user's permission is checked again at that moment, the action runs
through the contract services and is audited with source="ai"; a proposal runs at most once."""

from datetime import date
from decimal import Decimal

import pytest
from django.core import mail

from apps.ai.copilot.actions import ActionError, execute_action, reject_action
from apps.ai.copilot.tools import ToolContext, run_tool
from apps.ai.models import CopilotAction, CopilotSession
from apps.bookings.models import Reservation
from apps.bookings.services.reservations import check_in
from apps.bookings.tests.helpers import book, build_hotel, oct_
from apps.core.models import AuditEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def hotel(prop):
    return build_hotel(prop)  # business date 2026-10-01; DBL 101/102/201, STE 301


def propose(user, prop, name, arguments) -> CopilotAction:
    session = CopilotSession.objects.filter(
        property=prop, user=user
    ).first() or CopilotSession.objects.create(property=prop, user=user)
    output = run_tool(ToolContext(property=prop, user=user, session=session), name, arguments)
    assert "proposal" in output, output
    return CopilotAction.objects.get(pk=output["proposal"]["id"])


def ai_audit(action_code):
    return AuditEvent.objects.filter(action="ai.copilot_action", source="ai", changes__action=action_code)


def test_confirming_create_reservation_creates_it_audited_as_ai(hotel, make_member):
    front = make_member("front_desk")
    action = propose(
        front,
        hotel.prop,
        "create_reservation",
        {
            "checkin": "2026-10-12",
            "checkout": "2026-10-14",
            "adults": 2,
            "room_type": "DBL",
            "guest_name": "Ana Pérez",
            "guest_email": "ana@example.com",
        },
    )

    executed = execute_action(action, user=front)

    reservation = Reservation.objects.get()
    assert (executed.status, executed.result["code"]) == ("executed", reservation.code)
    assert executed.executed_at is not None and executed.decided_by == front
    assert (reservation.booker.full_name, reservation.checkin_date, reservation.total_amount) == (
        "Ana Pérez",
        date(2026, 10, 12),
        Decimal("761600.00"),
    )
    created = AuditEvent.objects.get(action="bookings.reservation_created")
    assert (created.source, created.actor) == ("ai", front)
    event = ai_audit("create_reservation").get()
    assert (event.actor, event.target_id) == (front, str(reservation.pk))


def test_the_permission_is_checked_again_when_confirming(hotel, make_member, organization):
    """Proposed by a front desk user whose role then became housekeeping: the confirmation is refused."""
    from apps.accounts.models import Membership, Role

    front = make_member("front_desk")
    action = propose(
        front,
        hotel.prop,
        "create_reservation",
        {
            "checkin": "2026-10-12",
            "checkout": "2026-10-14",
            "guest_name": "Ana Pérez",
        },
    )
    membership = Membership.objects.get(user=front, organization=organization)
    membership.role = Role.objects.get(organization=organization, code="housekeeping")
    membership.save()

    with pytest.raises(ActionError) as caught:
        execute_action(action, user=front)

    assert (caught.value.status_code, caught.value.code) == (403, "permission_denied")
    assert caught.value.extra["permission"] == "bookings.manage"
    assert not Reservation.objects.exists()
    action.refresh_from_db()
    assert action.status == "proposed"


def test_only_the_user_who_asked_can_confirm(hotel, make_member):
    front, other = make_member("front_desk"), make_member("owner")
    action = propose(
        front,
        hotel.prop,
        "create_reservation",
        {
            "checkin": "2026-10-12",
            "checkout": "2026-10-14",
            "guest_name": "Ana Pérez",
        },
    )

    with pytest.raises(ActionError) as caught:
        execute_action(action, user=other)

    assert caught.value.status_code == 404
    assert not Reservation.objects.exists()


def test_a_proposal_runs_only_once(hotel, owner):
    action = propose(
        owner,
        hotel.prop,
        "create_reservation",
        {
            "checkin": "2026-10-12",
            "checkout": "2026-10-14",
            "guest_name": "Ana Pérez",
        },
    )
    execute_action(action, user=owner)

    with pytest.raises(ActionError) as caught:
        execute_action(CopilotAction.objects.get(pk=action.pk), user=owner)

    assert (caught.value.status_code, caught.value.code) == (409, "action_not_pending")
    assert Reservation.objects.count() == 1


def test_a_rejected_proposal_cannot_run(hotel, owner):
    action = propose(owner, hotel.prop, "block_room", {"room_number": "101", "start": "2026-10-05"})

    rejected = reject_action(action, user=owner)

    assert (rejected.status, rejected.decided_by) == ("rejected", owner)
    with pytest.raises(ActionError):
        execute_action(rejected, user=owner)


def test_move_room_confirmed_moves_the_stay(hotel, owner):
    reservation = book(hotel, oct_(3), oct_(5), stay_kwargs={"room_id": hotel.rooms["101"].pk})
    action = propose(
        owner, hotel.prop, "move_room", {"reservation_code": reservation.code, "room_number": "102"}
    )

    execute_action(action, user=owner)

    assert reservation.stays.get().room == hotel.rooms["102"]
    assert ai_audit("move_room").exists()


def test_move_room_to_another_category_keeps_the_upgrade_flag(hotel, owner):
    reservation = book(hotel, oct_(3), oct_(5), stay_kwargs={"room_id": hotel.rooms["101"].pk})
    action = propose(
        owner, hotel.prop, "move_room", {"reservation_code": reservation.code, "room_number": "301"}
    )

    execute_action(action, user=owner)

    stay = reservation.stays.get()
    assert (stay.room, stay.room_type) == (hotel.rooms["301"], hotel.dbl)  # upgrade: price and category stay


def test_check_in_confirmed_checks_the_guest_in(hotel, owner):
    reservation = book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["101"].pk})
    action = propose(owner, hotel.prop, "check_in", {"reservation_code": reservation.code})

    executed = execute_action(action, user=owner)

    assert reservation.stays.get().status == "checked_in"
    assert executed.result["checked_in"] == 1


def test_a_failing_check_out_is_recorded_as_failed_with_the_reason(hotel, owner):
    reservation = book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["101"].pk})
    check_in(reservation.stays.get(), actor=owner)
    action = propose(owner, hotel.prop, "check_out", {"reservation_code": reservation.code})

    failed = execute_action(action, user=owner)  # the balance is still due

    assert failed.status == "failed"
    assert "saldo" in failed.error.lower()
    assert reservation.stays.get().status == "checked_in"
    assert not ai_audit("check_out").exists()


def test_block_room_confirmed_blocks_it(hotel, owner):
    from apps.inventory.models import RoomBlock

    action = propose(
        owner,
        hotel.prop,
        "block_room",
        {
            "room_number": "201",
            "start": "2026-10-05",
            "end": "2026-10-07",
            "kind": "maintenance",
            "reason": "Pintura",
        },
    )

    execute_action(action, user=owner)

    block = RoomBlock.objects.get()
    assert (block.room, block.start_date, block.end_date, block.kind, block.reason) == (
        hotel.rooms["201"],
        date(2026, 10, 5),
        date(2026, 10, 7),
        "maintenance",
        "Pintura",
    )


def test_add_extra_confirmed_posts_the_charge_on_the_folio(hotel, owner):
    from apps.finance.models import Charge
    from apps.rates.tests.factories import ExtraFactory

    ExtraFactory(
        property=hotel.prop,
        code="BRK",
        name={"es": "Desayuno", "en": "Breakfast"},
        price=Decimal("35000"),
        charge_type="per_person_night",
    )
    reservation = book(hotel, oct_(3), oct_(5))
    action = propose(
        owner,
        hotel.prop,
        "add_extra",
        {"reservation_code": reservation.code, "extra": "desayuno", "quantity": 2},
    )

    execute_action(action, user=owner)

    charge = Charge.objects.get(kind="extra")
    assert (charge.quantity, charge.amount, charge.source, charge.folio.reservation) == (
        2,
        Decimal("70000.00"),
        "ai",
        reservation,
    )


def test_send_message_confirmed_sends_the_template_by_email(hotel, owner):
    reservation = book(hotel, oct_(3), oct_(5))
    action = propose(
        owner,
        hotel.prop,
        "send_message",
        {"reservation_code": reservation.code, "template_code": "confirmation"},
    )

    executed = execute_action(action, user=owner)

    assert executed.status == "executed", executed.error
    (email,) = mail.outbox
    assert email.to == [reservation.booker.email]
    assert reservation.code in email.body


def test_an_object_that_disappeared_fails_cleanly(hotel, owner):
    reservation = book(hotel, oct_(3), oct_(5), stay_kwargs={"room_id": hotel.rooms["101"].pk})
    action = propose(
        owner, hotel.prop, "move_room", {"reservation_code": reservation.code, "room_number": "102"}
    )
    hotel.rooms["102"].is_active = False
    hotel.rooms["102"].save()

    failed = execute_action(action, user=owner)

    assert failed.status == "failed" and failed.error
    assert reservation.stays.get().room == hotel.rooms["101"]
