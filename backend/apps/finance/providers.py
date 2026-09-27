"""Payment providers for `kind="payments"` (spec §1.2): real = Wompi, simulated = local gateway page.

Interface (plan B4), every method returns plain dicts so other kinds (e.g. C11 `saas_billing`) can mirror it:

- `create_checkout(intent) -> {"checkout_url": str}`
- `fetch_status(intent) -> {"status", "method", "provider_reference", "amount", "message", "payload"}` where
  `status` ∈ created (no transaction yet) | pending | approved | declined | voided | error | expired,
  `method` is a `Payment.Method` value and `amount` a Decimal (or None).
- `parse_webhook(request) -> dict | None` validates the signature; None when it is not genuine.
- `refund(payment, amount) -> {"status": approved|pending|failed, "provider_reference", "instructions",
  "message", "payload"}`.

Providers never touch the database: `apps.finance.services` applies what they report.
"""

from __future__ import annotations

import json
from datetime import UTC
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.http.request import RawPostDataException

from apps.core.codes import generate_code
from apps.core.integrations import BaseProvider, register_provider
from apps.finance import wompi
from apps.finance.errors import IntegrationMisconfigured, ProviderError

NO_TRANSACTION = {
    "status": "created",
    "method": "",
    "provider_reference": "",
    "amount": None,
    "message": "",
    "payload": {},
}
MANUAL_WOMPI_REFUND = (
    "Wompi no hizo el reembolso automático{detail}. Haz una transferencia al huésped por este monto desde la "
    "cuenta del hotel y marca el reembolso como hecho."
)
UNCERTAIN_WOMPI_REFUND = (
    "Wompi no respondió a la solicitud de reembolso{detail}. Revisa en el panel de Wompi si quedó "
    "aplicado: si no, haz una transferencia al huésped por este monto. Después márcalo aquí como hecho."
)
PROCESSING_WOMPI_REFUND = (
    "Wompi recibió el reembolso ({detail}) y aún lo está procesando. Confírmalo en el panel de Wompi y "
    "márcalo aquí como hecho."
)


def redirect_url_for(intent) -> str:
    """Where the gateway sends the guest back: the intent's `return_url` + `payment_ref=<reference>`
    (Wompi also appends `id=<transaction id>`). Empty when the intent has no return URL."""
    if not intent.return_url:
        return ""
    parts = urlsplit(intent.return_url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "payment_ref"]
    query.append(("payment_ref", intent.reference))
    return urlunsplit(parts._replace(query=urlencode(query)))


class PaymentProvider(BaseProvider):
    kind = "payments"
    code = ""  # stored in PaymentIntent.provider and Payment.provider

    def create_checkout(self, intent) -> dict:
        raise NotImplementedError

    def fetch_status(self, intent) -> dict:
        raise NotImplementedError

    def parse_webhook(self, request) -> dict | None:
        return None

    def refund(self, payment, amount) -> dict:
        raise NotImplementedError


class SimulatedPaymentProvider(PaymentProvider):
    """Local gateway: the guest decides on `/sim/pay/<reference>` (approve / decline / let it expire).

    The decision is stored in `intent.payload["simulation"]` by the public `decide` endpoint, which then
    runs the normal `sync_payment_intent` — the same path a real provider's webhook takes.
    """

    mode = "simulated"
    code = "simulated"
    label = "Pasarela simulada (sin cobros reales)"
    CONFIG_FIELDS: list[dict] = []

    def create_checkout(self, intent) -> dict:
        return {"checkout_url": f"{settings.FRONTEND_URL}/sim/pay/{intent.reference}"}

    def fetch_status(self, intent) -> dict:
        simulation = (intent.payload or {}).get("simulation") or {}
        outcome = simulation.get("outcome")
        if outcome not in ("approved", "declined", "expired"):
            return dict(NO_TRANSACTION)
        return {
            "status": outcome,
            "method": simulation.get("method", ""),
            "provider_reference": simulation.get("transaction_id", ""),
            "amount": intent.amount,
            "message": "",
            "payload": {"simulated": True, **simulation},
        }

    def refund(self, payment, amount) -> dict:
        return {
            "status": "approved",
            "provider_reference": f"SIMREF-{generate_code('', 8)}",
            "instructions": "",
            "message": "",
            "payload": {"simulated": True},
        }


def _field(
    name, label_es, label_en, type_, *, secret=False, required=True, help_es="", help_en="", options=None
):
    field = {
        "name": name,
        "label_es": label_es,
        "label_en": label_en,
        "type": type_,
        "secret": secret,
        "required": required,
        "help_es": help_es,
        "help_en": help_en,
    }
    if options:
        field["options"] = options
    return field


