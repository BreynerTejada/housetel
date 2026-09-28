"""Demo data of messaging (plan C6 › Seed).

- Templates: the defaults (ES/EN, email and WhatsApp) of every lifecycle event plus `checkin_invitation` (C5)
  and `payment_link` (B4) are system templates in code (`defaults.SYSTEM_TEMPLATES`): they already apply to
  every hotel, also to the ones created later by signup. The seed adds the kind of customizations a hotel
  makes, so the editor shows the three levels: Casa Aurora signs its confirmation email (hotel override) and
  offers a welcome drink (custom organization template); Grupo Andino has a late check-out offer and the
  hostel its own arrival-day WhatsApp.
- Lifecycle rules: the six rules, enabled, for every hotel.
- An inbox per hotel built from real reservations of the demo: WhatsApp with an in-house guest (lifecycle
  messages already sent, an unread question and an internal note), WhatsApp with today's arrival (assigned to
  the front desk), an email reply of an upcoming guest, a WhatsApp contact without a booking and a closed
  thread with a guest who already left. The lifecycle messages shown are recorded as dispatched.
- History: the scheduled lifecycle messages already due when the demo is created (pre-arrival of the next
  days, today's arrivals, recent departures, payment reminders) are marked as dispatched without sending
  them. Otherwise the first run of `messaging.lifecycle_dispatch` would write to every guest of the demo at
  once; from then on the automation sends what becomes due, day by day.

Nothing is sent: rows are written directly (the demo must never email or message anybody). Idempotent: rules
and templates are get-or-create, the history is unique per (reservation, event) and a hotel whose inbox
already has a message from a guest keeps it.
"""

import random
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.messaging.defaults import EVENTS, SCHEDULED_EVENTS
from apps.messaging.lifecycle import due_reservations, effective_rule, ensure_rules
from apps.messaging.models import Conversation, LifecycleDispatch, Message, MessageTemplate
from apps.messaging.renderer import render_plain, render_whatsapp
from apps.messaging.services import _one_line, find_guest, guest_address, message_language, resolve_template
from apps.messaging.variables import build_variables

HISTORY_DETAIL = "Histórico del demo: ya se había enviado"
FRONT_DESK_USERS = {"aurora": "aurora_front", "andino_mde": "andino_front", "andino_bog": "andino_front"}

_MONTHS = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]

