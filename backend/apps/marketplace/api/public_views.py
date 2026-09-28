"""Public marketplace and booking engine API (`/api/v1/public/marketplace/`, no session).

Throttles are per IP and defined on the classes (shared settings stay untouched).
"""

import time

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.core.errors import NotFoundError
from apps.marketplace.api import serializers as s
from apps.marketplace.services import catalog, checkout, engine, lookup
from apps.marketplace.services.offers import offers_response, sellable_offers
from apps.marketplace.services.search import SORTS, SearchQuery, search

VIA = OpenApiParameter(
    "via",
    OpenApiTypes.STR,
    enum=list(engine.CHANNELS),
    description="marketplace (por defecto) o booking_engine",
)
STAY_PARAMS = [
    OpenApiParameter("checkin", OpenApiTypes.DATE),
    OpenApiParameter("checkout", OpenApiTypes.DATE, description="Exclusiva"),
    OpenApiParameter("adults", OpenApiTypes.INT),
    OpenApiParameter("children", OpenApiTypes.INT),
    OpenApiParameter("children_ages", OpenApiTypes.STR, description="Edades separadas por coma: 4,7"),
]


class IpThrottle(AnonRateThrottle):
    def timer(self):
        # Read the clock at call time. DRF stores `time.time` as a class attribute when its module is
        # imported; if that import happens under a patched clock (freezegun in tests) the attribute becomes a
        # plain function and binds as a method.
        return time.time()


class PublicReadThrottle(IpThrottle):
    scope = "marketplace_public_read"
    rate = "240/min"


class QuoteThrottle(IpThrottle):
    scope = "marketplace_quote"
    rate = "120/min"


class BookingThrottle(IpThrottle):
    # Generous on purpose: behind a proxy that does not forward the client IP (the Vite dev proxy, some hotel
    # networks) every guest shares one address.
    scope = "marketplace_booking"
    rate = "60/hour"


class LookupThrottle(IpThrottle):
    scope = "marketplace_lookup"
    rate = "30/min"


class PublicView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [PublicReadThrottle]


def _validated(serializer_class, data, **kwargs):
    serializer = serializer_class(data=data, **kwargs)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class DestinationsView(PublicView):
    """`GET destinations/` — cities with listed hotels (most hotels first) and a cover photo."""

    @extend_schema(
        responses=OpenApiResponse(
            OpenApiTypes.OBJECT, description="[{city, department, properties_count, cover_photo}]"
        ),
        auth=[],
    )
    def get(self, request):
        return Response(catalog.destinations())


class SearchView(PublicView):
    """`GET search/` — a city's listed hotels; with dates, only available ones and their cheapest offer."""

    @extend_schema(
        parameters=[
            OpenApiParameter("city", OpenApiTypes.STR),
            *STAY_PARAMS,
            OpenApiParameter(
                "type", OpenApiTypes.STR, description="hotel|hostel|boutique|aparthotel|glamping (repetible)"
            ),
            OpenApiParameter("stars", OpenApiTypes.INT, description="Estrellas exactas (repetible)"),
            OpenApiParameter(
                "amenities", OpenApiTypes.STR, description="Códigos; el hotel debe tenerlos todos"
            ),
            OpenApiParameter("min_price", OpenApiTypes.NUMBER, description="Precio por noche mínimo"),
            OpenApiParameter("max_price", OpenApiTypes.NUMBER, description="Precio por noche máximo"),
            OpenApiParameter("sort", OpenApiTypes.STR, enum=list(SORTS)),
        ],
        responses=OpenApiResponse(
            OpenApiTypes.OBJECT, description="{count, nights, results: [card + offer]}"
        ),
        auth=[],
    )
    def get(self, request):
        data = _validated(s.SearchQuerySerializer, s.query_dict(request.query_params))
        query = SearchQuery(
            city=data["city"],
            checkin=data["checkin"],
            checkout=data["checkout"],
            adults=data["adults"],
            children=data["children"],
            children_ages=data["children_ages"],
            types=sorted(set(data["type"])),
            stars=sorted(set(data["stars"])),
            amenities=sorted(set(data["amenities"])),
            min_price=data["min_price"],
            max_price=data["max_price"],
            sort=data["sort"],
        )
        return Response(search(query))