def _wompi_time(value) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _read_event(request) -> dict | None:
    data = getattr(request, "data", None)  # DRF Request (already parsed)
    if isinstance(data, dict):
        return data
    try:
        event = json.loads(request.body)
    except (AttributeError, RawPostDataException, TypeError, ValueError):
        return None
    return event if isinstance(event, dict) else None


def _refund_result(status, *, reference="", instructions="", message="", payload=None) -> dict:
    return {
        "status": status,
        "provider_reference": reference,
        "instructions": instructions,
        "message": message,
        "payload": payload or {},
    }


def _unanswered(exc: ProviderError) -> bool:
    """Network failure or 5xx: Wompi may or may not have applied the operation."""
    return exc.status is None or exc.status >= 500


def _uncertain_refund(exc: ProviderError) -> dict:
    return _refund_result(
        "pending", instructions=UNCERTAIN_WOMPI_REFUND.format(detail=f" ({exc})"), payload=exc.payload
    )


def _result_from(transaction: dict) -> dict:
    return {
        "status": wompi.STATUS_MAP.get(transaction.get("status"), "pending"),
        "method": wompi.METHOD_MAP.get(transaction.get("payment_method_type"), "wompi_other"),
        "provider_reference": transaction.get("id", ""),
        "amount": wompi.transaction_amount(transaction),
        "message": transaction.get("status_message") or "",
        "payload": {"transaction": transaction},
    }


