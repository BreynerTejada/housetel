"""Platform billing providers (`kind="saas_billing"`, platform scope: `IntegrationSetting(property=None)`).

Interface (plain dicts, mirrors `apps.finance.providers`):
- `charge(invoice, subscription) -> {"status": approved|declined|pending|requires_action|error, "reference",
  "method", "message", "payload"}` — automatic charge of the saved payment method.
- `create_checkout(invoice, *, return_url) -> {"checkout_url", "payload"}` — pay one invoice by hand.
- `fetch_status(invoice) -> {"status", "reference", "method", "message"}` — verify a checkout or a charge.
- `card_setup() -> dict` — what the browser needs to tokenize a card (real mode) or `{}` (simulated).
- `create_payment_source(*, token, acceptance_token, accept_personal_auth, customer_email) -> dict` — save a
  card (real mode).

Simulated approves every charge unless `organization.settings["simulate_payment_failure"]` is true.
Real = Wompi with the platform account (`WOMPI_PLATFORM_*` environment variables, never the hotels' keys),
following docs.wompi.co ("Fuentes de pago", "Tokens de aceptación", checked 2026-09-27):
- The browser tokenizes the card itself (`POST /v1/tokens/cards` with the public key as Bearer, body
  `{number, cvc, exp_month "MM", exp_year "YY", card_holder}` → `data.id`): card data never reaches Housetel.
- The acceptance tokens come from `GET /v1/merchants/{public_key}` (`data.presigned_acceptance` and
  `data.presigned_personal_data_auth`, each with `acceptance_token` + `permalink`); the user must see both
  documents and accept them.
- Payment source: `POST /v1/payment_sources` (private key) `{type: "CARD", token, customer_email,
  acceptance_token, accept_personal_auth}` → `data.id`, `data.public_data`.
- Recurring charge: `POST /v1/transactions` (private key) with `payment_source_id`, `recurrent: true`,
  integrity `signature`, `payment_method.installments`; manual payments use the web checkout and
  `GET /v1/transactions?reference=` verifies them (see B4's notes).
"""

from __future__ import annotations

from django.conf import settings

from apps.core.codes import generate_code
from apps.core.integrations import BaseProvider, register_provider
from apps.finance import wompi
from apps.finance.errors import ProviderError


class SaasBillingProvider(BaseProvider):
    kind = "saas_billing"
    code = ""

    def charge(self, invoice, subscription) -> dict:
        raise NotImplementedError

    def create_checkout(self, invoice, *, return_url: str) -> dict:
        raise NotImplementedError

    def fetch_status(self, invoice) -> dict:
        raise NotImplementedError

    def card_setup(self) -> dict:
        return {}

    def create_payment_source(
        self, *, token: str, acceptance_token: str, accept_personal_auth: str = "", customer_email: str
    ) -> dict:
        raise NotImplementedError


class SimulatedSaasBillingProvider(SaasBillingProvider):
    mode = "simulated"
    code = "simulated"
    label = "Cobro simulado (sin cargos reales)"
    CONFIG_FIELDS: list[dict] = []

    def charge(self, invoice, subscription) -> dict:
        org = invoice.organization
        source = (subscription.payment_source if subscription else None) or {}
        method = (
            f"{source.get('brand', 'CARD')} •••• {source.get('last4', '4242')}" if source else "Pago simulado"
        )
        if (org.settings or {}).get("simulate_payment_failure"):
            return {
                "status": "declined",
                "reference": "",
                "method": method,
                "message": "Tarjeta rechazada (simulación de fallo activada para esta organización)",
                "payload": {"simulated": True},
            }
        return {
            "status": "approved",
            "reference": f"SIM-SAAS-{generate_code('', 8)}",
            "method": method,
            "message": "",
            "payload": {"simulated": True},
        }

    def create_checkout(self, invoice, *, return_url: str) -> dict:
        return {"checkout_url": None, "payload": {}}

    def fetch_status(self, invoice) -> dict:
        return {"status": "created", "reference": "", "method": "", "message": ""}

    def create_payment_source(
        self, *, token: str, acceptance_token: str, accept_personal_auth: str = "", customer_email: str
    ) -> dict:
        raise ProviderError("El modo simulado no guarda tarjetas en Wompi")


class PlatformWompiClient(wompi.WompiClient):
    """B4's Wompi client plus the two platform-only calls (payment sources and direct transactions)."""

    def create_payment_source(self, body: dict) -> dict:
        return self._request("POST", "/payment_sources", json=body).get("data") or {}

    def create_transaction(self, body: dict) -> dict:
        return self._request("POST", "/transactions", json=body).get("data") or {}


def _result(transaction: dict, reference: str) -> dict:
    return {
        "status": wompi.STATUS_MAP.get(transaction.get("status"), "pending"),
        "reference": transaction.get("id", "") or reference,
        "method": transaction.get("payment_method_type", ""),
        "message": transaction.get("status_message") or "",
        "payload": {"transaction_id": transaction.get("id", ""), "reference": reference},
    }


