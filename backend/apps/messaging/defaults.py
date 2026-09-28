"""System defaults (plan C6): the last step of template resolution (property → organization → system) and the
lifecycle rules a property starts with. Template text uses the renderer markup: `**bold**`, `[label](url)`
(alone in its paragraph it is an email button) and blank lines between paragraphs.

`checkin_invitation` is sent by the guest portal (C5) and `payment_link` by finance (B4): other apps rely on
these codes existing for both channels and languages.
"""

from datetime import time

EVENTS = ["confirmation", "pre_arrival", "arrival_day", "post_stay", "payment_reminder", "cancellation"]
SHARED_CODES = ["checkin_invitation", "payment_link"]
SYSTEM_CODES = [*EVENTS, *SHARED_CODES]
CHANNELS = ["email", "whatsapp"]
SCHEDULED_EVENTS = ["pre_arrival", "arrival_day", "post_stay", "payment_reminder"]

CODE_LABELS = {
    "confirmation": {"es": "Confirmación de reserva", "en": "Booking confirmation"},
    "pre_arrival": {
        "es": "Antes de la llegada (check-in en línea)",
        "en": "Before arrival (online check-in)",
    },
    "arrival_day": {"es": "Día de llegada", "en": "Arrival day"},
    "post_stay": {"es": "Después de la estadía", "en": "After the stay"},
    "payment_reminder": {"es": "Recordatorio de pago", "en": "Payment reminder"},
    "cancellation": {"es": "Cancelación", "en": "Cancellation"},
    "checkin_invitation": {"es": "Invitación al check-in en línea", "en": "Online check-in invitation"},
    "payment_link": {"es": "Link de pago", "en": "Payment link"},
}

DEFAULT_RULES = {
    "confirmation": {"days_offset": 0, "channels": ["email", "whatsapp"]},
    "pre_arrival": {"days_offset": 3, "channels": ["email", "whatsapp"]},
    "arrival_day": {"days_offset": 0, "channels": ["whatsapp"]},
    "post_stay": {"days_offset": 1, "channels": ["email"]},
    "payment_reminder": {"days_offset": 3, "channels": ["email", "whatsapp"]},
    "cancellation": {"days_offset": 0, "channels": ["email"]},
}
DEFAULT_SEND_AFTER = time(9, 0)


def default_rule(event: str) -> dict:
    values = DEFAULT_RULES[event]
    return {
        "event": event,
        "enabled": True,
        "days_offset": values["days_offset"],
        "channels": list(values["channels"]),
        "template_code": event,
        "send_after": DEFAULT_SEND_AFTER,
    }


def _t(subject: str, *paragraphs: str) -> dict:
    """A template: its subject (email only) and body paragraphs (joined by a blank line). A `\n` inside a
    paragraph is a line break of the message."""
    return {"subject": subject, "body": "\n\n".join(paragraphs)}


