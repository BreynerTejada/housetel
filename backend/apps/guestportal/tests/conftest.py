"""Fixtures of the guest portal tests.

The hotel comes from the bookings test helpers (`build_hotel`): DBL rooms 101/102/201 (320.000/night, base
occupancy 2, max 2 adults + 1 child), STE 301, a dorm D1 with beds A–D, base plan BAR, IVA 19 % excluded and
exempt for foreign non-residents. Business date 2026-10-01 (Thursday). Reservations are created through the
real booking services.
"""

import base64
import io

import pytest
from PIL import Image, ImageDraw

from apps.bookings.tests.helpers import book, build_hotel, oct_
from apps.core.tokens import make_reservation_token


@pytest.fixture
def hotel(prop):
    return build_hotel(prop)


@pytest.fixture
def reservation(hotel):
    """Confirmed DBL reservation for 2 adults, Oct 5 → Oct 7 (Colombian resident booker)."""
    return book(hotel, oct_(5), oct_(7))


@pytest.fixture
def token(reservation):
    return make_reservation_token(reservation)


@pytest.fixture
def portal_url(token):
    def _url(path: str = "") -> str:
        return f"/api/v1/public/guestportal/{token}/{path}"

    return _url


def png_bytes(*, blank: bool = False, size=(300, 120)) -> bytes:
    """A small PNG: a drawn stroke (a signature) or a fully transparent canvas."""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    if not blank:
        draw = ImageDraw.Draw(image)
        draw.line([(20, 80), (80, 30), (140, 90), (220, 40), (280, 70)], fill=(20, 20, 20, 255), width=4)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def signature_data_url(*, blank: bool = False) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes(blank=blank)).decode()


def jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 40), (200, 180, 160)).save(buffer, format="JPEG")
    return buffer.getvalue()
