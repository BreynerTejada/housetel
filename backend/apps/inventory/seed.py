"""Inventory demo data (spec §10, plan B1). Idempotent: existing categories, rooms, fields and photos are left
as they are (a demo user's changes survive re-seeding).

- Global amenity catalog (ES/EN, lucide icon names in kebab-case).
- Per organization: custom fields "minibar" (room, boolean) and "orientation" (room_type, select).
- Categories, rooms and dorm beds of the three demo properties, created with `provision_room_type`; a few
  overrides on rooms of newly created categories (306 panoramic suite, accessible 101, …).
- Profile extras (languages, policies, property amenities) when missing.
- Photos: https://picsum.photos/seed/<slug>-<n>/1200/800 (5 s timeout, downloaded in parallel; if the first
  one fails nothing else is tried), otherwise deterministic warm gradients drawn with Pillow.

`ctx.data["inventory"]["room_types"][<property key>][<code>]` exposes the RoomType objects to later seeders.
"""

import io
import os
import zlib
from concurrent.futures import ThreadPoolExecutor

from django.core.files.base import ContentFile

from apps.inventory.models import Amenity, CustomFieldDefinition, Photo, Room, RoomType
from apps.inventory.serializers import clean_overrides, resolve_amenities, room_occupancy_errors
from apps.inventory.services import provision_room_type

PHOTOS_PER_ROOM_TYPE = 3
PHOTOS_PER_PROPERTY = 4
PHOTO_SIZE = (1200, 800)
PICSUM = "https://picsum.photos/seed/{slug}/1200/800"

# (code, name es, name en, lucide icon, category)
AMENITIES = [
    ("wifi", "Wifi", "Wi-Fi", "wifi", "room"),
    ("air_conditioning", "Aire acondicionado", "Air conditioning", "air-vent", "room"),
    ("fan", "Ventilador", "Fan", "fan", "room"),
    ("heating", "Calefacción", "Heating", "heater", "room"),
    ("tv", "Televisor", "TV", "tv", "room"),
    ("smart_tv", "Smart TV con streaming", "Smart TV with streaming", "monitor-play", "room"),
    ("minibar", "Minibar", "Minibar", "refrigerator", "room"),
    ("safe", "Caja fuerte", "In-room safe", "vault", "room"),
    ("desk", "Escritorio", "Work desk", "lamp-desk", "room"),
    ("coffee_maker", "Cafetera", "Coffee maker", "coffee", "room"),
    ("balcony", "Balcón", "Balcony", "fence", "room"),
    ("blackout_curtains", "Cortinas blackout", "Blackout curtains", "moon", "room"),
    ("soundproofing", "Insonorizada", "Soundproofed", "volume-x", "room"),
    ("iron", "Plancha", "Iron", "shirt", "room"),
    ("sofa", "Sofá", "Sofa", "sofa", "room"),
    ("lockers", "Lockers individuales", "Personal lockers", "lock", "room"),
    ("reading_light", "Luz de lectura", "Reading light", "lamp", "room"),
    ("bedside_outlet", "Enchufe junto a la cama", "Bedside power outlet", "plug", "room"),
    ("private_bathroom", "Baño privado", "Private bathroom", "bath", "bathroom"),
    ("shared_bathroom", "Baño compartido", "Shared bathroom", "users", "bathroom"),
    ("bathtub", "Bañera", "Bathtub", "bath", "bathroom"),
    ("rain_shower", "Ducha tipo lluvia", "Rain shower", "shower-head", "bathroom"),
    ("hairdryer", "Secador de pelo", "Hair dryer", "wind", "bathroom"),
    ("toiletries", "Artículos de aseo", "Toiletries", "soap-dispenser-droplet", "bathroom"),
    ("towels", "Toallas", "Towels", "towel-rack", "bathroom"),
    ("pool", "Piscina", "Swimming pool", "waves-ladder", "property"),
    ("parking", "Parqueadero", "Parking", "square-parking", "property"),
    ("restaurant", "Restaurante", "Restaurant", "utensils", "property"),
    ("bar", "Bar", "Bar", "wine", "property"),
    ("breakfast", "Desayuno disponible", "Breakfast available", "croissant", "property"),
    ("gym", "Gimnasio", "Gym", "dumbbell", "property"),
    ("spa", "Spa", "Spa", "flower-2", "property"),
    ("reception_24h", "Recepción 24 horas", "24-hour front desk", "concierge-bell", "property"),
    ("airport_shuttle", "Traslado al aeropuerto", "Airport shuttle", "bus", "property"),
    ("laundry", "Lavandería", "Laundry", "washing-machine", "property"),
    ("shared_kitchen", "Cocina compartida", "Shared kitchen", "cooking-pot", "property"),
    ("terrace", "Terraza", "Terrace", "sun", "property"),
    ("coworking", "Coworking", "Coworking", "laptop", "property"),
    ("luggage_storage", "Guardaequipaje", "Luggage storage", "luggage", "property"),
    ("elevator", "Ascensor", "Elevator", "arrow-up-down", "accessibility"),
    ("wheelchair_accessible", "Accesible en silla de ruedas", "Wheelchair accessible", "accessibility",
     "accessibility"),
    ("grab_bars", "Barras de apoyo", "Grab bars", "grip-horizontal", "accessibility"),
    ("roll_in_shower", "Ducha sin escalón", "Roll-in shower", "shower-head", "accessibility"),
    ("sea_view", "Vista al mar", "Sea view", "waves-horizontal", "view"),
    ("city_view", "Vista a la ciudad", "City view", "building", "view"),
    ("garden_view", "Vista al jardín", "Garden view", "trees", "view"),
    ("mountain_view", "Vista a la montaña", "Mountain view", "mountain", "view"),
]  # fmt: skip