# What guests ask each hotel (by the guest's language: es, or en for everybody else).
TEXTS = {
    "aurora": {
        "in_house": {
            "es": "¡Hola! ¿Tienen toallas para la playa? Queremos ir a Bocagrande esta tarde 🏖️",
            "en": "Hi! Do you have beach towels? We'd like to go to Bocagrande this afternoon 🏖️",
        },
        "note": "Pedí a housekeeping dos toallas de playa para su habitación.",
        "arriving": {
            "es": "Buenos días 👋 Nuestro vuelo llega a las 9:40 p. m., ¿hay problema con el check-in tarde?",
            "en": "Good morning 👋 Our flight lands at 9:40 pm, is a late check-in OK?",
        },
        "email": {
            "es": "Hola,\n\n¿Sería posible agregar una cama para nuestro hijo de 6 años? "
            "¿Tiene costo adicional?\n\nMuchas gracias,\n{first_name}",
            "en": "Hello,\n\nCould you add an extra bed for our 6-year-old son? "
            "Is there an extra charge?\n\nMany thanks,\n{first_name}",
        },
        "contact": (
            "Carolina Mejía",
            [
                "Hola, buenas tardes 😊",
                "¿Tienen disponibilidad para 2 personas del {start} al {end}? ¿Cuánto cuesta "
                "la noche con desayuno?",
            ],
        ),
        "thanks": {
            "es": "¡Gracias a ustedes! Todo estuvo perfecto y el desayuno en la terraza, increíble. "
            "Volveremos en diciembre.",
            "en": "Thank you! Everything was perfect and the breakfast on the terrace was amazing. "
            "We'll be back in December.",
        },
        "answer": {
            "es": "¡Qué alegría leerte, {first_name}! Te esperamos en diciembre 😊",
            "en": "So happy to read this, {first_name}! See you in December 😊",
        },
    },
    "andino_mde": {
        "in_house": {
            "es": "Hola, ¿el parqueadero tiene costo? Llegué con carro 🚗",
            "en": "Hi, is there a charge for parking? I came by car 🚗",
        },
        "note": "Parqueadero: $ 25.000 por noche; lo cargamos al folio al hacer el check-out.",
        "arriving": {
            "es": "Hola, llegamos a las 10 a. m. ¿Nos pueden guardar las maletas hasta el check-in?",
            "en": "Hi, we arrive at 10 am. Can you keep our luggage until check-in?",
        },
        "email": {
            "es": "Buenas tardes,\n\n¿Me pueden enviar la factura a nombre de la empresa? "
            "Viajo por trabajo y les comparto el NIT al llegar.\n\nGracias,\n{first_name}",
            "en": "Good afternoon,\n\nCould you issue the invoice to my company? "
            "I'm traveling for work and will share the tax ID at check-in.\n\nThanks,\n{first_name}",
        },
        "contact": (
            "Julián Arango",
            ["Hola", "¿Tienen habitación familiar para el {start}? Somos 3 personas."],
        ),
        "thanks": {
            "es": "Muchas gracias por todo, la atención fue excelente.",
            "en": "Thanks a lot for everything, the service was excellent.",
        },
        "answer": {
            "es": "¡Gracias a ti, {first_name}! Fue un gusto recibirte.",
            "en": "Thank you, {first_name}! It was a pleasure having you.",
        },
    },
    "andino_bog": {
        "in_house": {
            "es": "¡Hola! ¿Hay lockers para la mochila? ¿Y el walking tour de mañana sale desde aquí?",
            "en": "Hi! Is there a locker for my backpack? And does tomorrow's walking tour start here?",
        },
        "note": "Walking tour 10 a. m. desde recepción. Lockers con candado propio (se vende en recepción).",
        "arriving": {
            "es": "Hola, llego en bus a las 6 a. m., ¿puedo dejar la maleta antes del check-in?",
            "en": "Hi, my bus arrives at 6 am, can I leave my bag before check-in?",
        },
        "email": {
            "es": "Hola,\n\n¿El dormitorio tiene cortinas en las camas y enchufe propio? "
            "Viajamos dos amigas.\n\nGracias,\n{first_name}",
            "en": "Hi,\n\nDo the dorm beds have curtains and their own plug? "
            "We're two friends traveling.\n\nThanks,\n{first_name}",
        },
        "contact": (
            "Lucía Fernández",
            ["Hola!", "¿Cuánto cuesta una cama en el dormitorio femenino para el {start}?"],
        ),
        "thanks": {
            "es": "¡Gracias! Me encantó el hostal y el tour por La Candelaria.",
            "en": "Thanks! I loved the hostel and the tour around La Candelaria.",
        },
        "answer": {
            "es": "¡Gracias por visitarnos, {first_name}! Vuelve pronto.",
            "en": "Thanks for staying with us, {first_name}! Come back soon.",
        },
    },
}
TEXTS["default"] = TEXTS["aurora"]

