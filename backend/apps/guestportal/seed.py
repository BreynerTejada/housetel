"""Demo data of the guest portal (plan C5 › Seed).

- Portal settings for every demo property, with terms that name the hotel.
- About 40 % of the confirmed arrivals of the next three business days (today included) arrive with their
  online check-in completed, exactly as the real flow leaves it: TRA/SIRE data of every guest (companions
  are created and added as occupants through `bookings.add_occupant`), a private identity document per
  adult (`guests.add_document(uploaded_via="portal")`), the ETA on the reservation, a signature in private
  storage and the acceptance of the terms. Nothing is notified: it is history (no `guest_checked_in_online`).
- A few pending service requests (late check-out, early check-in, airport transfer) with their alerts, created
  through the portal service like a guest would.

Idempotent: once a property is seeded it records the audit event `guestportal.demo_seeded` and later runs
skip it (check-ins a demo user or a test made on their own never block the demo data, and never get
overwritten: those reservations are left out). Every random choice comes from a generator seeded with the
property slug, so a rerun on the same data makes the same choices.
"""

import io
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, ImageDraw

from apps.bookings.models import Reservation
from apps.bookings.services.reservations import add_occupant, update_reservation
from apps.core import audit
from apps.core.models import AuditEvent
from apps.guestportal.models import GuestPortalSettings, OnlineCheckin, ServiceRequest
from apps.guestportal.services.checkin import (
    guest_slots,
    guests_with_documents,
    identity_complete,
    is_adult,
)
from apps.guestportal.services.requests import create_request
from apps.guestportal.services.summary import balance_of
from apps.guests.models import Guest
from apps.guests.services import add_document, update_guest, upsert_guest
from apps.guests.types import GuestInput

SHARE = 0.4
DAYS_AHEAD = 3  # today and the next two business days

NAMES = {
    "es": [
        "Camila",
        "Santiago",
        "Valentina",
        "Mateo",
        "Isabella",
        "Sebastián",
        "Mariana",
        "Nicolás",
        "Daniela",
        "Tomás",
        "Lucía",
        "Andrés",
    ],
    "en": ["Emily", "Michael", "Olivia", "James", "Sophia", "Daniel", "Grace", "Ethan", "Chloe", "Ryan"],
    "fr": ["Camille", "Louis", "Chloé", "Hugo", "Léa", "Jules", "Manon"],
    "de": ["Lena", "Jonas", "Mia", "Lukas", "Hannah", "Felix", "Anna"],
    "pt": ["Beatriz", "João", "Larissa", "Gabriel", "Mariana", "Rafael", "Ana"],
}
LAST_NAMES = {
    "es": ["Restrepo", "Martínez", "Cárdenas", "Ospina", "Vargas", "Moreno", "Salazar", "Rincón"],
    "en": ["Walker", "Johnson", "Miller", "Brown", "Taylor", "Clark"],
    "fr": ["Martin", "Bernard", "Dubois", "Moreau", "Laurent"],
    "de": ["Müller", "Schmidt", "Fischer", "Weber", "Wagner"],
    "pt": ["Silva", "Santos", "Oliveira", "Souza", "Costa"],
}
LANGUAGE_OF = {
    "CO": "es",
    "ES": "es",
    "AR": "es",
    "MX": "es",
    "PE": "es",
    "CL": "es",
    "EC": "es",
    "VE": "es",
    "US": "en",
    "GB": "en",
    "CA": "en",
    "FR": "fr",
    "DE": "de",
    "BR": "pt",
}
CITIES = {
    "CO": ["Bogotá", "Medellín", "Cali", "Barranquilla", "Bucaramanga", "Pereira"],
    "US": ["Miami", "New York"],
    "ES": ["Madrid", "Barcelona"],
    "FR": ["Paris", "Lyon"],
    "DE": ["Berlin", "Munich"],
    "BR": ["São Paulo"],
    "AR": ["Buenos Aires"],
    "MX": ["Ciudad de México"],
    "CA": ["Toronto"],
    "GB": ["London"],
}
TRAVEL_REASONS = ["leisure"] * 6 + ["business"] * 2 + ["family"]
USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Mobile/15E148",
    "Mozilla/5.0 (Linux; Android 15; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0 "
    "Mobile Safari/537.36",
]
ETAS = [time(13, 0), time(14, 30), time(15, 0), time(16, 0), time(17, 30), time(19, 0), time(21, 30)]


