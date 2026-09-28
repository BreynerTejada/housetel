"""`send_message` (spec §4.2 contract): template → rendered text → provider per channel → conversation +
message."""

import smtplib

import pytest
from django.core import mail
from django.core.mail import EmailMultiAlternatives

from apps.bookings.tests.factories import ReservationFactory
from apps.core import integrations
from apps.core.errors import DomainError
from apps.guests.tests.factories import GuestFactory
from apps.messaging.models import Conversation, Message
from apps.messaging.services import send_message
from apps.messaging.tests.factories import MessageTemplateFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _frontend(settings):
    settings.FRONTEND_URL = "http://front.test"


@pytest.fixture
def guest(prop):
    return GuestFactory(
        organization=prop.organization, first_name="Ana", email="ana@example.com", phone="+573001112233"
    )


@pytest.fixture
def reservation(prop, guest):
    return ReservationFactory(property=prop, booker=guest, code="HT-ABC123")


def _set_mode(prop, kind, mode, **extra):
    setting = integrations.get_setting(prop, kind)
    setting.mode = mode
    for field, value in extra.items():
        setattr(setting, field, value)
    setting.save()


class TestEmail:
    def test_real_mode_sends_through_smtp_and_records_the_message(self, prop, guest, reservation):
        MessageTemplateFactory(
            property=prop,
            subject="Reserva {{reservation.code}}",
            body="Hola {{guest.first_name}}\n\n[Ver]({{portal_url}})",
        )
        (out,) = send_message(property=prop, template_code="confirmation", reservation=reservation)

        assert (out.channel, out.to, out.status, out.subject, out.template_code) == (
            "email",
            "ana@example.com",
            "sent",
            "Reserva HT-ABC123",
            "confirmation",
        )
        (email,) = mail.outbox
        assert (email.to, email.subject, email.from_email) == (
            ["ana@example.com"],
            "Reserva HT-ABC123",
            f"{prop.name} <no-reply@housetel.co>",
        )
        assert email.body.startswith("Hola Ana\n\nVer: http://front.test/g/")
        html, mimetype = email.alternatives[0]
        assert mimetype == "text/html"
        assert prop.name in html and 'href="http://front.test/g/' in html and "Hola Ana" in html

        message = Message.objects.get(pk=out.message_id)
        assert (message.direction, message.channel, message.status, message.template_code) == (
            "out",
            "email",
            "sent",
            "confirmation",
        )
        assert (message.recipient, message.reservation, message.subject) == (
            "ana@example.com",
            reservation,
            "Reserva HT-ABC123",
        )
        assert message.provider_message_id == email.extra_headers["Message-ID"] == out.provider_message_id
        conversation = message.conversation
        assert (
            conversation.channel,
            conversation.external_thread_key,
            conversation.guest,
            conversation.reservation,
        ) == ("email", "ana@example.com", guest, reservation)
        assert conversation.last_message_at == message.created_at
        assert conversation.last_message_direction == "out" and conversation.unread_count == 0

    def test_guests_reply_to_the_hotel(self, prop, reservation):
        send_message(property=prop, template_code="confirmation", reservation=reservation)
        assert mail.outbox[0].reply_to == [prop.email]

    def test_guest_values_are_escaped_in_the_html(self, prop, guest, reservation):
        guest.first_name = "<b>Ana</b>"
        guest.save()
        MessageTemplateFactory(property=prop, body="Hola {{guest.first_name}}")
        send_message(property=prop, template_code="confirmation", reservation=reservation)
        html = mail.outbox[0].alternatives[0][0]
        assert "<b>Ana</b>" not in html and "&lt;b&gt;Ana&lt;/b&gt;" in html

    def test_simulated_mode_only_records(self, prop, reservation):
        _set_mode(prop, "email", "simulated")
        (out,) = send_message(property=prop, template_code="confirmation", reservation=reservation)
        assert mail.outbox == []
        assert out.status == "sent" and out.provider_message_id.startswith("SIMMAIL-")
        assert Message.objects.get(pk=out.message_id).status == "sent"

    def test_an_smtp_failure_is_recorded_and_never_raised(self, prop, reservation, monkeypatch):
        def refuse(self, fail_silently=False):
            raise smtplib.SMTPRecipientsRefused({"ana@example.com": (550, b"no mailbox")})

        monkeypatch.setattr(EmailMultiAlternatives, "send", refuse)
        (out,) = send_message(property=prop, template_code="confirmation", reservation=reservation)
        message = Message.objects.get(pk=out.message_id)
        assert (out.status, message.status) == ("failed", "failed")
        assert "no mailbox" in message.error and out.error == message.error


