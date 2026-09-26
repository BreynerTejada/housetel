"""Messaging contract (spec §4.2). Phase A stub: logs and returns []; C6 implements templates and delivery."""

import logging

from apps.messaging.types import OutboundMessage

logger = logging.getLogger("housetel.messaging")


def send_message(
    *,
    property,
    template_code,
    guest=None,
    reservation=None,
    to=None,
    channels=("email",),
    context=None,
    language=None,
) -> list[OutboundMessage]:
    """Render `template_code` in the guest's language and send it through each channel (email | whatsapp).

    Phase A: nothing is sent; the call is logged (without recipient data) and no messages are returned.
    """
    logger.info(
        "send_message stub: property=%s template=%s channels=%s reservation=%s guest=%s explicit_to=%s",
        getattr(property, "pk", None),
        template_code,
        ",".join(channels),
        getattr(reservation, "pk", None),
        getattr(guest, "pk", None),
        bool(to),
    )
    return []