CUSTOM_FIELDS = [
    {
        "applies_to": "room",
        "key": "minibar",
        "label": {"es": "Minibar surtido", "en": "Stocked minibar"},
        "field_type": "boolean",
        "default_value": False,
        "sort_order": 10,
    },
    {
        "applies_to": "room_type",
        "key": "orientation",
        "label": {"es": "Orientación", "en": "Orientation"},
        "field_type": "select",
        "options": [
            {"value": "sea", "label": {"es": "Mar", "en": "Sea"}},
            {"value": "city", "label": {"es": "Ciudad", "en": "City"}},
            {"value": "garden", "label": {"es": "Jardín", "en": "Garden"}},
        ],
        "show_in_marketplace": True,
        "sort_order": 20,
    },
]

ROOM_BASICS = ["wifi", "private_bathroom", "toiletries", "towels", "hairdryer"]
DORM_BASICS = ["wifi", "lockers", "reading_light", "bedside_outlet", "towels"]


def _room_type(code, es, en, description, *, rooms, beds_per_room=None, **data):
    data.update({"code": code, "name": {"es": es, "en": en}, "description": description})
    return {"data": data, "rooms": rooms, "beds_per_room": beds_per_room}


CATALOG = {
    "aurora": [
        _room_type(
            "DBL", "Estándar", "Standard",
            {"es": "Habitación colonial con cama queen, techos altos y vista a las calles del centro.",
             "en": "Colonial room with a queen bed, high ceilings and views of the historic center streets."},
            rooms="101-110", base_occupancy=2, max_adults=2, max_children=1, max_occupancy=3,
            beds=[{"type": "queen", "count": 1}], size_m2="22", view="city", color="#4E6C88",
            housekeeping_minutes=30, custom_values={"orientation": "city"},
            amenities=[*ROOM_BASICS, "air_conditioning", "smart_tv", "safe", "desk", "rain_shower",
                       "blackout_curtains"],
        ),
        _room_type(
            "SUP", "Superior", "Superior",
            {"es": "Más amplia, con cama king y balcón de madera sobre la calle empedrada.",
             "en": "More spacious, with a king bed and a wooden balcony over the cobblestone street."},
            rooms="201-208", base_occupancy=2, max_adults=2, max_children=1, max_occupancy=3,
            beds=[{"type": "king", "count": 1}], size_m2="28", view="city", color="#5F7F66",
            housekeeping_minutes=35, custom_values={"orientation": "city"},
            amenities=[*ROOM_BASICS, "air_conditioning", "smart_tv", "safe", "desk", "rain_shower", "balcony",
                       "coffee_maker", "minibar"],
        ),
        _room_type(
            "STE", "Suite Vista al Mar", "Sea View Suite",
            {"es": "Suite en el último piso con bañera, sala y vista abierta al mar Caribe.",
             "en": "Top-floor suite with a bathtub, a lounge and open views of the Caribbean Sea."},
            rooms="301-306", base_occupancy=2, max_adults=3, max_children=2, max_occupancy=4,
            beds=[{"type": "king", "count": 1}, {"type": "sofa_bed", "count": 1}], size_m2="42", view="sea",
            color="#B4583B", housekeeping_minutes=50, custom_values={"orientation": "sea"},
            amenities=[*ROOM_BASICS, "air_conditioning", "smart_tv", "safe", "bathtub", "rain_shower",
                       "balcony", "coffee_maker", "minibar", "sofa", "sea_view"],
        ),
    ],
    "andino_mde": [
        _room_type(
            "STD", "Estándar", "Standard",
            {"es": "Habitación práctica y silenciosa en El Poblado, ideal para viajes de trabajo.",
             "en": "A practical, quiet room in El Poblado, ideal for business trips."},
            rooms="201-210,301-310", base_occupancy=2, max_adults=2, max_children=1, max_occupancy=3,
            beds=[{"type": "queen", "count": 1}], size_m2="20", view="city", color="#4E6C88",
            housekeeping_minutes=30, custom_values={"orientation": "city"},
            amenities=[*ROOM_BASICS, "air_conditioning", "tv", "desk", "safe"],
        ),
        _room_type(
            "EJE", "Ejecutiva", "Executive",
            {"es": "Cama king, escritorio amplio, cafetera y ventanas insonorizadas con vista al valle.",
             "en": "King bed, a large desk, a coffee maker and soundproofed windows over the valley."},
            rooms="401-407,501-507", base_occupancy=2, max_adults=2, max_children=1, max_occupancy=3,
            beds=[{"type": "king", "count": 1}], size_m2="26", view="city", color="#B98A2E",
            housekeeping_minutes=35, custom_values={"orientation": "city"},
            amenities=[*ROOM_BASICS, "air_conditioning", "smart_tv", "desk", "safe", "coffee_maker",
                       "soundproofing", "blackout_curtains", "minibar"],
        ),
        _room_type(
            "FAM", "Familiar", "Family",
            {"es": "Cama queen y dos sencillas: espacio para una familia de cinco con vista a las montañas.",
             "en": "A queen bed and two twin beds, room for a family of five with mountain views."},
            rooms="601-606", base_occupancy=3, max_adults=4, max_children=3, max_occupancy=5,
            beds=[{"type": "queen", "count": 1}, {"type": "twin", "count": 2}], size_m2="34", view="mountain",
            color="#5F7F66", housekeeping_minutes=45, custom_values={"orientation": "garden"},
            amenities=[*ROOM_BASICS, "air_conditioning", "smart_tv", "safe", "bathtub", "mountain_view"],
        ),
    ],
    "andino_bog": [
        _room_type(
            "D6", "Dormitorio mixto 6 camas", "6-bed mixed dorm",
            {"es": "Camarotes con cortina, luz de lectura y enchufe propio; baños compartidos en el piso.",
             "en": "Bunks with curtains, a reading light and your own outlet; shared bathrooms nearby."},
            rooms="D1-D2", beds_per_room=6, kind="dorm", beds=[{"type": "bunk", "count": 3}], size_m2="24",
            view="city", color="#B98A2E", housekeeping_minutes=40, custom_values={"orientation": "city"},
            amenities=[*DORM_BASICS, "shared_bathroom", "fan"],
        ),
        _room_type(
            "D8", "Dormitorio mixto 8 camas", "8-bed mixed dorm",
            {"es": "El dormitorio más económico: ocho camas en camarotes y lockers grandes.",
             "en": "Our best-value dorm: eight beds in bunks and large lockers."},
            rooms="D3-D4", beds_per_room=8, kind="dorm", beds=[{"type": "bunk", "count": 4}], size_m2="30",
            view="city", color="#4E6C88", housekeeping_minutes=45, custom_values={"orientation": "city"},
            amenities=[*DORM_BASICS, "shared_bathroom", "fan"],
        ),
        _room_type(
            "DF6", "Dormitorio femenino 6 camas", "6-bed female dorm",
            {"es": "Solo para mujeres, con baño privado dentro del dormitorio y secador de pelo.",
             "en": "Women only, with an en-suite bathroom and a hair dryer."},
            rooms="D5", beds_per_room=6, kind="dorm", beds=[{"type": "bunk", "count": 3}], size_m2="26",
            view="garden", color="#B4583B", housekeeping_minutes=40, custom_values={"orientation": "garden"},
            amenities=[*DORM_BASICS, "private_bathroom", "hairdryer"],
        ),
        _room_type(
            "PDB", "Privada doble", "Private double",
            {"es": "Habitación privada con cama doble y baño propio, a un paso de la vida del hostal.",
             "en": "A private room with a double bed and en-suite bathroom, a step from hostel life."},
            rooms="101-106", base_occupancy=2, max_adults=2, max_children=0, max_occupancy=2,
            beds=[{"type": "double", "count": 1}], size_m2="14", view="city", color="#5F7F66",
            housekeeping_minutes=25, custom_values={"orientation": "city"},
            amenities=[*ROOM_BASICS, "fan"],
        ),
        _room_type(
            "PFM", "Privada familiar", "Family private",
            {"es": "Cama doble y un camarote: perfecta para familias o grupos de amigos.",
             "en": "A double bed and a bunk: perfect for families or groups of friends."},
            rooms="201-202", base_occupancy=3, max_adults=3, max_children=2, max_occupancy=4,
            beds=[{"type": "double", "count": 1}, {"type": "bunk", "count": 1}], size_m2="20", view="city",
            color="#4E6C88", housekeeping_minutes=30, custom_values={"orientation": "city"},
            amenities=[*ROOM_BASICS, "fan", "lockers"],
        ),
    ],
}  # fmt: skip

