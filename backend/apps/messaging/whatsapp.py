"""Meta WhatsApp Cloud API details (verified against developers.facebook.com on 2026-09-27):

- Version: Graph API v26.0 (released 2026-07-29, the latest; v25.0 stays valid until 2028-07-29). A hotel can
  pin another active version in the integration's `api_version`.
- Send: `POST https://graph.facebook.com/v26.0/{phone_number_id}/messages`, `Authorization: Bearer <token>`,
  JSON `{"messaging_product": "whatsapp", "recipient_type": "individual", "to", "type": "text",
  "text": {"preview_url", "body"}}` or `"type": "template", "template": {"name", "language": {"code"},
  "components": [{"type": "body", "parameters": [{"type": "text", "text"}]}]}`. Response
  `{"messaging_product", "contacts": [{"input", "wa_id"}], "messages": [{"id": "wamid…", "message_status"}]}`.
- Free-form messages only within 24 h of the customer's last message (customer service window); after that
  only approved templates: error 131047 "Message Outside 24-Hour Window".
- Errors: `{"error": {"message", "type", "code", "error_data": {"messaging_product", "details"},
  "fbtrace_id"}}`.
- Webhooks: `GET` verification with `hub.mode=subscribe`, `hub.verify_token`, `hub.challenge` (answer 200 with
  the challenge); `POST` notifications signed in `X-Hub-Signature-256: sha256=<HMAC-SHA256(raw body, app
  secret)>`, answered with 200 (Meta retries non-200 deliveries with decreasing frequency for up to 7 days,
  and may send duplicates, so processing is idempotent by message id).
  Payload: `entry[].changes[].value` with `metadata.phone_number_id`, `contacts[{profile.name, wa_id}]`,
  `messages[{from, id, timestamp, type, text.body}]` and `statuses[{id, status: sent|delivered|read|failed,
  timestamp, recipient_id, errors}]`.
"""

import hashlib
import hmac

GRAPH_BASE = "https://graph.facebook.com"
DEFAULT_API_VERSION = "v26.0"
OUTSIDE_WINDOW_ERROR = 131047
TIMEOUT = 10


def text_payload(to: str, text: str) -> dict:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": True, "body": text},
    }


def template_payload(to: str, name: str, language_code: str, parameters: list[str]) -> dict:
    template = {"name": name, "language": {"code": language_code}}
    if parameters:
        template["components"] = [
            {"type": "body", "parameters": [{"type": "text", "text": str(value)} for value in parameters]}
        ]
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "template",
        "template": template,
    }


def describe_error(response) -> str:
    """Human (Spanish) explanation of a Graph API error response."""
    try:
        error = response.json().get("error") or {}
    except ValueError:
        error = {}
    code = error.get("code")
    details = (error.get("error_data") or {}).get("details") or ""
    message = error.get("message") or f"HTTP {response.status_code}"
    if code == OUTSIDE_WINDOW_ERROR:
        return (
            f"Fuera de la ventana de 24 h de WhatsApp ({code}): el huésped no ha escrito en las últimas "
            "24 horas. "
            "Configura en la plantilla una plantilla aprobada por Meta para escribirle."
        )
    text = f"WhatsApp rechazó la solicitud ({code or response.status_code}): {message}"
    return f"{text}. {details}" if details else text


def signature_is_valid(raw_body: bytes, header: str, app_secret: str) -> bool:
    """`X-Hub-Signature-256: sha256=<hex>` = HMAC-SHA256 of the raw body with the app secret."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), header.removeprefix("sha256=").strip().lower().encode())