SYSTEM_TEMPLATES: dict[tuple[str, str, str], dict] = {
    # --- confirmation ------------------------------------------------------------------------------------
    ("confirmation", "email", "es"): _t(
        "Reserva confirmada · {{reservation.code}} · {{property.name}}",
        "Hola {{guest.first_name}},",
        "¡Gracias por elegir {{property.name}}! Tu reserva está confirmada y ya estamos preparando todo para "
        "recibirte.",
        "**Código de reserva:** {{reservation.code}}\n"
        "**Llegada:** {{reservation.checkin}}, desde las {{property.check_in_time}}\n"
        "**Salida:** {{reservation.checkout}}, hasta las {{property.check_out_time}}\n"
        "**Habitación:** {{reservation.room_type}}\n"
        "**Huéspedes:** {{reservation.guests}} · **Noches:** {{nights}}\n"
        "**Total:** {{reservation.total}}",
        "En tu portal de huésped puedes revisar la reserva, hacer el check-in en línea y pagar el saldo "
        "cuando quieras.",
        "[Ver mi reserva]({{portal_url}})",
        "¿Alguna pregunta o petición especial? Responde este correo o escríbenos al {{property.phone}}.",
        "¡Te esperamos!\nEquipo de {{property.name}}",
    ),
    ("confirmation", "email", "en"): _t(
        "Booking confirmed · {{reservation.code}} · {{property.name}}",
        "Hi {{guest.first_name}},",
        "Thank you for choosing {{property.name}}! Your booking is confirmed and we are already getting "
        "ready to welcome you.",
        "**Booking code:** {{reservation.code}}\n"
        "**Arrival:** {{reservation.checkin}}, from {{property.check_in_time}}\n"
        "**Departure:** {{reservation.checkout}}, until {{property.check_out_time}}\n"
        "**Room:** {{reservation.room_type}}\n"
        "**Guests:** {{reservation.guests}} · **Nights:** {{nights}}\n"
        "**Total:** {{reservation.total}}",
        "In your guest portal you can review the booking, check in online and pay the balance whenever you "
        "like.",
        "[View my booking]({{portal_url}})",
        "Any questions or special requests? Just reply to this email or call us at {{property.phone}}.",
        "See you soon!\nThe {{property.name}} team",
    ),
    ("confirmation", "whatsapp", "es"): _t(
        "",
        "¡Hola {{guest.first_name}}! Tu reserva en {{property.name}} está confirmada ✅",
        "**Código:** {{reservation.code}}\n"
        "**Llegada:** {{reservation.checkin}} (desde las {{property.check_in_time}})\n"
        "**Salida:** {{reservation.checkout}}\n"
        "**Huéspedes:** {{reservation.guests}}",
        "[Tu portal de huésped]({{portal_url}})",
        "Por aquí mismo puedes escribirnos cualquier pregunta.",
    ),
    ("confirmation", "whatsapp", "en"): _t(
        "",
        "Hi {{guest.first_name}}! Your booking at {{property.name}} is confirmed ✅",
        "**Code:** {{reservation.code}}\n"
        "**Arrival:** {{reservation.checkin}} (from {{property.check_in_time}})\n"
        "**Departure:** {{reservation.checkout}}\n"
        "**Guests:** {{reservation.guests}}",
        "[Your guest portal]({{portal_url}})",
        "Feel free to message us here with any question.",
    ),
    # --- pre_arrival -------------------------------------------------------------------------------------
    ("pre_arrival", "email", "es"): _t(
        "Tu llegada a {{property.name}} se acerca: haz el check-in en línea",
        "Hola {{guest.first_name}},",
        "¡Ya casi llega el día! Te esperamos el {{reservation.checkin}} a partir de las "
        "{{property.check_in_time}}.",
        "Ahorra tiempo en la recepción: completa ahora el check-in en línea con los datos de los huéspedes, "
        "la foto del documento y tu hora estimada de llegada. Toma solo un par de minutos.",
        "[Hacer check-in en línea]({{checkin_url}})",
        "¿Necesitas traslado desde el aeropuerto, una cama extra o llegar más temprano? Responde este correo "
        "y lo coordinamos.",
        "Hasta pronto,\nEquipo de {{property.name}}",
    ),
    ("pre_arrival", "email", "en"): _t(
        "Your stay at {{property.name}} is coming up: check in online",
        "Hi {{guest.first_name}},",
        "The day is almost here! We look forward to welcoming you on {{reservation.checkin}} from "
        "{{property.check_in_time}}.",
        "Skip the front-desk wait: complete your online check-in now with your guests' details, a photo of "
        "your ID and your estimated arrival time. It only takes a couple of minutes.",
        "[Check in online]({{checkin_url}})",
        "Need an airport transfer, an extra bed or an early arrival? Reply to this email and we will arrange "
        "it.",
        "See you soon,\nThe {{property.name}} team",
    ),
    ("pre_arrival", "whatsapp", "es"): _t(
        "",
        "¡Hola {{guest.first_name}}! 🧳 Faltan pocos días para tu llegada a {{property.name}} el "
        "{{reservation.checkin}}.",
        "Adelanta tu registro y evita filas en la recepción:\n[Check-in en línea]({{checkin_url}})",
        "¿Nos cuentas a qué hora llegas? Responde por aquí.",
    ),
    ("pre_arrival", "whatsapp", "en"): _t(
        "",
        "Hi {{guest.first_name}}! 🧳 Your arrival at {{property.name}} on {{reservation.checkin}} is just a "
        "few days away.",
        "Check in online and skip the queue at the front desk:\n[Online check-in]({{checkin_url}})",
        "What time will you arrive? Just reply here.",
    ),
    # --- arrival_day -------------------------------------------------------------------------------------
    ("arrival_day", "email", "es"): _t(
        "¡Hoy te esperamos en {{property.name}}!",
        "Hola {{guest.first_name}},",
        "¡Hoy es el día! Tu habitación estará lista desde las {{property.check_in_time}}.",
        "**Dirección:** {{property.address}}, {{property.city}}\n**Teléfono:** {{property.phone}}",
        "Si aún no lo hiciste, completa el check-in en línea y entra directo a descansar.",
        "[Hacer check-in en línea]({{checkin_url}})",
        "¡Buen viaje!\nEquipo de {{property.name}}",
    ),
    ("arrival_day", "email", "en"): _t(
        "We're expecting you today at {{property.name}}!",
        "Hi {{guest.first_name}},",
        "Today is the day! Your room will be ready from {{property.check_in_time}}.",
        "**Address:** {{property.address}}, {{property.city}}\n**Phone:** {{property.phone}}",
        "If you haven't yet, complete your online check-in and head straight to your room.",
        "[Check in online]({{checkin_url}})",
        "Safe travels!\nThe {{property.name}} team",
    ),
    ("arrival_day", "whatsapp", "es"): _t(
        "",
        "¡Hoy es el día, {{guest.first_name}}! 🌴 Te esperamos en {{property.name}} desde las "
        "{{property.check_in_time}}.",
        "📍 {{property.address}}, {{property.city}}",
        "Si ya sabes tu hora de llegada, cuéntanos por aquí. [Check-in en línea]({{checkin_url}})",
    ),
    ("arrival_day", "whatsapp", "en"): _t(
        "",
        "Today's the day, {{guest.first_name}}! 🌴 We're expecting you at {{property.name}} from "
        "{{property.check_in_time}}.",
        "📍 {{property.address}}, {{property.city}}",
        "Let us know your arrival time here. [Online check-in]({{checkin_url}})",
    ),
    # --- post_stay ---------------------------------------------------------------------------------------
    ("post_stay", "email", "es"): _t(
        "Gracias por hospedarte en {{property.name}}",
        "Hola {{guest.first_name}},",
        "Gracias por quedarte con nosotros. Esperamos que tu estadía haya sido tan buena como la imaginaste.",
        "¿Nos cuentas cómo te fue? Tu opinión nos ayuda a mejorar y a que otros viajeros nos conozcan.",
        "[Contarnos cómo te fue]({{review_url}})",
        "¡Vuelve pronto! Para tu próxima visita escríbenos directamente y te daremos la mejor tarifa "
        "disponible.",
        "Un abrazo,\nEquipo de {{property.name}}",
    ),
    ("post_stay", "email", "en"): _t(
        "Thank you for staying at {{property.name}}",
        "Hi {{guest.first_name}},",
        "Thank you for staying with us. We hope your stay was everything you imagined.",
        "Would you tell us how it went? Your feedback helps us improve and helps other travelers find us.",
        "[Share your feedback]({{review_url}})",
        "Come back soon! For your next visit, write to us directly and we'll give you our best available "
        "rate.",
        "Warm regards,\nThe {{property.name}} team",
    ),
    ("post_stay", "whatsapp", "es"): _t(
        "",
        "¡Gracias por visitarnos, {{guest.first_name}}! 🙌 Esperamos que hayas disfrutado {{property.name}}.",
        "¿Nos regalas un minuto para contarnos cómo te fue?\n[Dejar mi opinión]({{review_url}})",
    ),
    ("post_stay", "whatsapp", "en"): _t(
        "",
        "Thank you for visiting, {{guest.first_name}}! 🙌 We hope you enjoyed {{property.name}}.",
        "Could you spare a minute to tell us how it went?\n[Leave my feedback]({{review_url}})",
    ),
    # --- payment_reminder --------------------------------------------------------------------------------
    ("payment_reminder", "email", "es"): _t(
        "Saldo pendiente de tu reserva {{reservation.code}}",
        "Hola {{guest.first_name}},",
        "Te recordamos que tu reserva en {{property.name}} para el {{reservation.checkin}} tiene un saldo "
        "pendiente de **{{balance}}**.",
        "Puedes pagarlo en línea de forma segura (tarjeta, PSE o Nequi) desde tu portal de huésped:",
        "[Pagar mi saldo]({{payment_url}})",
        "Si ya hiciste el pago, ignora este mensaje. ¿Dudas? Escríbenos al {{property.phone}}.",
        "Equipo de {{property.name}}",
    ),
    ("payment_reminder", "email", "en"): _t(
        "Balance due for your booking {{reservation.code}}",
        "Hi {{guest.first_name}},",
        "A friendly reminder that your booking at {{property.name}} on {{reservation.checkin}} has a balance "
        "due of **{{balance}}**.",
        "You can pay it securely online (card, PSE or Nequi) from your guest portal:",
        "[Pay my balance]({{payment_url}})",
        "If you have already paid, please ignore this message. Questions? Call us at {{property.phone}}.",
        "The {{property.name}} team",
    ),
    ("payment_reminder", "whatsapp", "es"): _t(
        "",
        "Hola {{guest.first_name}}, te recordamos que tu reserva **{{reservation.code}}** en "
        "{{property.name}} tiene un saldo pendiente de **{{balance}}**.",
        "[Pagar en línea]({{payment_url}})",
    ),
    ("payment_reminder", "whatsapp", "en"): _t(
        "",
        "Hi {{guest.first_name}}, a reminder that your booking **{{reservation.code}}** at {{property.name}} "
        "has a balance due of **{{balance}}**.",
        "[Pay online]({{payment_url}})",
    ),
    # --- cancellation ------------------------------------------------------------------------------------
    ("cancellation", "email", "es"): _t(
        "Reserva cancelada · {{reservation.code}}",
        "Hola {{guest.first_name}},",
        "Confirmamos que tu reserva **{{reservation.code}}** en {{property.name}} ({{reservation.checkin}} – "
        "{{reservation.checkout}}) fue cancelada.",
        "**Penalidad aplicada:** {{reservation.cancellation_fee}}",
        "Si fue un error o quieres reservar otras fechas, responde este correo o escríbenos al "
        "{{property.phone}}. Será un gusto recibirte en otra ocasión.",
        "Equipo de {{property.name}}",
    ),
    ("cancellation", "email", "en"): _t(
        "Booking cancelled · {{reservation.code}}",
        "Hi {{guest.first_name}},",
        "We confirm that your booking **{{reservation.code}}** at {{property.name}} ({{reservation.checkin}} "
        "– {{reservation.checkout}}) has been cancelled.",
        "**Cancellation fee:** {{reservation.cancellation_fee}}",
        "If this was a mistake or you would like other dates, reply to this email or call us at "
        "{{property.phone}}. We would love to welcome you another time.",
        "The {{property.name}} team",
    ),
    ("cancellation", "whatsapp", "es"): _t(
        "",
        "Hola {{guest.first_name}}, tu reserva **{{reservation.code}}** en {{property.name}} "
        "({{reservation.checkin}}) fue cancelada. Penalidad: {{reservation.cancellation_fee}}.",
        "Si quieres reservar otras fechas, escríbenos por aquí.",
    ),
    ("cancellation", "whatsapp", "en"): _t(
        "",
        "Hi {{guest.first_name}}, your booking **{{reservation.code}}** at {{property.name}} "
        "({{reservation.checkin}}) has been cancelled. Cancellation fee: {{reservation.cancellation_fee}}.",
        "If you would like other dates, just message us here.",
    ),
    # --- checkin_invitation (guest portal, C5) -----------------------------------------------------------
    ("checkin_invitation", "email", "es"): _t(
        "Haz tu check-in en línea · {{property.name}}",
        "Hola {{guest.first_name}},",
        "Para tu llegada el {{reservation.checkin}} puedes adelantar el registro desde tu celular: datos de "
        "los huéspedes, foto del documento y firma. Al llegar solo recogerás tu llave.",
        "[Hacer check-in en línea]({{checkin_url}})",
        "El enlace es personal: no lo compartas.",
        "Equipo de {{property.name}}",
    ),
    ("checkin_invitation", "email", "en"): _t(
        "Check in online · {{property.name}}",
        "Hi {{guest.first_name}},",
        "Ahead of your arrival on {{reservation.checkin}} you can complete your registration from your "
        "phone: guest details, a photo of your ID and your signature. When you arrive you will just pick up "
        "your key.",
        "[Check in online]({{checkin_url}})",
        "This link is personal: please don't share it.",
        "The {{property.name}} team",
    ),
    ("checkin_invitation", "whatsapp", "es"): _t(
        "",
        "¡Hola {{guest.first_name}}! Adelanta tu registro en {{property.name}} desde el celular y al llegar "
        "solo recoges tu llave 🔑",
        "[Check-in en línea]({{checkin_url}})",
    ),
    ("checkin_invitation", "whatsapp", "en"): _t(
        "",
        "Hi {{guest.first_name}}! Complete your registration at {{property.name}} from your phone and just "
        "pick up your key when you arrive 🔑",
        "[Online check-in]({{checkin_url}})",
    ),
    # --- payment_link (finance, B4) ----------------------------------------------------------------------
    ("payment_link", "email", "es"): _t(
        "Link de pago · reserva {{reservation.code}}",
        "Hola {{guest.first_name}},",
        "Aquí tienes el link para pagar **{{amount}}** de tu reserva {{reservation.code}} en "
        "{{property.name}}. El pago es seguro y puedes usar tarjeta, PSE o Nequi.",
        "[Pagar {{amount}}]({{payment_url}})",
        "El link vence el {{expires_at}}. Referencia: {{reference}}.",
        "Equipo de {{property.name}}",
    ),
    ("payment_link", "email", "en"): _t(
        "Payment link · booking {{reservation.code}}",
        "Hi {{guest.first_name}},",
        "Here is the link to pay **{{amount}}** for your booking {{reservation.code}} at {{property.name}}. "
        "The payment is secure and you can use card, PSE or Nequi.",
        "[Pay {{amount}}]({{payment_url}})",
        "The link expires on {{expires_at}}. Reference: {{reference}}.",
        "The {{property.name}} team",
    ),
    ("payment_link", "whatsapp", "es"): _t(
        "",
        "Hola {{guest.first_name}}, este es tu link para pagar **{{amount}}** de la reserva "
        "{{reservation.code}} en {{property.name}}:\n"
        "[Pagar en línea]({{payment_url}})",
        "Vence el {{expires_at}}.",
    ),
    ("payment_link", "whatsapp", "en"): _t(
        "",
        "Hi {{guest.first_name}}, here is your link to pay **{{amount}}** for booking {{reservation.code}} "
        "at {{property.name}}:\n"
        "[Pay online]({{payment_url}})",
        "It expires on {{expires_at}}.",
    ),
}