SEED_MARKER = "guestportal.demo_seeded"


def seed(ctx) -> None:
    for key, prop in ctx.properties.items():
        settings = _ensure_settings(prop)
        if AuditEvent.objects.filter(property=prop, action=SEED_MARKER).exists():
            ctx.log(f"  {key}: el portal del huésped ya tiene sus datos de demostración")
            continue
        rng = random.Random(f"guestportal:{prop.slug}")
        arrivals = [reservation for reservation in _upcoming_arrivals(prop) if _completable(reservation)]
        chosen = sorted(rng.sample(arrivals, round(len(arrivals) * SHARE)), key=lambda r: r.code)
        for reservation in chosen:
            _complete_online_checkin(reservation, rng)
        requests = _pending_requests(prop, rng)
        audit.record(
            action=SEED_MARKER,
            target=settings,
            summary="Datos de demostración del portal del huésped",
            source="system",
            property=prop,
            changes={"online_checkins": len(chosen), "requests": len(requests)},
        )
        ctx.log(
            f"  {key}: {len(chosen)} check-ins en línea completados, {len(requests)} solicitudes pendientes"
        )


# --- settings -------------------------------------------------------------------------------------------


def _ensure_settings(prop) -> GuestPortalSettings:
    """Created once with terms that name the hotel; later changes of the demo user are kept."""
    settings, _ = GuestPortalSettings.objects.get_or_create(property=prop, defaults={"terms": _terms(prop)})
    return settings


def _terms(prop) -> dict:
    company = prop.legal_name or prop.name
    check_in = prop.check_in_time.strftime("%H:%M") if prop.check_in_time else "15:00"
    check_out = prop.check_out_time.strftime("%H:%M") if prop.check_out_time else "12:00"
    return {
        "es": (
            "Confirmo que los datos registrados son verdaderos y corresponden a los huéspedes de esta "
            f"reserva. Autorizo a {company} ({prop.name}) a tratar mis datos personales y los de mis "
            "acompañantes para el registro hotelero (Tarjeta de Registro Alojamiento), los reportes a "
            "Migración Colombia cuando apliquen y la prestación del servicio, conforme a la Ley 1581 de "
            f"2012. Acepto el reglamento de {prop.name}: check-in desde las {check_in} y check-out hasta las "
            f"{check_out}."
        ),
        "en": (
            "I confirm that the data provided is true and belongs to the guests of this booking. I authorize "
            f"{company} ({prop.name}) to process my personal data and that of my companions for the hotel "
            "registration (Tarjeta de Registro Alojamiento), the reports to Colombian Migration when they "
            "apply and the provision of the service, under Colombian Law 1581 of 2012. I accept the rules of "
            f"{prop.name}: check-in from {check_in} and check-out until {check_out}."
        ),
    }


# --- online check-ins -----------------------------------------------------------------------------------


def _upcoming_arrivals(prop) -> list[Reservation]:
    today = prop.business_date
    return list(
        Reservation.objects.filter(
            property=prop,
            status=Reservation.Status.CONFIRMED,
            checkin_date__gte=today,
            checkin_date__lt=today + timedelta(days=DAYS_AHEAD),
            online_checkin__isnull=True,  # one a guest already started is theirs
        )
        .select_related("property__organization", "booker")
        .order_by("checkin_date", "code")
    )


def _completable(reservation) -> bool:
    """The booker has the identity data the portal cannot invent (name, document, nationality, residence)."""
    booker = reservation.booker
    return (
        all(
            (
                booker.first_name,
                booker.last_name,
                booker.document_type,
                booker.document_number,
                booker.nationality,
                booker.country_of_residence,
            )
        )
        and booker.anonymized_at is None
    )