# Applied only to rooms of categories created in the same run (never over a demo user's edits).
OVERRIDES = {
    "aurora": {
        "306": {
            "overrides": {"name": {"es": "Suite Panorámica", "en": "Panoramic Suite"}, "view": "panoramic",
                          "size_m2": "48.00"},
            "custom_values": {"minibar": True},
        },
        "301": {"custom_values": {"minibar": True}},
        "302": {"custom_values": {"minibar": True}},
        "303": {"custom_values": {"minibar": True}},
        "304": {"custom_values": {"minibar": True}},
        "305": {"custom_values": {"minibar": True}},
        "101": {"overrides": {"accessible": True},
                "extra_amenities": ["wheelchair_accessible", "grab_bars", "roll_in_shower"]},
        "208": {"extra_amenities": ["bathtub"], "custom_values": {"minibar": True}},
    },
    "andino_mde": {
        "606": {"overrides": {"max_occupancy": 6, "max_children": 4,
                              "beds": [{"type": "queen", "count": 1}, {"type": "bunk", "count": 1},
                                       {"type": "twin", "count": 1}]}},
        "507": {"overrides": {"view": "mountain"}, "extra_amenities": ["balcony"]},
    },
    "andino_bog": {
        "106": {"overrides": {"view": "mountain"}, "notes": "Ventana hacia Monserrate"},
    },
}  # fmt: skip

