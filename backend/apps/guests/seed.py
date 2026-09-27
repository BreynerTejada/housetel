"""Demo guests (spec §10, plan B3 seed). Runs after inventory/rates and before bookings (SEED_ORDER).

Per organization (guests are shared by the properties of a chain): ~180 guests — 65 % Colombian with CC and
real cities, 35 % foreign with passport and residence in their country (US, ES, FR, DE, BR, AR, MX, CA, GB)
—, 5 % VIP, tags ("frecuente", "corporativo", "luna de miel"), Habeas Data consents, a few preferences and
three intentional duplicates for the merge demo (same document, same email, same phone + similar surname).

Idempotent: guests are upserted by document with a local deterministic RNG (independent of what other
seeders consumed from `ctx.rng`), duplicates are created only if missing. Shares
`ctx.data["guests"] = {"aurora": [guest ids], "andino": [guest ids]}` for the bookings seeder.

SEED_ORDER has no `accounts` entry (fixed by core tests), so this seeder also adds the team demo data
(apps.accounts.seed).
"""

import random
import unicodedata
from datetime import UTC, date, datetime, time, timedelta

from apps.guests.models import Guest
from apps.guests.services import update_guest, upsert_guest
from apps.guests.types import GuestInput

GUESTS_PER_ORG = 180
COLOMBIAN_SHARE = 0.65
VIP_SHARE = 0.05
TAG_SHARES = {"frecuente": 0.12, "corporativo": 0.08, "luna de miel": 0.04}
EMAIL_DOMAINS = ("example.com", "example.org", "example.net")  # reserved (RFC 2606): never real inboxes

CO_FIRST_NAMES = [
    "Andrés", "Santiago", "Juan Pablo", "Camilo", "Sebastián", "Alejandro", "Felipe", "Julián", "Mateo",
    "Daniel", "Carlos", "Diego", "Nicolás", "Jorge", "Luis Fernando", "Valentina", "Camila", "Mariana",
    "Daniela", "Laura", "Natalia", "Paula", "Sofía", "Juliana", "Carolina", "Isabella", "Luisa Fernanda",
    "María José", "Ana María", "Catalina", "Manuela", "Gabriela",
]  # fmt: skip
CO_LAST_NAMES = [
    "García", "Rodríguez", "Martínez", "López", "González", "Hernández", "Pérez", "Sánchez", "Ramírez",
    "Torres", "Gómez", "Díaz", "Vargas", "Rojas", "Moreno", "Jiménez", "Restrepo", "Ospina", "Castaño",
    "Arango", "Zapata", "Cárdenas", "Mejía", "Ríos", "Castro", "Suárez", "Ortiz", "Quintero", "Salazar",
    "Echeverri", "Montoya", "Villegas",
]  # fmt: skip
CO_CITIES = [
    "Bogotá", "Medellín", "Cali", "Barranquilla", "Cartagena", "Bucaramanga", "Pereira", "Manizales",
    "Santa Marta", "Cúcuta", "Ibagué", "Villavicencio", "Pasto", "Montería", "Neiva", "Armenia", "Popayán",
    "Tunja", "Valledupar", "Sincelejo",
]  # fmt: skip
CO_MOBILE_PREFIXES = [
    "300",
    "301",
    "304",
    "310",
    "311",
    "312",
    "313",
    "314",
    "315",
    "316",
    "317",
    "318",
    "320",
]