def _complete_online_checkin(reservation, rng: random.Random) -> OnlineCheckin:
    prop = reservation.property
    completed_at = timezone.now() - timedelta(hours=rng.randint(2, 60), minutes=rng.randint(0, 59))
    booker = reservation.booker
    booker_fill = {}
    if not booker.birth_date:
        booker_fill["birth_date"] = _birth_date(rng, reservation.checkin_date, 26, 64)
    if not booker.city_of_residence:
        booker_fill["city_of_residence"] = rng.choice(CITIES.get(booker.country_of_residence, ["—"]))
    if booker.data_processing_consent_at is None:
        booker_fill["data_processing_consent_at"] = completed_at
    if booker_fill:
        booker = update_guest(booker, booker_fill, source="guest")

    _register_companions(reservation, booker, rng)
    slots = guest_slots(reservation)
    guests = [slot.guest for slot in slots]
    trip = {
        "travel_reason": rng.choice(TRAVEL_REASONS),
        "origin": booker.city_of_residence or booker.country_of_residence,
        "destination": prop.city or prop.name,
    }
    with_documents = guests_with_documents(guest.pk for guest in guests)
    documents = []
    for guest in guests:
        if guest.pk in with_documents or not is_adult(guest, reservation.checkin_date):
            continue
        kind = "id_front" if guest.document_type in ("CC", "CE", "TI", "PPT", "PEP") else "passport"
        document = add_document(
            guest,
            kind=kind,
            file=ContentFile(_document_image(guest), name="documento.jpg"),
            uploaded_via="portal",
        )
        documents.append(
            {
                "guest_id": str(guest.pk),
                "document_id": str(document.pk),
                "kind": kind,
                "uploaded_at": completed_at.isoformat(),
            }
        )

    eta = rng.choice(ETAS)
    update_reservation(reservation, {"eta": eta}, source="guest")
    due = balance_of(reservation)["due"]
    checkin = OnlineCheckin(
        reservation=reservation,
        status=OnlineCheckin.Status.COMPLETED,
        current_step=OnlineCheckin.Step.PAYMENT if Decimal(due) > 0 else OnlineCheckin.Step.DONE,
        data={
            "travel": {str(guest.pk): dict(trip) for guest in guests},
            "documents": documents,
            "steps": ["arrival", "documents", "guests", "signature"],
        },
        accepted_terms_at=completed_at - timedelta(minutes=1),
        eta=eta,
        completed_at=completed_at,
        ip=f"181.{rng.randint(48, 63)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}",
        user_agent=rng.choice(USER_AGENTS),
    )
    checkin.signature.save("signature.png", ContentFile(_signature_image(rng)), save=False)
    checkin.save()
    return checkin


def _register_companions(reservation, booker, rng: random.Random) -> None:
    """Fill every empty guest slot with a companion of the booker's origin (adults first, then children)."""
    language = LANGUAGE_OF.get(booker.nationality, "en")
    slots = guest_slots(reservation)
    for slot in slots:
        if slot.guest is not None:
            if not identity_complete(slot.guest):  # a companion the hotel registered half-way
                update_guest(
                    slot.guest, _missing_identity(slot.guest, booker, reservation, rng), source="guest"
                )
            continue
        stay = slot.stay
        position = sum(1 for other in slots if other.stay.pk == stay.pk and other.index < slot.index)
        child = position >= stay.adults
        born = (
            _birth_date(rng, reservation.checkin_date, 4, 15)
            if child
            else _birth_date(rng, reservation.checkin_date, 20, 62)
        )
        colombian = booker.nationality == "CO"
        document_type = ("TI" if child else "CC") if colombian else "PA"
        guest = upsert_guest(
            reservation.property.organization,
            GuestInput(
                first_name=rng.choice(NAMES[language]),
                last_name=booker.last_name.split()[0]
                if child or rng.random() < 0.5
                else rng.choice(LAST_NAMES[language]),
                document_type=document_type,
                document_number=_unique_document(reservation.property.organization, colombian, rng),
                nationality=booker.nationality,
                country_of_residence=booker.country_of_residence,
                city_of_residence=booker.city_of_residence,
                birth_date=born,
                language=booker.language or reservation.language or "es",
            ),
        )
        add_occupant(stay, guest)