PROFILE_EXTRAS = {
    "aurora": {
        "languages": ["es", "en"],
        "policies": {"pets_allowed": False, "smoking_allowed": False, "children_allowed": True,
                     "events_allowed": True, "min_checkin_age": 18},
        "amenities": ["wifi", "pool", "restaurant", "bar", "breakfast", "reception_24h", "terrace",
                      "airport_shuttle", "laundry"],
    },
    "andino_mde": {
        "languages": ["es", "en"],
        "policies": {"pets_allowed": True, "smoking_allowed": False, "children_allowed": True,
                     "events_allowed": True, "min_checkin_age": 18},
        "amenities": ["wifi", "restaurant", "gym", "coworking", "parking", "breakfast", "reception_24h",
                      "elevator", "laundry"],
    },
    "andino_bog": {
        "languages": ["es", "en", "fr"],
        "policies": {"pets_allowed": False, "smoking_allowed": False, "children_allowed": True,
                     "events_allowed": False, "min_checkin_age": 18},
        "amenities": ["wifi", "shared_kitchen", "terrace", "bar", "reception_24h", "laundry",
                      "luggage_storage"],
    },
}  # fmt: skip

ROOM_TYPE_CAPTIONS = [("Vista general", "Overview"), ("La cama", "The bed"), ("El baño", "The bathroom")]
PROPERTY_CAPTIONS = [
    ("Fachada", "Facade"),
    ("Recepción", "Front desk"),
    ("Zonas comunes", "Common areas"),
    ("Terraza", "Terrace"),
]

