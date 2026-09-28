"""Demo data of `ai` (plan C9): AI settings, the chatbot FAQ of every hotel in Spanish and English and a
chatbot conversation waiting for a person (with its alert). Idempotent; runs in well under a second."""

from datetime import datetime, time, timedelta

from django.utils import timezone

from apps.ai.features import ai_settings
from apps.ai.models import ChatbotConversation, PropertyFAQ

FAQS = {
    "aurora": [
        (
            "¿El desayuno está incluido?",
            "El desayuno buffet se sirve de 6:30 a 10:30 en el patio central. Está incluido "
            "en la tarifa «Con desayuno»; si no, cuesta $35.000 por persona.",
            "Is breakfast included?",
            "The buffet breakfast is served from 6:30 to 10:30 in the courtyard. It is included "
            "in the «Breakfast included» rate; otherwise it costs COP 35,000 per person.",
        ),
        (
            "¿Tienen parqueadero?",
            "No tenemos parqueadero propio; a una cuadra hay un parqueadero vigilado con convenio "
            "por $25.000 la noche.",
            "Do you have parking?",
            "We don't have our own parking; there is a guarded parking lot one block away at "
            "COP 25,000 per night.",
        ),
        (
            "¿Aceptan mascotas?",
            "Lo sentimos, en el hotel no se admiten mascotas (salvo perros de asistencia).",
            "Do you accept pets?",
            "Sorry, pets are not allowed in the hotel (assistance dogs are welcome).",
        ),
        (
            "¿A qué hora es el check-in y el check-out?",
            "El check-in es desde las 15:00 y el check-out hasta las 12:00. Guardamos tu equipaje sin costo.",
            "What time are check-in and check-out?",
            "Check-in is from 3 pm and check-out until 12 noon. We store your luggage for free.",
        ),
        (
            "¿Cómo llegar desde el aeropuerto?",
            "Estamos en el Centro Histórico, a 15 minutos del aeropuerto Rafael "
            "Núñez. Ofrecemos traslado por $90.000 por trayecto.",
            "How do I get there from the airport?",
            "We are in the Old Town, 15 minutes from Rafael Núñez airport. We "
            "offer a transfer for COP 90,000 each way.",
        ),
    ],
    "andino_mde": [
        (
            "¿El desayuno está incluido?",
            "El desayuno americano se sirve de 6:00 a 10:00 en el restaurante del primer "
            "piso; cuesta $30.000 por persona si tu tarifa no lo incluye.",
            "Is breakfast included?",
            "The American breakfast is served from 6 to 10 am in the ground-floor restaurant; "
            "it costs COP 30,000 per person if your rate doesn't include it.",
        ),
        (
            "¿Tienen parqueadero?",
            "Sí, tenemos parqueadero cubierto para huéspedes por $25.000 la noche, sujeto a disponibilidad.",
            "Do you have parking?",
            "Yes, covered guest parking for COP 25,000 per night, subject to availability.",
        ),
        (
            "¿Aceptan mascotas?",
            "Sí, somos pet friendly: aceptamos mascotas de hasta 10 kg con un cargo de $40.000 por estadía.",
            "Do you accept pets?",
            "Yes, we are pet friendly: pets up to 10 kg are welcome for COP 40,000 per stay.",
        ),
        (
            "¿A qué hora es el check-in y el check-out?",
            "El check-in es desde las 15:00 y el check-out hasta las 12:00.",
            "What time are check-in and check-out?",
            "Check-in is from 3 pm and check-out until 12 noon.",
        ),
        (
            "¿Cómo llegar al hotel?",
            "Estamos en El Poblado, a 5 minutos del Parque Lleras y a 45 minutos del aeropuerto "
            "José María Córdova.",
            "How do I get to the hotel?",
            "We are in El Poblado, 5 minutes from Parque Lleras and 45 minutes from José "
            "María Córdova airport.",
        ),
    ],
    "andino_bog": [
        (
            "¿El desayuno está incluido?",
            "Incluimos un desayuno sencillo (café, pan y fruta) de 7:00 a 10:00 en la cocina compartida.",
            "Is breakfast included?",
            "A simple breakfast (coffee, bread and fruit) is included from 7 to 10 am in the shared kitchen.",
        ),
        (
            "¿Tienen parqueadero?",
            "No tenemos parqueadero; te recomendamos llegar en taxi o en TransMilenio (estación "
            "Museo del Oro).",
            "Do you have parking?",
            "We don't have parking; we recommend coming by taxi or TransMilenio (Museo del Oro station).",
        ),
        (
            "¿Aceptan mascotas?",
            "No admitimos mascotas en los dormitorios compartidos.",
            "Do you accept pets?",
            "Pets are not allowed in the shared dorms.",
        ),
        (
            "¿A qué hora es el check-in y el check-out?",
            "El check-in es desde las 14:00 (recepción 24 horas) y el check-out hasta las 11:00.",
            "What time are check-in and check-out?",
            "Check-in is from 2 pm (24-hour front desk) and check-out until 11 am.",
        ),
        (
            "¿Cómo llegar al hostal?",
            "Estamos en La Candelaria, a 3 cuadras de la Plaza de Bolívar y a 30 minutos del "
            "aeropuerto El Dorado.",
            "How do I get to the hostel?",
            "We are in La Candelaria, 3 blocks from Plaza de Bolívar and 30 minutes from El Dorado airport.",
        ),
    ],
}
GREETINGS = {
    "aurora": {
        "es": "¡Hola! Soy el asistente de Casa Aurora. ¿Te ayudo con tu estadía en Cartagena?",
        "en": "Hi! I'm Casa Aurora's assistant. Can I help you with your stay in Cartagena?",
    },
}
HANDOFF_SESSION = "demo-aurora-handoff-0001"
FAQ_SESSION = "demo-aurora-faq-0000001"