def _missing_identity(guest, booker, reservation, rng) -> dict:
    values = {
        "document_type": guest.document_type or ("CC" if booker.nationality == "CO" else "PA"),
        "document_number": guest.document_number
        or _unique_document(reservation.property.organization, booker.nationality == "CO", rng),
        "nationality": guest.nationality or booker.nationality,
        "country_of_residence": guest.country_of_residence or booker.country_of_residence,
        "birth_date": guest.birth_date or _birth_date(rng, reservation.checkin_date, 20, 62),
    }
    return {field: value for field, value in values.items() if value != getattr(guest, field)}


def _unique_document(organization, colombian: bool, rng: random.Random) -> str:
    while True:
        number = (
            str(rng.randint(1_000_000_000, 1_099_999_999))
            if colombian
            else f"S{rng.randint(10**7, 10**8 - 1)}"
        )
        if not Guest.objects.filter(organization=organization, document_number=number).exists():
            return number


def _birth_date(rng: random.Random, on: date, min_age: int, max_age: int) -> date:
    years = rng.randint(min_age, max_age)
    return date(on.year - years, rng.randint(1, 12), rng.randint(1, 28))


def _document_image(guest) -> bytes:
    """A labelled specimen card (never a real document) so the staff tab has something to show."""
    image = Image.new("RGB", (640, 400), (244, 238, 228))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((16, 16, 624, 384), radius=24, outline=(180, 88, 59), width=4)
    draw.rectangle((16, 16, 624, 86), fill=(180, 88, 59))
    draw.text((40, 38), "DOCUMENTO DE MUESTRA · DEMO", fill=(255, 255, 255))
    draw.rectangle((40, 120, 200, 320), fill=(214, 204, 190))
    draw.text((230, 140), guest.full_name.upper(), fill=(31, 28, 25))
    draw.text((230, 180), f"{guest.document_type} {guest.document_number}", fill=(31, 28, 25))
    draw.text((230, 220), guest.nationality, fill=(110, 103, 94))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=70)
    return buffer.getvalue()


def _signature_image(rng: random.Random) -> bytes:
    """A handwritten-looking stroke on a transparent canvas, like the one signature_pad sends."""
    image = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    x, y, points = 40, 120, []
    while x < 560:
        points.append((x, y))
        x += rng.randint(18, 42)
        y = max(40, min(170, y + rng.randint(-45, 45)))
    draw.line(points, fill=(28, 25, 22, 255), width=4, joint="curve")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# --- pending requests -----------------------------------------------------------------------------------


def _pending_requests(prop, rng: random.Random) -> list[ServiceRequest]:
    """A late check-out (first guest in the house to leave, or the next arrival), an early check-in of
    tomorrow and an airport transfer: what a front desk usually finds waiting in the morning."""
    today = prop.business_date
    base = Reservation.objects.filter(property=prop).select_related("property__organization", "booker")
    in_house = list(base.filter(status=Reservation.Status.CHECKED_IN).order_by("checkout_date", "code")[:1])
    upcoming = list(
        base.filter(
            status=Reservation.Status.CONFIRMED,
            checkin_date__gte=today,
            checkin_date__lt=today + timedelta(days=DAYS_AHEAD),
        ).order_by("checkin_date", "code")
    )
    used: set = set()
    created = []

    def pick(candidates):
        for reservation in candidates:
            if reservation.pk not in used:
                used.add(reservation.pk)
                return reservation
        return None

    late = pick(in_house + upcoming)
    if late is not None:
        created.append(
            create_request(
                late,
                kind="late_checkout",
                requested_time=time(14, 0),
                notes=rng.choice(["Nuestro vuelo sale a las 6 pm.", "Flight leaves at 7 pm, thanks!"]),
            )
        )
    early = pick([r for r in upcoming if r.checkin_date == today + timedelta(days=1)])
    if early is not None:
        created.append(
            create_request(
                early,
                kind="early_checkin",
                requested_time=time(11, 0),
                notes="Llegamos en el vuelo de la mañana.",
            )
        )
    transfer = pick(upcoming)
    if transfer is not None:
        arrival = datetime.combine(transfer.checkin_date, rng.choice(ETAS))
        created.append(
            create_request(
                transfer,
                kind="transfer",
                notes=f"Traslado desde el aeropuerto: vuelo AV{rng.randint(8000, 9899)}, llega a las "
                f"{arrival:%H:%M} del {arrival:%d/%m}. Somos {transfer.adults + transfer.children}.",
            )
        )
    return created