# (dark, light) pairs of the "warm Nordic" palette: terracotta, sage, slate, sand
PALETTE = [
    ((180, 88, 59), (245, 231, 224)),
    ((95, 127, 102), (232, 239, 232)),
    ((78, 108, 136), (229, 236, 243)),
    ((185, 138, 46), (248, 239, 218)),
]


def seed(ctx) -> None:
    seed_amenities()
    registry = ctx.data.setdefault("inventory", {}).setdefault("room_types", {})
    pending_photos = []
    for key, catalog in CATALOG.items():
        prop = ctx.properties.get(key)
        if prop is None:
            continue
        seed_custom_fields(prop.organization)
        created = set()
        registry[key] = {}
        for spec in catalog:
            room_type, is_new = seed_room_type(prop, spec)
            registry[key][room_type.code] = room_type
            if is_new:
                created.add(room_type.code)
        apply_overrides(prop, OVERRIDES.get(key, {}), created)
        seed_profile_extras(prop, PROFILE_EXTRAS.get(key, {}))
        pending_photos += photo_plan(prop)
    save_photos(pending_photos)
    ctx.log(f"   inventario: {RoomType.objects.count()} categorías, {Room.objects.count()} habitaciones")


def seed_amenities() -> None:
    for code, es, en, icon, category in AMENITIES:
        Amenity.objects.update_or_create(
            organization=None,
            code=code,
            defaults={"name": {"es": es, "en": en}, "icon": icon, "category": category},
        )


def seed_custom_fields(organization) -> None:
    for definition in CUSTOM_FIELDS:
        values = dict(definition)
        CustomFieldDefinition.objects.get_or_create(
            organization=organization,
            property=None,
            applies_to=values.pop("applies_to"),
            key=values.pop("key"),
            defaults=values,
        )


def seed_room_type(prop, spec) -> tuple[RoomType, bool]:
    existing = RoomType.objects.filter(property=prop, code=spec["data"]["code"]).first()
    if existing is not None:
        return existing, False
    room_type = provision_room_type(
        prop, data=spec["data"], room_numbers=[spec["rooms"]], beds_per_room=spec.get("beds_per_room")
    )
    return room_type, True


def apply_overrides(prop, overrides: dict, created_codes: set) -> None:
    context = {"property": prop}
    rooms = Room.objects.filter(property=prop, number__in=list(overrides), room_type__code__in=created_codes)
    for room in rooms.select_related("room_type"):
        spec = overrides[room.number]
        room.overrides = clean_overrides(spec.get("overrides", {}), context=context)
        errors = room_occupancy_errors(room.room_type, room.overrides)
        if errors:
            raise ValueError(f"Override inválido en {room.number}: {errors}")
        room.custom_values = {**(room.custom_values or {}), **spec.get("custom_values", {})}
        room.notes = spec.get("notes", room.notes)
        room.save()
        if spec.get("extra_amenities"):
            room.extra_amenities.set(resolve_amenities(prop.organization, spec["extra_amenities"]))


def seed_profile_extras(prop, extras: dict) -> None:
    settings = dict(prop.settings or {})
    missing = {key: value for key, value in extras.items() if key not in settings}
    if missing:
        prop.settings = {**settings, **missing}
        prop.save(update_fields=["settings", "updated_at"])


# ---- Photos --------------------------------------------------------------------------------------------


