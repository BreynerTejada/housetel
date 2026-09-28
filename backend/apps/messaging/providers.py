"""Integration providers of messaging (spec §1.2): `email` (real = SMTP, the default — Mailpit locally;
simulated = only recorded) and `whatsapp` (real = Meta WhatsApp Cloud API; simulated = recorded as
delivered). Registered with `apps.core.integrations.register_provider` (auto-discovered)."""

import logging
import smtplib
import uuid
from dataclasses import dataclass
from email.headerregistry import Address
from email.utils import make_msgid, parseaddr

import httpx
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

from apps.core.integrations import BaseProvider, register_provider
from apps.messaging import whatsapp

logger = logging.getLogger("housetel.messaging")


@dataclass(frozen=True)
class DeliveryResult:
    status: str  # sent | delivered | failed
    provider_message_id: str = ""
    error: str = ""


def _field(name, label_es, label_en, type_="text", *, secret=False, required=False, help_es="", help_en=""):
    return {
        "name": name,
        "label_es": label_es,
        "label_en": label_en,
        "type": type_,
        "secret": secret,
        "required": required,
        "options": [],
        "help_es": help_es,
        "help_en": help_en,
    }


# --- email ---------------------------------------------------------------------------------------------


class EmailProvider(BaseProvider):
    kind = "email"

    def send_email(self, *, to: str, subject: str, text: str, html: str) -> DeliveryResult:
        raise NotImplementedError


class SmtpEmailProvider(EmailProvider):
    """SMTP. Without `smtp_host` it uses the platform SMTP from the environment (Mailpit in development)."""

    mode = "real"
    label = "SMTP"
    CONFIG_FIELDS = [
        _field(
            "from_email",
            "Remitente",
            "Sender",
            help_es="Ej. «Hotel Casa Aurora <reservas@casaaurora.co>». "
            "Vacío: el remitente de la plataforma con el nombre del hotel.",
            help_en="E.g. “Hotel Casa Aurora <bookings@casaaurora.co>”. Empty: the platform sender with the "
            "hotel name.",
        ),
        _field(
            "reply_to",
            "Responder a",
            "Reply-to",
            help_es="Vacío: el correo del hotel.",
            help_en="Empty: the hotel email.",
        ),
        _field(
            "smtp_host",
            "Servidor SMTP propio",
            "Own SMTP server",
            help_es="Vacío: el servidor de correo de la plataforma.",
            help_en="Empty: the platform mail server.",
        ),
        _field("smtp_port", "Puerto SMTP", "SMTP port", "number"),
        _field("smtp_username", "Usuario SMTP", "SMTP user"),
        _field("smtp_password", "Contraseña SMTP", "SMTP password", "password", secret=True),
        _field("smtp_use_tls", "Usar TLS", "Use TLS", "boolean"),
    ]

    def _connection(self):
        host = (self.config.get("smtp_host") or "").strip()
        if not host:
            return get_connection()
        return get_connection(
            "django.core.mail.backends.smtp.EmailBackend",
            host=host,
            port=int(self.config.get("smtp_port") or 587),
            username=self.config.get("smtp_username") or "",
            password=self.secrets.get("smtp_password") or "",
            use_tls=bool(self.config.get("smtp_use_tls", True)),
            timeout=15,
        )

    def _from_email(self) -> str:
        configured = (self.config.get("from_email") or "").strip()
        name, address = parseaddr(configured or settings.DEFAULT_FROM_EMAIL)
        prop = self.setting.property
        display = name if configured and name else (prop.name if prop is not None else name)
        return str(Address(display_name=display, addr_spec=address))

    def _reply_to(self) -> list[str]:
        prop = self.setting.property
        reply_to = (self.config.get("reply_to") or "").strip() or (prop.email if prop is not None else "")
        return [reply_to] if reply_to else []

    def send_email(self, *, to, subject, text, html) -> DeliveryResult:
        message_id = make_msgid(domain="housetel.co")
        email = EmailMultiAlternatives(
            subject=subject,
            body=text,
            from_email=self._from_email(),
            to=[to],
            reply_to=self._reply_to(),
            headers={"Message-ID": message_id},
            connection=self._connection(),
        )
        email.attach_alternative(html, "text/html")
        try:
            email.send()
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning("SMTP delivery failed (%s): %s", type(exc).__name__, exc)
            return DeliveryResult("failed", error=f"El servidor de correo rechazó el envío: {exc}"[:1000])
        return DeliveryResult("sent", provider_message_id=message_id)

    def test_connection(self) -> tuple[bool, str]:
        connection = self._connection()
        try:
            connection.open()
        except (smtplib.SMTPException, OSError) as exc:
            return False, f"No se pudo conectar al servidor de correo: {exc}"
        finally:
            connection.close()
        return True, "Conexión SMTP correcta"


class SimulatedEmailProvider(EmailProvider):
    mode = "simulated"
    label = "Simulado"

    def send_email(self, *, to, subject, text, html) -> DeliveryResult:
        return DeliveryResult("sent", provider_message_id=f"SIMMAIL-{uuid.uuid4().hex[:16]}")


# --- WhatsApp ------------------------------------------------------------------------------------------


class WhatsAppProvider(BaseProvider):
    kind = "whatsapp"

    def send_whatsapp(self, *, to: str, text: str, template: dict | None = None) -> DeliveryResult:
        """`to` is E.164. `template` ({name, language, parameters}) is used outside the 24 h window."""
        raise NotImplementedError