# Customizations of the demo hotels (see the module docstring).
ORGANIZATION_TEMPLATES = {
    "aurora": {
        "code": "welcome_drink",
        "name": "Cóctel de bienvenida",
        "bodies": {
            "es": "¡Hola {{guest.first_name}}! Te esperamos con un cóctel de bienvenida en la terraza de "
            "{{property.name}}, de 5 a 7 p. m. 🍹 Muestra este mensaje en el bar.",
            "en": "Hi {{guest.first_name}}! Enjoy a welcome drink on the terrace of {{property.name}}, "
            "from 5 to 7 pm 🍹 Just show this message at the bar.",
        },
    },
    "andino_mde": {
        "code": "late_checkout_offer",
        "name": "Oferta de late check-out",
        "bodies": {
            "es": "Hola {{guest.first_name}}, ¿quieres quedarte un poco más? Tenemos **late check-out "
            "hasta las 3 p. m.** por $ 80.000. Responde *SÍ* y lo dejamos listo.",
            "en": "Hi {{guest.first_name}}, would you like to stay a bit longer? We have **late check-out "
            "until 3 pm** for $ 80,000. Reply *YES* and we'll set it up.",
        },
    },
}
PROPERTY_TEMPLATES = {
    "aurora": {
        "code": "confirmation",
        "channel": "email",
        "language": "es",
        "subject": "¡Tu reserva en Casa Aurora está confirmada! · {{reservation.code}}",
        "body": "\n\n".join(
            [
                "Hola {{guest.first_name}},",
                "¡Qué alegría que vengas a Cartagena! Tu reserva en {{property.name}} está confirmada y ya "
                "estamos preparando tu habitación.",
                "**Código de reserva:** {{reservation.code}}\n"
                "**Llegada:** {{reservation.checkin}}, desde las {{property.check_in_time}}\n"
                "**Salida:** {{reservation.checkout}}, hasta las {{property.check_out_time}}\n"
                "**Habitación:** {{reservation.room_type}} · **Noches:** {{nights}}\n"
                "**Total:** {{reservation.total}}",
                "Desde tu portal puedes hacer el check-in en línea, pagar el saldo y pedirnos lo que "
                "necesites.",
                "[Ver mi reserva]({{portal_url}})",
                "Un secreto: al llegar pregunta por el cóctel de bienvenida en la terraza, con la mejor "
                "vista de la ciudad amurallada.",
                "Con cariño,\nValentina y el equipo de {{property.name}}",
            ]
        ),
    },
    "andino_bog": {
        "code": "arrival_day",
        "channel": "whatsapp",
        "language": "es",
        "subject": "",
        "body": "\n\n".join(
            [
                "¡Hoy llegas a {{property.name}}, {{guest.first_name}}! 🎒",
                "📍 {{property.address}}, La Candelaria\n"
                "🕒 Check-in desde las {{property.check_in_time}} (puedes dejar tu maleta antes)",
                "Tenemos lockers, cocina compartida y walking tour gratis a las 10 a. m. "
                "[Check-in en línea]({{checkin_url}})",
            ]
        ),
    },
}

# --- helpers -------------------------------------------------------------------------------------------


def _local(prop, day: date, clock: time) -> datetime:
    return datetime.combine(day, clock, tzinfo=ZoneInfo(prop.timezone or "America/Bogota"))


def _short_date(day: date) -> str:
    return f"{day.day} de {_MONTHS[day.month - 1]}"


def _lang(prop, guest, reservation=None) -> str:
    return message_language(prop, guest, reservation)


def _text(texts: dict, key: str, lang: str, **values) -> str:
    variants = texts[key]
    return variants.get(lang, variants["en"]).format(**values)