class PropertyDetailView(PublicView):
    """`GET properties/<slug>/?via=` — the public hotel page (404 if the channel does not sell it)."""

    @extend_schema(parameters=[VIA], responses=OpenApiResponse(OpenApiTypes.OBJECT), auth=[])
    def get(self, request, slug):
        via = _validated(s.ChannelQuerySerializer, request.query_params)["via"]
        prop = engine.channel_property(slug, via)
        return Response(catalog.property_detail(prop, via))


class PropertyOffersView(PublicView):
    """`GET properties/<slug>/offers/` — bookable offers (room type × plan) with the exact total."""

    @extend_schema(
        parameters=[
            *STAY_PARAMS,
            VIA,
            OpenApiParameter("promo_code", OpenApiTypes.STR),
            OpenApiParameter(
                "foreign", OpenApiTypes.BOOL, description="Extranjero no residente (IVA exento)"
            ),
        ],
        responses=OpenApiResponse(
            OpenApiTypes.OBJECT, description="{nights, tax_exempt, promo, offers: [...]}"
        ),
        auth=[],
    )
    def get(self, request, slug):
        data = _validated(s.OffersQuerySerializer, s.query_dict(request.query_params))
        prop = engine.channel_property(slug, data["via"])
        items = sellable_offers(
            prop,
            via=data["via"],
            checkin=data["checkin"],
            checkout=data["checkout"],
            adults=data["adults"],
            children=data["children"],
            children_ages=data["children_ages"] or None,
            promo_code=data["promo_code"],
            foreign=data["foreign"],
        )
        return Response(
            offers_response(
                prop,
                items,
                checkin=data["checkin"],
                checkout=data["checkout"],
                adults=data["adults"],
                children=data["children"],
                promo_code=data["promo_code"],
                foreign=data["foreign"],
            )
        )


class CheckoutQuoteView(PublicView):
    """`POST checkout/quote/` — exact price of a selection (rooms, extras, IVA exemption) before booking."""

    throttle_classes = [QuoteThrottle]

    @extend_schema(request=s.CheckoutSerializer, responses=OpenApiResponse(OpenApiTypes.OBJECT), auth=[])
    def post(self, request):
        data = _validated(s.CheckoutSerializer, request.data)
        return Response(checkout.quote_selection(data))


class BookingsView(PublicView):
    """`POST bookings/` — create the reservation (and the payment link when something is paid now)."""

    throttle_classes = [BookingThrottle]

    @extend_schema(
        request=s.BookingSerializer, responses={201: OpenApiResponse(OpenApiTypes.OBJECT)}, auth=[]
    )
    def post(self, request):
        data = _validated(s.BookingSerializer, request.data)
        return Response(checkout.create_booking(data), status=status.HTTP_201_CREATED)


class BookingLookupView(PublicView):
    """`GET bookings/<code>/?email=` — the confirmation page (404 unless the email is the booker's)."""

    throttle_classes = [LookupThrottle]

    @extend_schema(
        parameters=[OpenApiParameter("email", OpenApiTypes.EMAIL, required=True)],
        responses=OpenApiResponse(OpenApiTypes.OBJECT),
        auth=[],
    )
    def get(self, request, code):
        data = _validated(s.LookupQuerySerializer, request.query_params)
        return Response(lookup.booking_status(code, data["email"]))


class EngineConfigView(PublicView):
    """`GET properties/<slug>/booking-engine/` — brand, texts and booking window of the hotel's engine."""

    @extend_schema(responses=OpenApiResponse(OpenApiTypes.OBJECT), auth=[])
    def get(self, request, slug):
        prop = engine.selling_properties().filter(slug=slug).first()
        if prop is None:
            raise NotFoundError("Este hotel no existe")
        return Response(catalog.engine_config(prop))