class WompiSaasBillingProvider(SaasBillingProvider):
    mode = "real"
    code = "wompi"
    label = "Wompi (cuenta de la plataforma)"
    CONFIG_FIELDS: list[dict] = []  # credentials come from the environment (WOMPI_PLATFORM_*)

    REQUIRED = (
        "WOMPI_PLATFORM_PUBLIC_KEY",
        "WOMPI_PLATFORM_PRIVATE_KEY",
        "WOMPI_PLATFORM_INTEGRITY_SECRET",
    )

    def _missing(self) -> list[str]:
        return [name for name in self.REQUIRED if not getattr(settings, name, "")]

    def _client(self) -> PlatformWompiClient:
        missing = self._missing()
        if missing:
            raise ProviderError(f"Faltan credenciales de Wompi de la plataforma: {', '.join(missing)}")
        return PlatformWompiClient(
            environment=settings.WOMPI_PLATFORM_ENV,
            public_key=settings.WOMPI_PLATFORM_PUBLIC_KEY,
            private_key=settings.WOMPI_PLATFORM_PRIVATE_KEY,
        )

    def test_connection(self) -> tuple[bool, str]:
        missing = self._missing()
        if missing:
            return False, f"Faltan variables de entorno: {', '.join(missing)}"
        try:
            merchant = self._client().merchant()
        except ProviderError as exc:
            return False, str(exc)
        return True, f"Conectado a Wompi ({settings.WOMPI_PLATFORM_ENV}): {merchant.get('name', '')}".strip()

    def charge(self, invoice, subscription) -> dict:
        source_id = ((subscription.payment_source if subscription else None) or {}).get(
            "wompi_payment_source_id"
        )
        if not source_id:
            return {"status": "requires_action", "message": "Sin fuente de pago en Wompi", "payload": {}}
        reference = f"{invoice.number}-A{invoice.attempts + 1}"
        cents = wompi.amount_in_cents(invoice.total)
        owner_email = (subscription.payment_source or {}).get("customer_email") or ""
        body = {
            "amount_in_cents": cents,
            "currency": invoice.currency,
            "signature": wompi.integrity_signature(
                reference, cents, invoice.currency, settings.WOMPI_PLATFORM_INTEGRITY_SECRET
            ),
            "customer_email": owner_email,
            "payment_method": {"installments": 1},
            "reference": reference,
            "payment_source_id": int(source_id),
            "recurrent": True,
        }
        try:
            transaction = self._client().create_transaction(body)
            if transaction.get("status") == "PENDING" and transaction.get("id"):
                transaction = self._client().get_transaction(transaction["id"]) or transaction
        except ProviderError as exc:
            return {"status": "error", "reference": "", "method": "", "message": str(exc), "payload": {}}
        return _result(transaction, reference)

    def create_checkout(self, invoice, *, return_url: str) -> dict:
        reference = f"{invoice.number}-P{generate_code('', 4)}"
        url = wompi.checkout_url(
            public_key=settings.WOMPI_PLATFORM_PUBLIC_KEY,
            reference=reference,
            amount_in_cents=wompi.amount_in_cents(invoice.total),
            currency=invoice.currency,
            integrity_secret=settings.WOMPI_PLATFORM_INTEGRITY_SECRET,
            redirect_url=return_url,
            customer_name=invoice.organization.legal_name or invoice.organization.name,
        )
        return {"checkout_url": url, "payload": {"checkout_reference": reference}}

    def fetch_status(self, invoice) -> dict:
        payload = invoice.payment_payload or {}
        reference = payload.get("checkout_reference") or payload.get("reference")
        if not reference:
            return {"status": "created", "reference": "", "method": "", "message": ""}
        try:
            transaction = wompi.pick_transaction(self._client().find_transactions(reference))
        except ProviderError as exc:
            return {"status": "pending", "reference": "", "method": "", "message": str(exc)}
        if transaction is None:
            return {"status": "created", "reference": "", "method": "", "message": ""}
        return _result(transaction, reference)

    def card_setup(self) -> dict:
        """Public data for the browser: where to tokenize the card and the two documents to accept."""
        merchant = self._client().merchant()
        acceptance = merchant.get("presigned_acceptance") or {}
        personal = merchant.get("presigned_personal_data_auth") or {}
        return {
            "public_key": settings.WOMPI_PLATFORM_PUBLIC_KEY,
            "environment": settings.WOMPI_PLATFORM_ENV,
            "tokenize_url": f"{wompi.API_URLS.get(settings.WOMPI_PLATFORM_ENV, wompi.API_URLS['sandbox'])}"
            "/tokens/cards",
            "acceptance_token": acceptance.get("acceptance_token", ""),
            "acceptance_permalink": acceptance.get("permalink", ""),
            "personal_auth_token": personal.get("acceptance_token", ""),
            "personal_auth_permalink": personal.get("permalink", ""),
        }

    def create_payment_source(
        self, *, token: str, acceptance_token: str, accept_personal_auth: str = "", customer_email: str
    ) -> dict:
        if not token or not acceptance_token:
            raise ProviderError("Faltan el token de la tarjeta y el token de aceptación de Wompi")
        body = {
            "type": "CARD",
            "token": token,
            "customer_email": customer_email,
            "acceptance_token": acceptance_token,
        }
        if accept_personal_auth:
            body["accept_personal_auth"] = accept_personal_auth
        source = self._client().create_payment_source(body)
        public = source.get("public_data") or {}
        return {
            "type": "card",
            "wompi_payment_source_id": source.get("id"),
            "status": source.get("status", ""),
            "brand": public.get("brand") or public.get("type") or "CARD",
            "last4": public.get("last_four", ""),
            "exp_month": public.get("exp_month"),
            "exp_year": public.get("exp_year"),
            "holder": public.get("card_holder", ""),
            "customer_email": customer_email,
            "simulated": False,
        }


register_provider("saas_billing", "simulated", SimulatedSaasBillingProvider)
register_provider("saas_billing", "real", WompiSaasBillingProvider)
