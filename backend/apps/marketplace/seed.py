"""Demo seed of the marketplace (plan C4 › Seed): booking engine and marketplace listing of the three demo
hotels, each with its own brand color (also written to the hotel brand, so the guest portal and the payment
page match the engine). Idempotent: an existing row is left as the hotel edited it. Takes well under a second.
"""

from apps.inventory.models import Photo
from apps.marketplace.models import BookingEngineSettings, ListingContent, ListingPhoto
from apps.marketplace.services.configuration import update_engine

DEMO = {
    "aurora": {
        "primary_color": "#0E6E74",  # Caribbean teal: 6.0:1 with white text
        "headline": {
            "es": "Una casa colonial para despertar dentro de la muralla",
            "en": "A colonial house to wake up inside the city walls",
        },
        "terms": {
            "es": "Check-in desde las 15:00 y check-out hasta las 12:00. "
            "Menores de edad con adulto responsable. "
            "No se admiten mascotas.",
            "en": "Check-in from 3 pm, check-out until noon. Minors must travel with a responsible adult. "
            "No pets.",
        },
        "neighborhood": "Centro Histórico",
        "tagline": {
            "es": "Casa colonial restaurada con piscina en la terraza, a tres cuadras de la Torre del Reloj.",
            "en": "Restored colonial house with a rooftop pool, three blocks from the Clock Tower.",
        },
        "highlights": [
            {"es": "Piscina y bar en la terraza", "en": "Rooftop pool and bar"},
            {
                "es": "Desayuno caribeño incluido en la tarifa con desayuno",
                "en": "Caribbean breakfast on the breakfast rate",
            },
            {"es": "Traslado desde el aeropuerto Rafael Núñez", "en": "Transfer from Rafael Núñez airport"},
        ],
    },
    "andino_mde": {
        "primary_color": "#3D5A80",  # Andean blue: 7.1:1 with white text
        "headline": {
            "es": "Tu base en El Poblado para trabajar y descansar",
            "en": "Your base in El Poblado to work and unwind",
        },
        "terms": {
            "es": "Check-in desde las 15:00 y check-out hasta las 12:00. "
            "Parqueadero sujeto a disponibilidad.",
            "en": "Check-in from 3 pm, check-out until noon. Parking subject to availability.",
        },
        "neighborhood": "El Poblado",
        "tagline": {
            "es": "Hotel de negocios con cowork, gimnasio y restaurante a pasos del Parque Lleras.",
            "en": "Business hotel with coworking, gym and restaurant steps from Parque Lleras.",
        },
        "highlights": [
            {"es": "Cowork abierto 24 horas", "en": "24-hour coworking"},
            {"es": "Gimnasio y restaurante en el hotel", "en": "On-site gym and restaurant"},
            {"es": "Parqueadero cubierto", "en": "Covered parking"},
        ],
    },
    "andino_bog": {
        "primary_color": "#8A4F7D",  # Candelaria plum: 6.0:1 with white text
        "headline": {
            "es": "Camas y privadas en el corazón de La Candelaria",
            "en": "Beds and private rooms in the heart of La Candelaria",
        },
        "terms": {
            "es": "Dormitorios solo para mayores de 18 años. Lockers con candado propio. "
            "Horas de silencio desde las 22:00.",
            "en": "Dorms for guests aged 18 and over. Bring your own padlock for the lockers. "
            "Quiet hours from 10 pm.",
        },
        "neighborhood": "La Candelaria",
        "tagline": {
            "es": "Hostal con cocina compartida y terraza, a dos cuadras del Chorro de Quevedo.",
            "en": "Hostel with a shared kitchen and terrace, two blocks from the Chorro de Quevedo.",
        },
        "highlights": [
            {"es": "Cocina compartida equipada", "en": "Fully equipped shared kitchen"},
            {"es": "Dormitorio femenino con baño privado", "en": "Female dorm with private bathroom"},
            {"es": "Recorridos a pie por el centro histórico", "en": "Walking tours of the old town"},
        ],
    },
}
FEATURED_PHOTOS = 4


def seed(ctx) -> None:
    for key, content in DEMO.items():
        prop = ctx.properties.get(key)
        if prop is None:
            continue
        _engine(prop, content)
        _listing(prop, content)
        ctx.log(f"  marketplace: {prop.slug} ({content['primary_color']}, {content['neighborhood']})")


def _engine(prop, content) -> None:
    if BookingEngineSettings.objects.filter(property=prop).exists():
        return
    update_engine(
        prop,
        {
            "enabled": True,
            "primary_color": content["primary_color"],
            "headline": content["headline"],
            "terms": content["terms"],
            "show_promo_field": True,
        },
    )


def _listing(prop, content) -> None:
    listing, created = ListingContent.objects.get_or_create(
        property=prop,
        defaults={
            "neighborhood": content["neighborhood"],
            "tagline": content["tagline"],
            "highlights": content["highlights"],
        },
    )
    if not created:
        return
    gallery = list(Photo.objects.filter(property=prop, room_type__isnull=True, room__isnull=True)[:3])
    rooms = list(Photo.objects.filter(property=prop, room_type__isnull=False, room__isnull=True)[:1])
    photos = [*gallery, *rooms][:FEATURED_PHOTOS]
    ListingPhoto.objects.bulk_create(
        ListingPhoto(listing=listing, photo=photo, sort_order=index) for index, photo in enumerate(photos)
    )
    if not prop.marketplace_listed:
        prop.marketplace_listed = True
        prop.save(update_fields=["marketplace_listed", "updated_at"])
