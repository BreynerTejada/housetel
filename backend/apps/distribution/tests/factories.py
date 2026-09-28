"""Distribution factories + `connect()`, a helper that creates a mapped connection for a test hotel."""

from decimal import Decimal

import factory

from apps.core.tests.factories import PropertyFactory
from apps.distribution.models import ChannelConnection, RateMapping, RoomMapping

PREFIXES = {"booksim": "BS", "airsim": "AS", "channex": "CH", "ical": "IC"}


class ChannelConnectionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ChannelConnection

    property = factory.SubFactory(PropertyFactory)
    channel_code = ChannelConnection.Channel.BOOKSIM
    name = factory.LazyAttribute(lambda o: ChannelConnection.Channel(o.channel_code).label)
    status = ChannelConnection.Status.ACTIVE


class RoomMappingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RoomMapping

    connection = factory.SubFactory(ChannelConnectionFactory)
    external_room_id = factory.Sequence(lambda n: f"ROOM-{n}")


class RateMappingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RateMapping

    connection = factory.SubFactory(ChannelConnectionFactory)
    external_rate_id = factory.Sequence(lambda n: f"RATE-{n}")
    markup_percent = Decimal("0")


def connect(hotel, channel="booksim", *, room_types=None, plans=None, markup="0", **fields):
    """A connection of `hotel.prop` mapping `room_types` (default DBL and STE) and `plans` (default the base
    plan) with readable external ids: `BS-DBL`, `BS-BAR`, …"""
    prefix = PREFIXES[channel]
    connection = ChannelConnectionFactory(property=hotel.prop, channel_code=channel, **fields)
    for room_type in room_types if room_types is not None else [hotel.dbl, hotel.ste]:
        RoomMappingFactory(
            connection=connection, room_type=room_type, external_room_id=f"{prefix}-{room_type.code}"
        )
    for plan in plans if plans is not None else [hotel.plan]:
        RateMappingFactory(
            connection=connection,
            rate_plan=plan,
            external_rate_id=f"{prefix}-{plan.code}",
            markup_percent=Decimal(markup),
        )
    return connection