FOREIGNERS = {
    "US": {
        "first": ["James", "Emily", "Michael", "Sarah", "David", "Jessica", "Ryan", "Ashley"],
        "last": ["Smith", "Johnson", "Miller", "Davis", "Wilson", "Anderson", "Taylor", "Brown"],
        "cities": ["New York", "Austin", "Miami", "Chicago", "San Francisco", "Denver"],
        "language": "en",
        "phone": lambda rng: f"+1 212 555 01{rng.randint(10, 99)}",
        "weight": 9,
    },
    "ES": {
        "first": ["Javier", "Lucía", "Pablo", "Marta", "Álvaro", "Elena", "Sergio", "Carmen"],
        "last": ["Fernández", "Ruiz", "Navarro", "Serrano", "Molina", "Blanco", "Iglesias", "Ortega"],
        "cities": ["Madrid", "Barcelona", "Valencia", "Sevilla", "Bilbao"],
        "language": "es",
        "phone": lambda rng: f"+34 6{rng.randint(10, 99)} {rng.randint(100, 999)} {rng.randint(100, 999)}",
        "weight": 6,
    },
    "FR": {
        "first": ["Julien", "Camille", "Thomas", "Léa", "Antoine", "Chloé", "Maxime", "Manon"],
        "last": ["Martin", "Bernard", "Dubois", "Durand", "Leroy", "Moreau", "Laurent", "Lefèvre"],
        "cities": ["Paris", "Lyon", "Marseille", "Bordeaux", "Toulouse"],
        "language": "en",
        "phone": lambda rng: (
            f"+33 6 {rng.randint(10, 99)} {rng.randint(10, 99)} {rng.randint(10, 99)} {rng.randint(10, 99)}"
        ),
        "weight": 4,
    },
    "DE": {
        "first": ["Lukas", "Anna", "Jonas", "Lena", "Felix", "Hannah", "Paul", "Laura"],
        "last": ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Wagner", "Becker", "Hoffmann"],
        "cities": ["Berlin", "München", "Hamburg", "Köln", "Frankfurt"],
        "language": "en",
        "phone": lambda rng: f"+49 151 {rng.randint(1000, 9999)} {rng.randint(1000, 9999)}",
        "weight": 4,
    },
    "BR": {
        "first": ["Gabriel", "Beatriz", "Lucas", "Mariana", "Rafael", "Juliana", "Pedro", "Larissa"],
        "last": ["Silva", "Santos", "Oliveira", "Souza", "Costa", "Pereira", "Almeida", "Carvalho"],
        "cities": ["São Paulo", "Rio de Janeiro", "Belo Horizonte", "Curitiba"],
        "language": "en",
        "phone": lambda rng: f"+55 11 9{rng.randint(1000, 9999)} {rng.randint(1000, 9999)}",
        "weight": 4,
    },
    "AR": {
        "first": ["Martín", "Florencia", "Facundo", "Agustina", "Tomás", "Micaela", "Joaquín", "Rocío"],
        "last": ["Fernández", "González", "Romero", "Álvarez", "Benítez", "Acosta", "Medina", "Herrera"],
        "cities": ["Buenos Aires", "Córdoba", "Rosario", "Mendoza"],
        "language": "es",
        "phone": lambda rng: f"+54 9 11 {rng.randint(1000, 9999)} {rng.randint(1000, 9999)}",
        "weight": 4,
    },
    "MX": {
        "first": ["Emiliano", "Regina", "Diego", "Ximena", "Santiago", "Fernanda", "Rodrigo", "Andrea"],
        "last": ["Hernández", "García", "Martínez", "López", "Flores", "Cruz", "Reyes", "Morales"],
        "cities": ["Ciudad de México", "Guadalajara", "Monterrey", "Puebla"],
        "language": "es",
        "phone": lambda rng: f"+52 55 {rng.randint(1000, 9999)} {rng.randint(1000, 9999)}",
        "weight": 5,
    },
    "CA": {
        "first": ["Liam", "Olivia", "Noah", "Emma", "Ethan", "Chloe", "Owen", "Grace"],
        "last": ["Tremblay", "Roy", "Campbell", "MacDonald", "Wong", "Thompson", "Young", "Clark"],
        "cities": ["Toronto", "Vancouver", "Montréal", "Calgary"],
        "language": "en",
        "phone": lambda rng: f"+1 416 555 01{rng.randint(10, 99)}",
        "weight": 4,
    },
    "GB": {
        "first": ["Oliver", "Amelia", "Harry", "Isla", "George", "Poppy", "Jack", "Freya"],
        "last": ["Jones", "Williams", "Evans", "Wright", "Walker", "Hughes", "Green", "Hall"],
        "cities": ["London", "Manchester", "Edinburgh", "Bristol"],
        "language": "en",
        "phone": lambda rng: f"+44 7700 900{rng.randint(100, 999)}",
        "weight": 4,
    },
}
PREFERENCES = [
    {"habitacion": "Piso alto, lejos del ascensor"},
    {"almohada": "Firme"},
    {"dieta": "Vegetariana"},
    {"cama": "King"},
    {"llegada": "Suele llegar después de las 22:00"},
    {"alergias": "Frutos secos"},
]


def _ascii(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))


def _email(rng, first: str, last: str, n: int) -> str:
    local = _ascii(f"{first.split()[0]}.{last.split()[0]}").lower().replace("'", "")
    return f"{local}{n}@{rng.choice(EMAIL_DOMAINS)}"


def _birth_date(rng) -> date:
    return date(1955, 1, 1) + timedelta(days=rng.randint(0, 49 * 365))


def _consent_time(rng, today: date) -> datetime:
    day = today - timedelta(days=rng.randint(1, 700))
    return datetime.combine(day, time(rng.randint(8, 21), rng.randint(0, 59)), tzinfo=UTC)


def _colombian(rng, n: int) -> GuestInput:
    first, last = rng.choice(CO_FIRST_NAMES), f"{rng.choice(CO_LAST_NAMES)} {rng.choice(CO_LAST_NAMES)}"
    number = str(
        rng.randint(1_000_000_000, 1_099_999_999)
        if rng.random() < 0.6
        else rng.randint(10_000_000, 99_999_999)
    )
    return GuestInput(
        first_name=first,
        last_name=last,
        email=_email(rng, first, last, n),
        phone=f"+57 {rng.choice(CO_MOBILE_PREFIXES)} {rng.randint(100, 999)} {rng.randint(1000, 9999)}",
        document_type="CC",
        document_number=number,
        nationality="CO",
        country_of_residence="CO",
        city_of_residence=rng.choice(CO_CITIES),
        birth_date=_birth_date(rng),
        language="es",
    )