class _Thread:
    """Writes a conversation and its messages with past timestamps (as if they had happened)."""

    def __init__(self, prop, channel, address, *, guest=None, reservation=None, contact_name=""):
        self.prop = prop
        self.guest = guest
        self.reservation = reservation
        self.conversation, _ = Conversation.objects.get_or_create(
            property=prop,
            channel=channel,
            external_thread_key=address,
            defaults={
                "guest": guest,
                "reservation": reservation,
                "contact_name": contact_name or (guest.full_name if guest else ""),
            },
        )
        self.dispatched: list[tuple[str, str]] = []

    def _add(self, at: datetime, **fields) -> Message:
        message = Message.objects.create(
            conversation=self.conversation, reservation=self.reservation, status_updated_at=at, **fields
        )
        Message.objects.filter(pk=message.pk).update(created_at=at)
        message.created_at = at
        return message

    def template(self, code: str, at: datetime, *, status: str) -> Message:
        channel = self.conversation.channel
        template = resolve_template(self.prop, code, channel, _lang(self.prop, self.guest, self.reservation))
        values = build_variables(
            property=self.prop, guest=self.guest, reservation=self.reservation, language=template.language
        )
        if channel == "email":
            subject, body = (
                _one_line(render_plain(template.subject, values), 255),
                render_plain(template.body, values),
            )
        else:
            subject, body = "", render_whatsapp(template.body, values)
        self.dispatched.append((code, channel))
        return self._add(
            at,
            direction="out",
            channel=channel,
            sender_label=self.prop.name,
            subject=subject,
            body=body,
            recipient=self.conversation.external_thread_key,
            status=status,
            template_code=code,
        )

    def inbound(self, body: str, at: datetime, *, subject: str = "") -> Message:
        sender = self.guest.full_name if self.guest else self.conversation.contact_name
        return self._add(
            at,
            direction="in",
            channel=self.conversation.channel,
            sender_label=sender[:200],
            subject=subject,
            body=body,
            status="received",
        )

    def staff(self, body: str, at: datetime, *, author, subject: str = "") -> Message:
        return self._add(
            at,
            direction="out",
            channel=self.conversation.channel,
            sender_label=_author(author, self.prop),
            subject=subject,
            body=body,
            recipient=self.conversation.external_thread_key,
            status="sent",
            sent_by=author,
        )

    def note(self, body: str, at: datetime, *, author) -> Message:
        return self._add(
            at,
            direction="out",
            channel=Message.Channel.INTERNAL_NOTE,
            sender_label=_author(author, self.prop),
            body=body,
            status="sent",
            sent_by=author,
        )

    def finish(self, *, unread: int, status: str = "open", assigned_to=None) -> Conversation:
        conversation = self.conversation
        messages = conversation.messages.exclude(channel=Message.Channel.INTERNAL_NOTE).order_by(
            "-created_at"
        )
        last = messages.first()
        last_in = messages.filter(direction="in").first()
        conversation.last_message_at = last.created_at
        conversation.last_message_preview = _one_line(last.body)
        conversation.last_message_direction = last.direction
        conversation.last_inbound_at = last_in.created_at if last_in else None
        conversation.unread_count = unread
        conversation.status = status
        conversation.assigned_to = assigned_to
        conversation.save()
        if self.reservation is not None and self.dispatched:
            events = {}
            for code, channel in self.dispatched:
                events.setdefault(code, []).append(channel)
            LifecycleDispatch.objects.bulk_create(
                [
                    LifecycleDispatch(reservation=self.reservation, event=code, channels=channels)
                    for code, channels in events.items()
                    if code in EVENTS
                ],
                ignore_conflicts=True,
            )
        return conversation


def _author(user, prop) -> str:
    return ((getattr(user, "full_name", "") or getattr(user, "email", "")) if user else prop.name)[:200]


def _front_desk_user(ctx, key, prop):
    user = ctx.users.get(FRONT_DESK_USERS.get(key, ""))
    if user is not None:
        return user
    from apps.accounts.models import Membership

    membership = (
        Membership.objects.select_related("user")
        .filter(organization_id=prop.organization_id, is_active=True, role__code="front_desk")
        .order_by("created_at")
        .first()
    )
    return membership.user if membership else None


def _pick(rng, reservations, used: set, channel: str):
    """A reservation whose booker is reachable on `channel`, is not in another demo thread and has no
    conversation yet on that channel (the automation may already have written to them on a live database:
    an example must read as one coherent story)."""
    rows = reservations.select_related("booker", "property").order_by("checkin_date", "code")[:60]
    candidates = []
    for reservation in rows:
        address = guest_address(channel, reservation.booker)
        if not address or reservation.booker_id in used:
            continue
        taken = Conversation.objects.filter(
            property=reservation.property, channel=channel, external_thread_key=address
        ).exists()
        if not taken:
            candidates.append(reservation)
        if len(candidates) == 12:
            break
    if not candidates:
        return None
    reservation = rng.choice(candidates)
    used.add(reservation.booker_id)
    return reservation