def _at(ctx, days_ago: int, hour: int, minute: int) -> str:
    moment = datetime.combine(ctx.today - timedelta(days=days_ago), time(hour, minute))
    return timezone.make_aware(moment).isoformat()


def _seed_faqs(prop, entries) -> int:
    if PropertyFAQ.objects.filter(property=prop).exists():
        return 0
    rows = []
    for sort, (question_es, answer_es, question_en, answer_en) in enumerate(entries, start=1):
        rows.append(
            PropertyFAQ(property=prop, question=question_es, answer=answer_es, language="es", sort=sort)
        )
        rows.append(
            PropertyFAQ(property=prop, question=question_en, answer=answer_en, language="en", sort=sort)
        )
    PropertyFAQ.objects.bulk_create(rows)
    return len(rows)


def _seed_conversations(ctx, prop) -> None:
    from apps.ai.chatbot import _raise_handoff_alert

    if not ChatbotConversation.objects.filter(property=prop, session_id=FAQ_SESSION).exists():
        ChatbotConversation.objects.create(
            property=prop,
            session_id=FAQ_SESSION,
            language="es",
            last_message_at=_at(ctx, 2, 18, 41),
            messages=[
                {"role": "user", "content": "¿Tienen parqueadero?", "at": _at(ctx, 2, 18, 40)},
                {"role": "assistant", "content": FAQS["aurora"][1][1], "at": _at(ctx, 2, 18, 41)},
            ],
        )
    if ChatbotConversation.objects.filter(property=prop, session_id=HANDOFF_SESSION).exists():
        return
    conversation = ChatbotConversation.objects.create(
        property=prop,
        session_id=HANDOFF_SESSION,
        language="es",
        messages=[
            {
                "role": "user",
                "content": "Hola, quiero celebrar un aniversario con decoración en la habitación. ¿Se puede?",
                "at": _at(ctx, 1, 20, 14),
            },
            {
                "role": "assistant",
                "content": "Con gusto te comunico con el equipo del hotel. Déjanos tu nombre y un "
                "correo o teléfono y te contactaremos pronto.",
                "at": _at(ctx, 1, 20, 14),
            },
        ],
        handoff_requested=True,
        handoff_reason="low_confidence",
        handoff_at=_at(ctx, 1, 20, 14),
        contact={
            "name": "Mariana López",
            "email": "mariana.lopez@example.com",
            "phone": "+573001112233",
            "message": "Somos dos personas y llegamos el viernes.",
            "at": _at(ctx, 1, 20, 16),
        },
        last_message_at=_at(ctx, 1, 20, 16),
    )
    _raise_handoff_alert(conversation)


def seed(ctx) -> None:
    created = 0
    for key, prop in ctx.properties.items():
        row = ai_settings(prop)
        if key in GREETINGS and not row.chatbot_greeting:
            row.chatbot_greeting = GREETINGS[key]
            row.save(update_fields=["chatbot_greeting", "updated_at"])
        created += _seed_faqs(prop, FAQS.get(key, FAQS["andino_mde"]))
    if "aurora" in ctx.properties:
        _seed_conversations(ctx, ctx.properties["aurora"])
    ctx.log(f"ai: {created} preguntas frecuentes, conversación de chatbot con traspaso a una persona")