def _foreigner(rng, n: int) -> GuestInput:
    countries = list(FOREIGNERS)
    country = rng.choices(countries, weights=[FOREIGNERS[c]["weight"] for c in countries])[0]
    spec = FOREIGNERS[country]
    first, last = rng.choice(spec["first"]), rng.choice(spec["last"])
    letters = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(2))
    return GuestInput(
        first_name=first,
        last_name=last,
        email=_email(rng, first, last, n),
        phone=spec["phone"](rng),
        document_type="PA",
        document_number=f"{country}{letters}{rng.randint(1_000_000, 9_999_999)}",
        nationality=country,
        country_of_residence=country,
        city_of_residence=rng.choice(spec["cities"]),
        birth_date=_birth_date(rng),
        language=spec["language"],
    )


def _extras(rng, today: date) -> dict:
    """Profile fields upsert_guest does not take (VIP, tags, preferences, consents)."""
    extras = {}
    if rng.random() < VIP_SHARE:
        extras["is_vip"] = True
        extras["notes"] = "Cliente VIP: ofrecer upgrade si hay disponibilidad y bienvenida en la habitación."
    tags = [tag for tag, share in TAG_SHARES.items() if rng.random() < share]
    if tags:
        extras["tags"] = tags
    if rng.random() < 0.15:
        extras["preferences"] = dict(rng.choice(PREFERENCES))
    if rng.random() < 0.92:
        extras["data_processing_consent_at"] = _consent_time(rng, today)
    if rng.random() < 0.45:
        extras["marketing_consent"] = True
    return extras


def _seed_organization(ctx, key: str, organization) -> list:
    rng = random.Random(f"housetel-guests-{key}")
    ids = []
    for n in range(1, GUESTS_PER_ORG + 1):
        data = _colombian(rng, n) if rng.random() < COLOMBIAN_SHARE else _foreigner(rng, n)
        extras = _extras(rng, ctx.today)
        guest = upsert_guest(organization, data)
        changes = {
            field: value
            for field, value in extras.items()
            if getattr(guest, field) in (None, "", [], {}, False)
        }
        if changes:
            update_guest(guest, changes, source="system")
        ids.append(guest.pk)
    _seed_duplicates(organization, ids)
    return list(
        Guest.objects.filter(organization=organization, merged_into__isnull=True).values_list("pk", flat=True)
    )


def _seed_duplicates(organization, ids: list) -> None:
    """Three records a receptionist could have typed twice (created as legacy data, bypassing upsert)."""
    guests = list(Guest.objects.filter(pk__in=ids[:12]).order_by("created_at"))
    colombians = [g for g in guests if g.nationality == "CO"]
    foreigners = [
        g for g in Guest.objects.filter(pk__in=ids).exclude(nationality="CO").order_by("created_at")[:1]
    ]
    pairs = []
    if colombians:  # same document number, typed without type, accents or second names
        base = colombians[0]
        pairs.append((base, {
            "first_name": _ascii(base.first_name.split()[0]), "last_name": _ascii(base.last_name.split()[0]),
            "document_type": "", "document_number": base.document_number, "nationality": "CO",
            "country_of_residence": "CO",
        }))  # fmt: skip
    if len(colombians) > 1:  # same phone, similar surname, no document, another email
        base = colombians[1]
        pairs.append((base, {
            "first_name": base.first_name.split()[0], "last_name": base.last_name.split()[0],
            "phone": base.phone, "email": f"otro.{base.email}", "nationality": "CO",
            "country_of_residence": "CO",
        }))  # fmt: skip
    if foreigners:  # same email, no passport
        base = foreigners[0]
        pairs.append((base, {
            "first_name": base.first_name, "last_name": base.last_name, "email": base.email.upper(),
            "nationality": base.nationality, "country_of_residence": base.country_of_residence,
            "language": base.language,
        }))  # fmt: skip
    for base, values in pairs:
        lookup = {
            k: values[k]
            for k in ("first_name", "last_name", "document_number", "phone", "email")
            if k in values
        }
        if not Guest.objects.filter(organization=organization, **lookup).exclude(pk=base.pk).exists():
            Guest.objects.create(organization=organization, **values)


def seed(ctx) -> None:
    ctx.data.setdefault("guests", {})
    for key, organization in ctx.orgs.items():
        existing = Guest.objects.filter(organization=organization, merged_into__isnull=True)
        if existing.count() >= GUESTS_PER_ORG:
            ctx.log(f"  huéspedes de {organization.name}: ya existen ({existing.count()})")
            ctx.data["guests"][key] = list(existing.values_list("pk", flat=True))
            continue
        ctx.data["guests"][key] = _seed_organization(ctx, key, organization)
        ctx.log(f"  huéspedes de {organization.name}: {len(ctx.data['guests'][key])}")

    from apps.accounts.seed import seed as seed_team

    seed_team(ctx)