def _booked_at(prop, reservation, now) -> datetime:
    """When the booking was confirmed: its creation, but always days before the arrival and in the past."""
    before_arrival = _local(prop, reservation.checkin_date - timedelta(days=5), time(11, 20))
    return min(reservation.created_at, before_arrival, now - timedelta(hours=6))


# --- threads -------------------------------------------------------------------------------------------


def _in_house_thread(prop, reservation, texts, staff, now):
    guest = reservation.booker
    lang = _lang(prop, guest, reservation)
    thread = _Thread(prop, "whatsapp", guest_address("whatsapp", guest), guest=guest, reservation=reservation)
    booked = _booked_at(prop, reservation, now)
    question_at = now - timedelta(minutes=38)
    thread.template("confirmation", booked, status="read")
    for code, day, clock in (
        ("pre_arrival", reservation.checkin_date - timedelta(days=3), time(9, 5)),
        ("arrival_day", reservation.checkin_date, time(9, 2)),
    ):
        at = _local(prop, day, clock)
        if booked < at < question_at - timedelta(hours=1):
            thread.template(code, at, status="read")
    thread.inbound(_text(texts, "in_house", lang), question_at)
    thread.note(texts["note"], now - timedelta(minutes=20), author=staff)
    return thread.finish(unread=1)


def _arriving_thread(prop, reservation, texts, staff, now):
    guest = reservation.booker
    lang = _lang(prop, guest, reservation)
    thread = _Thread(prop, "whatsapp", guest_address("whatsapp", guest), guest=guest, reservation=reservation)
    booked = _booked_at(prop, reservation, now)
    question_at = now - timedelta(hours=2, minutes=10)
    thread.template("confirmation", booked, status="read")
    pre_arrival = _local(prop, reservation.checkin_date - timedelta(days=3), time(9, 5))
    if booked < pre_arrival < question_at:
        thread.template("pre_arrival", pre_arrival, status="read")
    thread.inbound(_text(texts, "arriving", lang), question_at)
    return thread.finish(unread=1, assigned_to=staff)


def _email_thread(prop, reservation, texts, now):
    guest = reservation.booker
    lang = _lang(prop, guest, reservation)
    thread = _Thread(prop, "email", guest_address("email", guest), guest=guest, reservation=reservation)
    confirmation = thread.template("confirmation", _booked_at(prop, reservation, now), status="sent")
    reply = _text(texts, "email", lang, first_name=guest.first_name)
    thread.inbound(reply, now - timedelta(hours=5), subject=_one_line(f"Re: {confirmation.subject}", 255))
    return thread.finish(unread=1)


def _closed_thread(prop, reservation, texts, staff, now):
    guest = reservation.booker
    lang = _lang(prop, guest, reservation)
    thread = _Thread(prop, "email", guest_address("email", guest), guest=guest, reservation=reservation)
    sent_at = min(
        _local(prop, reservation.checkout_date + timedelta(days=1), time(9, 4)), now - timedelta(hours=5)
    )
    post_stay = thread.template("post_stay", sent_at, status="sent")
    subject = _one_line(f"Re: {post_stay.subject}", 255)
    thread.inbound(_text(texts, "thanks", lang), sent_at + timedelta(hours=2), subject=subject)
    thread.staff(
        _text(texts, "answer", lang, first_name=guest.first_name),
        sent_at + timedelta(hours=3),
        author=staff,
        subject=subject,
    )
    return thread.finish(unread=0, status="closed")


def _contact_thread(prop, texts, rng, now):
    """A prospect writes on WhatsApp without a booking: like the webhook, the number becomes a contact."""
    from apps.guests.services import upsert_guest
    from apps.guests.types import GuestInput

    name, bodies = texts["contact"]
    phone = f"+57315{rng.randrange(1_000_000, 9_999_999)}"
    guest = find_guest(prop, "whatsapp", phone)
    if guest is None:
        first, _, last = name.partition(" ")
        guest = upsert_guest(prop.organization, GuestInput(first_name=first, last_name=last, phone=phone))
    thread = _Thread(prop, "whatsapp", phone, guest=guest, contact_name=name)
    start = prop.business_date + timedelta(days=14)
    values = {"start": _short_date(start), "end": _short_date(start + timedelta(days=3))}
    for minutes, body in zip((27, 26), bodies, strict=False):
        thread.inbound(body.format(**values), now - timedelta(minutes=minutes))
    return thread.finish(unread=len(bodies))


