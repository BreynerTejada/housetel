from dataclasses import dataclass
from uuid import UUID


@dataclass
class OutboundMessage:
    """One delivery attempt returned by `send_message` (one per channel actually used)."""

    channel: str  # email | whatsapp
    to: str
    status: str  # queued | sent | delivered | failed | skipped
    subject: str = ""
    body: str = ""
    template_code: str = ""
    provider_message_id: str = ""
    error: str = ""
    message_id: UUID | None = None  # messaging.Message row (C6)