class WompiProvider(PaymentProvider):
    """Wompi checkout web + active verification (`GET /transactions`) + signed events + voids / refunds."""

    mode = "real"
    code = "wompi"
    label = "Wompi (tarjeta, PSE, Nequi)"
    CONFIG_FIELDS = [
        _field(
            "environment",
            "Ambiente",
            "Environment",
            "select",
            options=[
                {"value": "sandbox", "label_es": "Sandbox (pruebas)", "label_en": "Sandbox (testing)"},
                {"value": "production", "label_es": "Producción", "label_en": "Production"},
            ],
        ),
        _field(
            "public_key",
            "Llave pública",
            "Public key",
            "text",
            help_es="Empieza por pub_test_ (sandbox) o pub_prod_ (producción).",
            help_en="Starts with pub_test_ (sandbox) or pub_prod_ (production).",
        ),
        _field(
            "private_key",
            "Llave privada",
            "Private key",
            "password",
            secret=True,
            help_es="prv_test_… / prv_prod_…: consulta transacciones, anula y reembolsa pagos.",
            help_en="prv_test_… / prv_prod_…: used to query transactions, void and refund payments.",
        ),
        _field(
            "integrity_secret",
            "Secreto de integridad",
            "Integrity secret",
            "password",
            secret=True,
            help_es="Firma el checkout (Desarrolladores → Secretos para integración técnica).",
            help_en="Signs the checkout (Developers → Technical integration secrets).",
        ),
        _field(
            "events_secret",
            "Secreto de eventos",
            "Events secret",
            "password",
            secret=True,
            help_es="Valida los webhooks. URL de eventos: /api/v1/public/finance/webhooks/wompi/",
            help_en="Validates webhooks. Events URL: /api/v1/public/finance/webhooks/wompi/",
        ),
    ]

    @property
    def environment(self) -> str:
        return self.config.get("environment") or "sandbox"

    def _client(self) -> wompi.WompiClient:
        return wompi.WompiClient(
            environment=self.environment,
            public_key=self.config.get("public_key", ""),
            private_key=self.secrets.get("private_key", ""),
        )

    def _require(self, *names: str) -> None:
        values = {**self.config, **self.secrets}
        missing = [name for name in names if not values.get(name)]
        if missing:
            raise IntegrationMisconfigured(
                "Faltan credenciales de Wompi en la integración de pagos: " + ", ".join(missing),
                missing=missing,
            )

    def create_checkout(self, intent) -> dict:
        self._require("public_key", "integrity_secret")
        folio = intent.folio
        guest = folio.guest or (folio.reservation.booker if folio.reservation_id else None)
        url = wompi.checkout_url(
            public_key=self.config["public_key"],
            reference=intent.reference,
            amount_in_cents=wompi.amount_in_cents(intent.amount),
            currency=intent.currency,
            integrity_secret=self.secrets["integrity_secret"],
            redirect_url=redirect_url_for(intent),
            expiration_time=_wompi_time(intent.expires_at) if intent.expires_at else "",
            customer_email=guest.email if guest else "",
            customer_name=guest.full_name if guest else "",
        )
        return {"checkout_url": url}

    def fetch_status(self, intent) -> dict:
        self._require("private_key")
        client = self._client()
        transaction = None
        if intent.provider_transaction_id:
            # The id may come from the return URL, which anyone can edit: an unknown id (4xx) or one of
            # another reference is ignored and the reference search decides (it also replaces the stored id).
            try:
                transaction = client.get_transaction(intent.provider_transaction_id)
            except ProviderError as exc:
                if exc.status is None or exc.status >= 500:
                    raise
            if not transaction or transaction.get("reference") != intent.reference:
                transaction = None
        if transaction is None:
            transaction = wompi.pick_transaction(client.find_transactions(intent.reference))
        return _result_from(transaction) if transaction else dict(NO_TRANSACTION)

    def parse_webhook(self, request) -> dict | None:
        event = _read_event(request)
        if event is None:
            return None
        header = request.headers.get("X-Event-Checksum") if hasattr(request, "headers") else None
        if not wompi.verify_event(event, self.secrets.get("events_secret", ""), header):
            return None
        transaction = (event.get("data") or {}).get("transaction") or {}
        return {
            "event": event.get("event", ""),
            "reference": transaction.get("reference", ""),
            "status": wompi.STATUS_MAP.get(transaction.get("status"), ""),
            "transaction_id": transaction.get("id", ""),
            "method": wompi.METHOD_MAP.get(transaction.get("payment_method_type"), "wompi_other"),
            "transaction": transaction,
        }

    def refund(self, payment, amount) -> dict:
        """Card payments are voided (`POST /transactions/{id}/void`, cards only); when that is no longer
        possible, and for every other method, the Refunds API V2 is used (`POST /refunds`).

        Approved → `approved`. A definitive "no" → card: `failed` (the amount is freed to retry); other
        methods: `pending` with manual-transfer instructions. No answer (network / 5xx) → `pending` asking to
        check the Wompi dashboard first, so nobody refunds twice."""
        client = self._client()
        cents = wompi.amount_in_cents(amount)
        is_card = payment.method == "wompi_card"
        problems: list[str] = []
        if is_card:
            try:
                data = client.void_transaction(payment.provider_reference, cents)
            except ProviderError as exc:
                if _unanswered(exc):  # it may have been voided: a refund on top could pay twice
                    return _uncertain_refund(exc)
                problems.append(f"anulación: {exc}")
            else:
                return _refund_result(
                    "approved", reference=payment.provider_reference, payload={"void": data}
                )
        intent = getattr(payment, "intent", None) if payment.intent_id else None
        try:
            data = client.create_refund(
                payment.provider_reference,
                cents,
                reason="Reembolso registrado en Housetel",
                reference=intent.reference if intent else str(payment.pk),
            )
        except ProviderError as exc:
            if _unanswered(exc):
                return _uncertain_refund(exc)
            problems.append(f"reembolso: {exc}")
            payload = exc.payload
        else:
            status = str(data.get("status") or "").upper()
            refund_id = str(data.get("v2_refund_id") or data.get("id") or "")
            if status == "APPROVED":
                return _refund_result("approved", reference=refund_id, payload={"refund": data})
            if status not in ("DECLINED", "ERROR", "CANCELLED"):
                detail = refund_id or status or "sin estado"
                return _refund_result(
                    "pending",
                    reference=refund_id,
                    instructions=PROCESSING_WOMPI_REFUND.format(detail=detail),
                    payload={"refund": data},
                )
            problems.append(f"reembolso {status}: {data.get('status_message') or 'sin detalle'}")
            payload = {"refund": data}
        detail = "; ".join(problems)
        if is_card:
            return _refund_result("failed", message=f"Wompi no devolvió el pago ({detail})", payload=payload)
        return _refund_result(
            "pending", instructions=MANUAL_WOMPI_REFUND.format(detail=f" ({detail})"), payload=payload
        )

    def test_connection(self) -> tuple[bool, str]:
        env = self.environment
        suffix = "test" if env == "sandbox" else "prod"
        public_key = self.config.get("public_key", "")
        if not public_key.startswith(f"pub_{suffix}_"):
            return False, f"En el ambiente «{env}» la llave pública debe empezar por pub_{suffix}_"
        if not self.secrets.get("private_key", "").startswith(f"prv_{suffix}_"):
            return False, f"En el ambiente «{env}» la llave privada debe empezar por prv_{suffix}_"
        client = self._client()
        try:
            merchant = client.merchant()
        except ProviderError as exc:
            return False, f"Wompi no reconoce la llave pública ({exc})"
        try:
            client.find_transactions("HOUSETEL-CONNECTION-TEST")
        except ProviderError as exc:
            return False, f"Wompi rechazó la llave privada ({exc})"
        name = merchant.get("name") or merchant.get("legal_name") or merchant.get("id") or ""
        return True, f"Conectado a Wompi ({env}) {name}".strip()


register_provider("payments", "simulated", SimulatedPaymentProvider)
register_provider("payments", "real", WompiProvider)