def _seed_inbox(ctx, key, prop) -> int:
    from apps.bookings.models import Reservation

    rng = random.Random(f"messaging:{prop.slug}")
    texts = TEXTS.get(key, TEXTS["default"])
    staff = _front_desk_user(ctx, key, prop)
    now = timezone.now()
    today = prop.business_date
    reservations = Reservation.objects.filter(property=prop)
    used: set = set()
    threads = []
    if reservation := _pick(rng, reservations.filter(status="checked_in"), used, "whatsapp"):
        threads.append(_in_house_thread(prop, reservation, texts, staff, now))
    if reservation := _pick(
        rng, reservations.filter(status="confirmed", checkin_date=today), used, "whatsapp"
    ):
        threads.append(_arriving_thread(prop, reservation, texts, staff, now))
    upcoming = reservations.filter(
        status="confirmed",
        checkin_date__gte=today + timedelta(days=2),
        checkin_date__lte=today + timedelta(days=14),
    )
    if reservation := _pick(rng, upcoming, used, "email"):
        threads.append(_email_thread(prop, reservation, texts, now))
    departed = reservations.filter(
        status="checked_out", checkout_date__gte=today - timedelta(days=6), checkout_date__lt=today
    )
    if reservation := _pick(rng, departed, used, "email"):
        threads.append(_closed_thread(prop, reservation, texts, staff, now))
    threads.append(_contact_thread(prop, texts, rng, now))
    return len(threads)


def _seed_templates(key, prop) -> int:
    created = 0
    spec = ORGANIZATION_TEMPLATES.get(key)
    if spec is not None:
        for language, body in spec["bodies"].items():
            _, new = MessageTemplate.objects.get_or_create(
                organization=prop.organization,
                property=None,
                code=spec["code"],
                channel="whatsapp",
                language=language,
                defaults={"name": spec["name"], "body": body},
            )
            created += new
    spec = PROPERTY_TEMPLATES.get(key)
    if spec is not None:
        _, new = MessageTemplate.objects.get_or_create(
            organization=prop.organization,
            property=prop,
            code=spec["code"],
            channel=spec["channel"],
            language=spec["language"],
            defaults={"subject": spec["subject"], "body": spec["body"]},
        )
        created += new
    return created


def mark_due_as_history(prop) -> int:
    """Record the scheduled lifecycle messages already due as dispatched (without sending them)."""
    today = timezone.localtime(timezone.now(), ZoneInfo(prop.timezone or "America/Bogota")).date()
    marked = 0
    for event in SCHEDULED_EVENTS:
        rule = effective_rule(prop, event)
        if not rule["enabled"] or not rule["channels"]:
            continue
        while due := due_reservations(prop, event, rule["days_offset"], today):
            LifecycleDispatch.objects.bulk_create(
                [
                    LifecycleDispatch(
                        reservation=reservation,
                        event=event,
                        status=LifecycleDispatch.Status.SKIPPED,
                        channels=rule["channels"],
                        detail=HISTORY_DETAIL,
                    )
                    for reservation in due
                ],
                ignore_conflicts=True,
            )
            marked += len(due)
    return marked


def seed(ctx) -> None:
    for key, prop in ctx.properties.items():
        ensure_rules(prop)
        templates = _seed_templates(key, prop)
        has_inbox = Message.objects.filter(
            conversation__property=prop, direction=Message.Direction.IN
        ).exists()
        threads = 0 if has_inbox else _seed_inbox(ctx, key, prop)
        history = mark_due_as_history(prop)
        ctx.log(
            f"  {prop.name}: {threads} conversaciones de ejemplo, {templates} plantillas personalizadas, "
            f"{history} mensajes programados marcados como históricos"
        )