def photo_plan(prop) -> list[dict]:
    """Photos still missing: each category without photos and the property gallery if empty."""
    plan = []
    for room_type in RoomType.objects.filter(property=prop, photos__isnull=True).distinct():
        slug = f"{prop.slug}-{room_type.code.lower()}"
        for index, (es, en) in enumerate(ROOM_TYPE_CAPTIONS[:PHOTOS_PER_ROOM_TYPE], start=1):
            plan.append({
                "property": prop, "room_type": room_type, "slug": f"{slug}-{index}", "sort_order": index,
                "caption": {"es": f"{room_type.name.get('es')} · {es}",
                            "en": f"{room_type.name.get('en')} · {en}"},
                "title": room_type.name.get("es") or room_type.code, "subtitle": prop.name,
            })  # fmt: skip
    if not Photo.objects.filter(property=prop, room_type__isnull=True, room__isnull=True).exists():
        for index, (es, en) in enumerate(PROPERTY_CAPTIONS[:PHOTOS_PER_PROPERTY], start=1):
            plan.append({
                "property": prop, "room_type": None, "slug": f"{prop.slug}-{index}", "sort_order": index,
                "caption": {"es": es, "en": en}, "title": prop.name, "subtitle": es,
            })  # fmt: skip
    return plan


def save_photos(plan: list[dict]) -> None:
    """Demo photos live in `photos/seed/<slug>.jpg` (stored directly, not under the dated `upload_to`)."""
    storage = Photo._meta.get_field("image").storage
    downloaded = download_photos([PICSUM.format(slug=item["slug"]) for item in plan])
    for item in plan:
        content = downloaded.get(PICSUM.format(slug=item["slug"])) or generated_photo(
            item["title"], item["subtitle"], item["slug"]
        )
        name = storage.save(f"photos/seed/{item['slug']}.jpg", ContentFile(content))
        Photo.objects.create(
            property=item["property"],
            room_type=item["room_type"],
            caption=item["caption"],
            sort_order=item["sort_order"],
            image=name,
        )


def download_photos(urls: list[str]) -> dict[str, bytes]:
    """{url: jpeg bytes} of the photos that downloaded (5 s timeout each, 8 in parallel). Offline (the first
    download fails or SEED_OFFLINE=1) → {} right away instead of waiting on every timeout."""
    if not urls or os.environ.get("SEED_OFFLINE"):
        return {}
    import logging

    import httpx

    logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per request is noise in a seed
    with httpx.Client(timeout=5, follow_redirects=True) as client:
        first = _fetch(client, urls[0])
        if first is None:
            return {}
        results = {urls[0]: first}
        with ThreadPoolExecutor(max_workers=8) as pool:
            for url, content in zip(
                urls[1:], pool.map(lambda url: _fetch(client, url), urls[1:]), strict=True
            ):
                if content:
                    results[url] = content
    return results


def _fetch(client, url: str) -> bytes | None:
    import httpx
    from PIL import Image

    try:
        response = client.get(url)
    except (httpx.HTTPError, OSError):
        return None
    if response.status_code != 200 or not response.headers.get("content-type", "").startswith("image/"):
        return None
    try:
        Image.open(io.BytesIO(response.content)).verify()
    except Exception:  # noqa: BLE001 — any undecodable payload is just "no photo"
        return None
    return response.content


def generated_photo(title: str, subtitle: str, seed_key: str) -> bytes:
    """A deterministic 1200×800 JPEG: a warm diagonal gradient with the name, for offline demos."""
    from PIL import Image, ImageDraw, ImageFont

    dark, light = PALETTE[zlib.crc32(seed_key.encode()) % len(PALETTE)]
    mask = Image.linear_gradient("L").rotate(45, expand=True).resize(PHOTO_SIZE)
    image = Image.composite(Image.new("RGB", PHOTO_SIZE, light), Image.new("RGB", PHOTO_SIZE, dark), mask)
    draw = ImageDraw.Draw(image)
    # a thin "key tag" frame, the product's visual motif
    draw.rounded_rectangle(
        (60, 60, PHOTO_SIZE[0] - 60, PHOTO_SIZE[1] - 60), radius=28, outline=light, width=3
    )
    draw.ellipse((96, 96, 132, 132), outline=light, width=3)
    title_font = ImageFont.load_default(size=64)
    subtitle_font = ImageFont.load_default(size=30)
    draw.text((100, PHOTO_SIZE[1] - 230), title, font=title_font, fill=(255, 255, 255))
    draw.text((104, PHOTO_SIZE[1] - 140), subtitle, font=subtitle_font, fill=light)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()
