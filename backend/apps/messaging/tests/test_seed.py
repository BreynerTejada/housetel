"""Messaging demo seed (plan C6 › Seed): lifecycle rules per hotel, a believable inbox (WhatsApp and email
threads of real reservations with unread questions, a closed thread, a note), hotel customizations of the
templates, and the lifecycle messages already due marked as history so the first automation run does not
email every guest of the demo at once. Nothing is sent while seeding."""

import random
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.utils import timezone

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core import automation
from apps.core.seed import SeedContext
from apps.core.tests.factories import PropertyFactory
from apps.guests.tests.factories import GuestFactory
from apps.messaging import seed as messaging_seed
from apps.messaging.models import Conversation, LifecycleDispatch, LifecycleRule, Message, MessageTemplate
from apps.messaging.services import resolve_template

pytestmark = pytest.mark.django_db


@pytest.fixture
def world(prop, make_member):
    today = timezone.localdate()
    prop.business_date = today
    prop.save()
    front = make_member("front_desk", email="recepcion@example.com")

    def booking(status, checkin, nights=2, **guest):
        booker = GuestFactory(organization=prop.organization, **guest)
        reservation = ReservationFactory(
            property=prop,
            booker=booker,
            status=status,
            checkin_date=checkin,
            checkout_date=checkin + timedelta(days=nights),
        )
        StayFactory(reservation=reservation, total_amount=Decimal("600000"))
        return reservation

    world = {
        "in_house": booking("checked_in", today - timedelta(days=1), nights=3),
        "arriving": booking("confirmed", today),
        "soon": booking("confirmed", today + timedelta(days=2)),
        "upcoming": booking("confirmed", today + timedelta(days=6)),
        "departed": booking("checked_out", today - timedelta(days=4), nights=3),
        "foreigner": booking("confirmed", today + timedelta(days=8), language="en", first_name="Emily"),
    }
    sibling = PropertyFactory(organization=prop.organization)  # a hotel without reservations
    ctx = SeedContext(
        today=today,
        rng=random.Random(20260925),
        orgs={"aurora": prop.organization},
        properties={"aurora": prop, "andino_bog": sibling},
        users={"aurora_front": front},
    )
    return {**world, "ctx": ctx, "prop": prop, "sibling": sibling, "front": front, "book": booking}


def test_every_hotel_gets_its_six_rules_enabled(world):
    messaging_seed.seed(world["ctx"])
    for prop in (world["prop"], world["sibling"]):
        rules = LifecycleRule.objects.filter(property=prop)
        assert rules.count() == 6 and all(rule.enabled for rule in rules)


def test_the_inbox_has_unread_whatsapp_and_email_questions_of_real_guests(world):
    messaging_seed.seed(world["ctx"])

    conversations = Conversation.objects.filter(property=world["prop"])
    assert {"whatsapp", "email"} <= set(conversations.values_list("channel", flat=True))
    unread = conversations.filter(unread_count__gt=0, status="open")
    assert unread.count() >= 3
    linked = {c.reservation_id for c in conversations if c.reservation_id}
    assert {world["in_house"].pk, world["arriving"].pk} <= linked
    for conversation in unread:
        last_in = conversation.messages.filter(direction="in").order_by("-created_at").first()
        assert last_in is not None and last_in.status == "received"
        latest = conversation.messages.exclude(channel="internal_note").order_by("-created_at").first()
        assert conversation.last_message_at == latest.created_at  # a note never counts as activity
        assert conversation.last_message_direction == "in"
        # Unread = the guest's messages after the hotel's last answer (notes do not answer).
        last_answer = (
            conversation.messages.filter(direction="out")
            .exclude(channel="internal_note")
            .order_by("-created_at")
        ).first()
        waiting = conversation.messages.filter(direction="in")
        if last_answer is not None:
            waiting = waiting.filter(created_at__gt=last_answer.created_at)
        assert conversation.unread_count == waiting.count()
    # A WhatsApp question from the last hours keeps the 24 h window open, so the staff can answer freely.
    whatsapp = unread.filter(channel="whatsapp", guest__isnull=False).first()
    assert timezone.now() - whatsapp.last_inbound_at < timedelta(hours=24)