class TestWhatsApp:
    def test_simulated_whatsapp_is_delivered_with_whatsapp_markup(self, prop, reservation):
        MessageTemplateFactory(
            property=prop, channel="whatsapp", subject="", body="Reserva **{{reservation.code}}**"
        )
        (out,) = send_message(
            property=prop, template_code="confirmation", reservation=reservation, channels=("whatsapp",)
        )
        assert (out.channel, out.to, out.status, out.body) == (
            "whatsapp",
            "+573001112233",
            "delivered",
            "Reserva *HT-ABC123*",
        )
        assert out.provider_message_id.startswith("SIMWA-")
        conversation = Conversation.objects.get()
        assert (conversation.channel, conversation.external_thread_key) == ("whatsapp", "+573001112233")

    def test_both_channels_in_one_call(self, prop, reservation):
        result = send_message(
            property=prop,
            template_code="confirmation",
            reservation=reservation,
            channels=("email", "whatsapp"),
        )
        assert [(m.channel, m.status) for m in result] == [("email", "sent"), ("whatsapp", "delivered")]
        assert Conversation.objects.count() == 2


class TestLanguage:
    @pytest.fixture(autouse=True)
    def _templates(self, prop):
        MessageTemplateFactory(property=prop, language="es", subject="Hola", body="Hola")
        MessageTemplateFactory(property=prop, language="en", subject="Hello", body="Hello")

    def test_the_guest_language_is_used(self, prop, guest, reservation):
        guest.language = "en"
        guest.save()
        (out,) = send_message(property=prop, template_code="confirmation", reservation=reservation)
        assert out.subject == "Hello"

    def test_an_explicit_language_wins(self, prop, guest, reservation):
        guest.language = "en"
        guest.save()
        (out,) = send_message(
            property=prop, template_code="confirmation", reservation=reservation, language="es"
        )
        assert out.subject == "Hola"

    def test_an_unsupported_language_falls_back_to_the_hotel_language(self, prop, guest, reservation):
        guest.language = "fr"
        guest.save()
        reservation.language = "fr"
        reservation.save()
        prop.default_language = "en"
        prop.save()
        (out,) = send_message(property=prop, template_code="confirmation", reservation=reservation)
        assert out.subject == "Hello"


