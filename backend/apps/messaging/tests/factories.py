import factory

from apps.core.tests.factories import PropertyFactory
from apps.messaging.models import Conversation, LifecycleRule, Message, MessageTemplate


class MessageTemplateFactory(factory.django.DjangoModelFactory):
    """Property-level template. Organization-level:
    `MessageTemplateFactory(property=None, organization=org)`."""

    class Meta:
        model = MessageTemplate

    property = factory.SubFactory(PropertyFactory)
    organization = factory.LazyAttribute(lambda o: o.property.organization if o.property else None)
    code = "confirmation"
    channel = MessageTemplate.Channel.EMAIL
    language = "es"
    subject = "Asunto {{reservation.code}}"
    body = "Hola {{guest.first_name}}"


class ConversationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Conversation

    property = factory.SubFactory(PropertyFactory)
    channel = Conversation.Channel.WHATSAPP
    external_thread_key = factory.Sequence(lambda n: f"+57310{n:07d}")
    contact_name = "Laura Gómez"


class MessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Message

    conversation = factory.SubFactory(ConversationFactory)
    direction = Message.Direction.IN
    channel = factory.SelfAttribute("conversation.channel")
    body = "Hola, ¿a qué hora es el check-in?"
    status = Message.Status.RECEIVED
    sender_label = factory.SelfAttribute("conversation.contact_name")


class LifecycleRuleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LifecycleRule

    property = factory.SubFactory(PropertyFactory)
    event = LifecycleRule.Event.CONFIRMATION
    enabled = True
    days_offset = 0
    channels = factory.LazyFunction(lambda: ["email"])
    template_code = factory.SelfAttribute("event")