def test_the_history_reads_like_the_real_flow(world):
    messaging_seed.seed(world["ctx"])
    prop = world["prop"]

    in_house = Conversation.objects.get(property=prop, reservation=world["in_house"], channel="whatsapp")
    outbound = in_house.messages.filter(direction="out").exclude(channel="internal_note")
    assert {"confirmation", "pre_arrival"} <= set(outbound.values_list("template_code", flat=True))
    confirmation = outbound.get(template_code="confirmation")
    assert world["in_house"].code in confirmation.body and confirmation.status in ("delivered", "read")
    assert in_house.messages.filter(channel="internal_note").exists()
    question = in_house.messages.filter(direction="in").get()
    assert (
        confirmation.created_at < outbound.get(template_code="pre_arrival").created_at < question.created_at
    )
    arrival = timezone.make_aware(datetime.combine(world["in_house"].checkin_date, time.min))
    assert confirmation.created_at < arrival  # the booking was confirmed before the guest arrived
    assert all(m.created_at <= timezone.now() for m in Message.objects.filter(conversation__property=prop))

    closed = Conversation.objects.get(property=prop, status="closed")
    assert closed.unread_count == 0 and closed.messages.filter(direction="in").exists()
    assert closed.messages.filter(direction="out", sent_by=world["front"]).exists()

    email = Conversation.objects.filter(property=prop, channel="email", status="open").first()
    first = email.messages.order_by("created_at").first()
    assert first.direction == "out" and first.subject and first.recipient == email.external_thread_key
    reply = email.messages.filter(direction="in").get()
    assert reply.subject.startswith("Re: ")

    # The lifecycle messages shown in the threads are recorded as dispatched.
    assert LifecycleDispatch.objects.filter(reservation=world["in_house"], event="confirmation").exists()


def test_nothing_is_sent_and_the_first_automation_run_does_not_flood_the_guests(world):
    messaging_seed.seed(world["ctx"])
    assert mail.outbox == []
    messages = Message.objects.count()

    run = automation.run("messaging.lifecycle_dispatch", world["prop"])

    assert run.status == "success"
    assert Message.objects.count() == messages and mail.outbox == []
    # …because what was already due (the arrival of today, the pre-arrival of the next days) is history.
    for key, event in (("arriving", "arrival_day"), ("soon", "pre_arrival")):
        dispatch = LifecycleDispatch.objects.get(reservation=world[key], event=event)
        assert dispatch.status in ("sent", "skipped")


def test_the_hotels_customize_some_templates(world):
    messaging_seed.seed(world["ctx"])
    confirmation = resolve_template(world["prop"], "confirmation", "email", "es")
    assert confirmation.source == "property" and "{{reservation.code}}" in confirmation.body
    custom = MessageTemplate.objects.filter(organization=world["prop"].organization, property__isnull=True)
    assert custom.exists() and all(row.name for row in custom)


def test_the_seed_is_idempotent(world):
    messaging_seed.seed(world["ctx"])
    counts = (
        Conversation.objects.count(),
        Message.objects.count(),
        LifecycleDispatch.objects.count(),
        MessageTemplate.objects.count(),
        LifecycleRule.objects.count(),
    )
    messaging_seed.seed(world["ctx"])
    assert counts == (
        Conversation.objects.count(),
        Message.objects.count(),
        LifecycleDispatch.objects.count(),
        MessageTemplate.objects.count(),
        LifecycleRule.objects.count(),
    )


def test_a_hotel_without_reservations_still_gets_an_inbox_contact(world):
    messaging_seed.seed(world["ctx"])
    sibling_threads = Conversation.objects.filter(property=world["sibling"])
    assert sibling_threads.filter(channel="whatsapp", reservation__isnull=True, unread_count__gt=0).exists()


def test_example_threads_never_mix_with_a_conversation_that_already_exists(world):
    """The automation may already have written to a demo guest (a rerun on a live database): that thread is
    left alone and the example uses another guest, so every example reads as one coherent story."""
    prop = world["prop"]
    today = timezone.localdate()
    booker = world["in_house"].booker
    existing = Conversation.objects.create(
        property=prop, channel="whatsapp", external_thread_key=booker.phone
    )
    Message.objects.create(
        conversation=existing, direction="out", channel="whatsapp", body="Recordatorio", status="delivered"
    )
    other = world["book"]("checked_in", today - timedelta(days=2), nights=4)

    messaging_seed.seed(world["ctx"])

    assert existing.messages.count() == 1
    example = Conversation.objects.get(property=prop, reservation=other, channel="whatsapp")
    assert example.messages.filter(direction="in").exists()
