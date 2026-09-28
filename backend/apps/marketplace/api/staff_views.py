"""Staff API of C4 (`/api/v1/marketplace/`, `marketplace.manage`): booking engine, listing and snippet."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.core.tenancy import PropertyScopedAPIView
from apps.marketplace.api import serializers as s
from apps.marketplace.services import configuration

MANAGE = "marketplace.manage"
IMAGE_KINDS = {"logo": "logo", "hero": "hero_image"}


def _validated(serializer_class, request, **kwargs):
    serializer = serializer_class(data=request.data, context={"property": request.property}, **kwargs)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class BookingEngineView(PropertyScopedAPIView):
    """`GET/PATCH booking-engine/` — the hotel's booking engine (the color is also the hotel brand)."""

    required_permissions = {"get": MANAGE, "patch": MANAGE}

    @extend_schema(responses=OpenApiResponse(OpenApiTypes.OBJECT))
    def get(self, request):
        return Response(configuration.engine_payload(request.property))

    @extend_schema(request=s.EngineSettingsSerializer, responses=OpenApiResponse(OpenApiTypes.OBJECT))
    def patch(self, request):
        data = _validated(s.EngineSettingsSerializer, request, partial=True)
        configuration.update_engine(request.property, data, actor=request.user)
        return Response(configuration.engine_payload(request.property))


class EngineImageView(PropertyScopedAPIView):
    """`POST/DELETE booking-engine/logo/` and `booking-engine/hero/` (multipart `image`, JPG/PNG/WEBP)."""

    required_permissions = {"post": MANAGE, "delete": MANAGE}
    parser_classes = [MultiPartParser, FormParser]

    def _kind(self, kind: str) -> str:
        if kind not in IMAGE_KINDS:
            raise NotFound("Imagen desconocida")
        return IMAGE_KINDS[kind]

    @extend_schema(request=s.ImageUploadSerializer, responses=OpenApiResponse(OpenApiTypes.OBJECT))
    def post(self, request, kind):
        field = self._kind(kind)
        image = _validated(s.ImageUploadSerializer, request)["image"]
        configuration.set_engine_image(request.property, field, image, actor=request.user)
        return Response(configuration.engine_payload(request.property))

    @extend_schema(responses=OpenApiResponse(OpenApiTypes.OBJECT))
    def delete(self, request, kind):
        configuration.set_engine_image(request.property, self._kind(kind), None, actor=request.user)
        return Response(configuration.engine_payload(request.property))


class ListingView(PropertyScopedAPIView):
    """`GET/PATCH listing/` — how the hotel shows up in the marketplace (and whether it is listed)."""

    required_permissions = {"get": MANAGE, "patch": MANAGE}

    @extend_schema(responses=OpenApiResponse(OpenApiTypes.OBJECT))
    def get(self, request):
        return Response(configuration.listing_payload(request.property))

    @extend_schema(request=s.ListingSerializer, responses=OpenApiResponse(OpenApiTypes.OBJECT))
    def patch(self, request):
        data = _validated(s.ListingSerializer, request, partial=True)
        configuration.update_listing(request.property, data, actor=request.user)
        return Response(configuration.listing_payload(request.property))


class EmbedSnippetView(PropertyScopedAPIView):
    """`GET embed-snippet/` — links and HTML to put the booking engine on the hotel's own website."""

    required_permissions = {"get": MANAGE}

    @extend_schema(responses=OpenApiResponse(OpenApiTypes.OBJECT))
    def get(self, request):
        return Response(configuration.embed_snippet(request.property))
