"""Demo data of `ai` (plan C9 seed): AI settings, FAQs in Spanish and English for every hotel (breakfast,
parking, pets, hours, how to get there) and one chatbot conversation that asked for a person."""

import random
from datetime import date

import pytest

from apps.ai import seed as ai_seed
from apps.ai.models import AISettings, ChatbotConversation, PropertyFAQ
from apps.core.models import Alert
from apps.core.seed import SeedContext
from apps.core.tests.factories import OrganizationFactory, PropertyFactory

pytestmark = pytest.mark.django_db

TOPICS = ("desayuno", "parqueadero", "mascotas", "check-in", "llegar")


@pytest.fixture
def ctx(organization):
    andino = OrganizationFactory(name="Grupo Andino")
    context = SeedContext(today=date(2026, 9, 25), rng=random.Random(20260925))
    context.orgs = {"aurora": organization, "andino": andino}
    context.properties = {
        "aurora": PropertyFactory(organization=organization, name="Hotel Casa Aurora", city="Cartagena"),
        "andino_mde": PropertyFactory(organization=andino, name="Andino Medellín", city="Medellín"),
        "andino_bog": PropertyFactory(
            organization=andino, name="Andino Hostel Bogotá", city="Bogotá", property_type="hostel"
        ),
    }
    context.users = {}
    return context


def test_every_hotel_gets_its_faq_in_both_languages(ctx):
    ai_seed.seed(ctx)

    for prop in ctx.properties.values():
        spanish = " ".join(
            PropertyFAQ.objects.filter(property=prop, language="es").values_list("question", flat=True)
        )
        english = PropertyFAQ.objects.filter(property=prop, language="en")
        assert all(topic in spanish.lower() for topic in TOPICS), spanish
        assert english.count() == PropertyFAQ.objects.filter(property=prop, language="es").count() >= 5
        assert AISettings.objects.filter(property=prop, chatbot_enabled=True, copilot_enabled=True).exists()


def test_the_demo_has_a_conversation_waiting_for_a_person(ctx):
    ai_seed.seed(ctx)

    aurora = ctx.properties["aurora"]
    conversation = ChatbotConversation.objects.get(property=aurora, handoff_requested=True)
    assert conversation.contact["email"]
    assert [message["role"] for message in conversation.messages][:2] == ["user", "assistant"]
    alert = Alert.objects.get(property=aurora, kind="chatbot_handoff", resolved_at__isnull=True)
    assert alert.link.endswith(str(conversation.pk))


def test_seeding_twice_changes_nothing(ctx):
    ai_seed.seed(ctx)
    counts = (PropertyFAQ.objects.count(), ChatbotConversation.objects.count(), Alert.objects.count())

    ai_seed.seed(ctx)

    assert (PropertyFAQ.objects.count(), ChatbotConversation.objects.count(), Alert.objects.count()) == counts