class WhatsAppCloudProvider(WhatsAppProvider):
    """Meta WhatsApp Cloud API (see `apps/messaging/whatsapp.py`). Delivery and read receipts and the guest's
    replies arrive at `POST /api/v1/public/messaging/webhooks/whatsapp/`."""

    mode = "real"
    label = "WhatsApp Cloud API (Meta)"
    CONFIG_FIELDS = [
        _field(
            "phone_number_id",
            "Phone number ID",
            "Phone number ID",
            required=True,
            help_es="Identificador del número en Meta (WhatsApp › Configuración de la API).",
            help_en="Number identifier in Meta (WhatsApp › API Setup).",
        ),
        _field(
            "access_token",
            "Token de acceso",
            "Access token",
            "password",
            secret=True,
            required=True,
            help_es="Token permanente de un usuario del sistema con permiso whatsapp_business_messaging.",
            help_en="Permanent system-user token with the whatsapp_business_messaging permission.",
        ),
        _field(
            "app_secret",
            "Clave secreta de la app",
            "App secret",
            "password",
            secret=True,
            help_es="Valida la firma X-Hub-Signature-256 de los webhooks.",
            help_en="Validates the X-Hub-Signature-256 signature of the webhooks.",
        ),
        _field(
            "verify_token",
            "Token de verificación del webhook",
            "Webhook verify token",
            "password",
            secret=True,
            help_es="El mismo texto que configures en Meta al suscribir el webhook.",
            help_en="The same text you set in Meta when subscribing the webhook.",
        ),
        _field(
            "api_version",
            "Versión de la Graph API",
            "Graph API version",
            help_es=f"Por defecto {whatsapp.DEFAULT_API_VERSION}.",
            help_en=f"Default {whatsapp.DEFAULT_API_VERSION}.",
        ),
        _field(
            "template_language_es",
            "Idioma de plantillas en español",
            "Spanish template language",
            help_es="Código de idioma de tus plantillas aprobadas (por defecto «es»).",
            help_en="Language code of your approved templates (default “es”).",
        ),
        _field(
            "template_language_en",
            "Idioma de plantillas en inglés",
            "English template language",
            help_es="Por ejemplo «en» o «en_US» (por defecto «en»).",
            help_en="E.g. “en” or “en_US” (default “en”).",
        ),
    ]

    def _base_url(self) -> str:
        version = (self.config.get("api_version") or "").strip() or whatsapp.DEFAULT_API_VERSION
        return f"{whatsapp.GRAPH_BASE}/{version}"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.secrets.get('access_token', '')}"}

    def _missing(self) -> list[str]:
        values = {
            "phone_number_id": self.config.get("phone_number_id"),
            "access_token": self.secrets.get("access_token"),
        }
        return [name for name, value in values.items() if not value]

    def send_whatsapp(self, *, to, text, template=None) -> DeliveryResult:
        missing = self._missing()
        if missing:
            return DeliveryResult("failed", error=f"Faltan credenciales de WhatsApp: {', '.join(missing)}")
        if template:
            language = self.config.get(f"template_language_{template['language']}") or template["language"]
            payload = whatsapp.template_payload(
                to, template["name"], language, template.get("parameters") or []
            )
        else:
            payload = whatsapp.text_payload(to, text)
        url = f"{self._base_url()}/{self.config['phone_number_id']}/messages"
        try:
            response = httpx.post(url, json=payload, headers=self._headers(), timeout=whatsapp.TIMEOUT)
        except httpx.HTTPError as exc:
            return DeliveryResult("failed", error=f"No se pudo conectar con WhatsApp: {exc}")
        if response.status_code >= 400:
            return DeliveryResult("failed", error=whatsapp.describe_error(response))
        try:
            message_id = response.json()["messages"][0]["id"]
        except (ValueError, KeyError, IndexError, TypeError):
            return DeliveryResult("failed", error="Respuesta inesperada de WhatsApp")
        return DeliveryResult("sent", provider_message_id=message_id)

    def test_connection(self) -> tuple[bool, str]:
        missing = self._missing()
        if missing:
            return False, f"Faltan credenciales de WhatsApp: {', '.join(missing)}"
        url = f"{self._base_url()}/{self.config['phone_number_id']}"
        try:
            response = httpx.get(
                url,
                params={"fields": "display_phone_number,verified_name"},
                headers=self._headers(),
                timeout=whatsapp.TIMEOUT,
            )
        except httpx.HTTPError as exc:
            return False, f"No se pudo conectar con WhatsApp: {exc}"
        if response.status_code >= 400:
            return False, whatsapp.describe_error(response)
        data = response.json()
        return True, f"Conectado: {data.get('display_phone_number', '')} ({data.get('verified_name', '')})"


class SimulatedWhatsAppProvider(WhatsAppProvider):
    """Nothing leaves the server: the message is recorded as delivered (the simulator at
    /app/simulators/whatsapp plays the guest). The 24 h window is not enforced here."""

    mode = "simulated"
    label = "Simulado"

    def send_whatsapp(self, *, to, text, template=None) -> DeliveryResult:
        return DeliveryResult("delivered", provider_message_id=f"SIMWA-{uuid.uuid4().hex[:16]}")


register_provider("email", "real", SmtpEmailProvider)
register_provider("email", "simulated", SimulatedEmailProvider)
register_provider("whatsapp", "real", WhatsAppCloudProvider)
register_provider("whatsapp", "simulated", SimulatedWhatsAppProvider)