class TestRecipients:
    def test_without_an_address_the_channel_is_skipped(self, prop, guest, reservation):
        guest.email = ""
        guest.save()
        (out,) = send_message(property=prop, template_code="confirmation", reservation=reservation)
        assert (out.status, out.to, out.message_id) == ("skipped", "", None)
        assert out.error and Message.objects.count() == 0 and mail.outbox == []

    def test_an_explicit_address_is_used_for_its_channel_only(self, prop, reservation):
        result = send_message(
            property=prop,
            template_code="confirmation",
            reservation=reservation,
            to="otra@example.com",
            channels=("email", "whatsapp"),
        )
        assert [m.to for m in result] == ["otra@example.com", "+573001112233"]
        assert mail.outbox[0].to == ["otra@example.com"]

    def test_a_message_can_go_to_an_address_without_a_guest(self, prop):
        (out,) = send_message(property=prop, template_code="checkin_invitation", to="solo@example.com")
        assert (out.status, out.to) == ("sent", "solo@example.com")
        assert Conversation.objects.get().guest is None

    def test_an_inactive_template_switches_its_channel_off(self, prop, reservation):
        MessageTemplateFactory(property=prop, is_active=False)
        (out,) = send_message(property=prop, template_code="confirmation", reservation=reservation)
        assert out.status == "skipped" and mail.outbox == []

    def test_a_disabled_integration_skips_the_channel(self, prop, reservation):
        _set_mode(prop, "email", "real", enabled=False)
        (out,) = send_message(property=prop, template_code="confirmation", reservation=reservation)
        assert out.status == "skipped" and mail.outbox == []

    def test_the_same_address_reuses_its_conversation(self, prop, guest, reservation):
        later = ReservationFactory(property=prop, booker=guest)
        send_message(property=prop, template_code="confirmation", reservation=reservation)
        send_message(property=prop, template_code="confirmation", reservation=later)
        conversation = Conversation.objects.get()
        assert conversation.messages.count() == 2 and conversation.reservation == later

    def test_an_unknown_template_is_an_error(self, prop, reservation):
        with pytest.raises(DomainError) as error:
            send_message(property=prop, template_code="nope", reservation=reservation)
        assert error.value.code == "template_not_found"


def test_the_finance_payment_link_context_reaches_both_channels(prop, reservation):
    context = {
        "payment_url": "http://front.test/sim/pay/HT-ABC123-X",
        "amount": "$ 200.000",
        "reference": "HT-ABC123-X",
        "expires_at": "2026-09-27T23:44:51+00:00",
    }
    email, whatsapp = send_message(
        property=prop,
        template_code="payment_link",
        reservation=reservation,
        channels=("email", "whatsapp"),
        context=context,
    )
    assert (email.status, whatsapp.status) == ("sent", "delivered")
    for body in (mail.outbox[0].body, whatsapp.body):
        assert "$ 200.000" in body and "http://front.test/sim/pay/HT-ABC123-X" in body
    assert "27 de septiembre de 2026, 18:44" in mail.outbox[0].body


class TestCustomMessage:
    """Free text through the contract (e.g. the AI copilot's "send this message" action): `custom_message`
    wraps `context["message"]` (and an optional `context["subject"]`). The text is data: escaped in the HTML
    and never parsed as markup."""

    def test_the_text_goes_out_on_both_channels(self, prop, reservation):
        text = "Hola Ana, tu habitación <b>ya</b> está lista"
        email, whatsapp = send_message(
            property=prop,
            template_code="custom_message",
            reservation=reservation,
            channels=("email", "whatsapp"),
            context={"message": text},
        )
        assert (email.status, whatsapp.status) == ("sent", "delivered")
        assert mail.outbox[0].subject == f"Mensaje de {prop.name}"
        assert mail.outbox[0].body == text
        assert "&lt;b&gt;ya&lt;/b&gt;" in mail.outbox[0].alternatives[0][0]
        assert whatsapp.body == text
        assert Message.objects.get(pk=whatsapp.message_id).template_code == "custom_message"

    def test_the_caller_can_set_the_subject_and_the_guest_language_is_kept(self, prop, guest, reservation):
        guest.language = "en"
        guest.save()
        (email,) = send_message(
            property=prop,
            template_code="custom_message",
            reservation=reservation,
            context={"message": "Hi", "subject": "Your room"},
        )
        assert (email.subject, mail.outbox[0].body) == ("Your room", "Hi")
        (email,) = send_message(
            property=prop, template_code="custom_message", reservation=reservation, context={"message": "Hi"}
        )
        assert email.subject == f"Message from {prop.name}"

    def test_without_a_text_nothing_is_sent(self, prop, reservation):
        with pytest.raises(DomainError) as error:
            send_message(property=prop, template_code="custom_message", reservation=reservation, context={})
        assert error.value.code == "message_required"
        assert Message.objects.count() == 0
