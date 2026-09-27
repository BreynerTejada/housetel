"""Wompi (Colombia) helpers: checkout web, integrity signature, event checksum and a small HTTP client.

Verified against docs.wompi.co and the official API spec (SwaggerHub `waybox/wompi` 1.2.0), see
docs/integration-notes/B4-finance.md:

- Checkout web: `GET https://checkout.wompi.co/p/` with `public-key`, `currency`, `amount-in-cents`,
  `reference`, `signature:integrity` and optionally `redirect-url` (Wompi appends `?id=<transaction id>`),
  `expiration-time` (ISO 8601 UTC) and `customer-data:*`.
- Integrity signature: SHA256 hex of `reference + amount_in_cents + currency [+ expiration_time] + secret`.
- Events (`transaction.updated`): checksum = SHA256 of the values of `signature.properties` (paths inside
  `data`) + `timestamp` + events secret; it arrives in `signature.checksum` and in the `X-Event-Checksum`
  header. The merchant must answer HTTP 200 (Wompi retries 3 times in 24 h otherwise).
- API: sandbox `https://sandbox.wompi.co/v1`, production `https://production.wompi.co/v1`.
  `GET /transactions/{id}` and `GET /transactions?reference=` require `Authorization: Bearer <private key>`;
  `POST /transactions/{id}/void` `{amount_in_cents}` voids APPROVED card transactions only;
  `POST /refunds` (Refunds API V2, private key) `{transaction_id, amount_in_cents, reason?, reference?}`
  refunds an APPROVED transaction totally or partially (docs label it "Sandbox"; production availability and
  the methods it covers are not documented, so callers fall back to a manual transfer).
  `GET /merchants/{public_key}` is public.

Pure functions live here so the SaaS billing provider (C11) can reuse them with platform credentials.
"""

from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal
from urllib.parse import urlencode

import httpx

from apps.core.money import D
from apps.finance.errors import ProviderError

CHECKOUT_URL = "https://checkout.wompi.co/p/"
API_URLS = {"sandbox": "https://sandbox.wompi.co/v1", "production": "https://production.wompi.co/v1"}
TIMEOUT_SECONDS = 10.0

# Wompi transaction status → PaymentIntent/provider status used by apps.finance.
STATUS_MAP = {
    "APPROVED": "approved",
    "DECLINED": "declined",
    "VOIDED": "voided",
    "ERROR": "error",
    "PENDING": "pending",
}
# Wompi payment_method_type → Payment.Method.
METHOD_MAP = {"CARD": "wompi_card", "PSE": "wompi_pse", "NEQUI": "wompi_nequi"}


def amount_in_cents(amount) -> int:
    """Wompi amounts are integers in cents (COP 150.000 → 15000000)."""
    return int((D(amount) * 100).to_integral_value())


def integrity_signature(reference, amount_cents, currency, secret, expiration_time=None) -> str:
    """`signature:integrity` of a checkout: SHA256 hex of reference + cents + currency [+ expiry] + secret."""
    raw = f"{reference}{int(amount_cents)}{currency}{expiration_time or ''}{secret}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _property_value(data: dict, path: str) -> str:
    value = data
    for key in path.split("."):
        if not isinstance(value, dict):
            raise KeyError(path)
        value = value[key]
    return "" if value is None else str(value)


def event_checksum(event: dict, secret: str) -> str:
    """Lowercase SHA256 hex of the signed property values + timestamp + events secret."""
    signature = event.get("signature")
    if not isinstance(signature, dict):
        raise ValueError("signature missing")
    properties = signature.get("properties")
    if not isinstance(properties, list):
        raise ValueError("signature.properties missing")
    timestamp = event.get("timestamp")
    if timestamp in (None, ""):
        raise ValueError("timestamp missing")
    data = event.get("data") or {}
    raw = "".join(_property_value(data, path) for path in properties) + str(timestamp) + secret
    return hashlib.sha256(raw.encode()).hexdigest()


def verify_event(event: dict, secret: str, header_checksum: str | None = None) -> bool:
    """True when the event's checksum (header `X-Event-Checksum` if sent, else `signature.checksum`)
    matches. Comparison is constant-time and case-insensitive; malformed events never verify."""
    if not secret or not isinstance(event, dict):
        return False
    signature = event.get("signature")
    body_checksum = signature.get("checksum") if isinstance(signature, dict) else None
    received = str(header_checksum or body_checksum or "").strip().lower()
    if not received:
        return False
    try:
        expected = event_checksum(event, secret)
    except (KeyError, TypeError, ValueError):
        return False
    return hmac.compare_digest(expected.encode(), received.encode())  # bytes: any input, constant time


def checkout_url(
    *,
    public_key,
    reference,
    amount_in_cents,
    currency,
    integrity_secret,
    redirect_url="",
    expiration_time="",
    customer_email="",
    customer_name="",
) -> str:
    """Web checkout URL (redirect). The expiration time, when given, is part of the signature."""
    params = {
        "public-key": public_key,
        "currency": currency,
        "amount-in-cents": str(int(amount_in_cents)),
        "reference": reference,
        "signature:integrity": integrity_signature(
            reference, amount_in_cents, currency, integrity_secret, expiration_time or None
        ),
    }
    if redirect_url:
        params["redirect-url"] = redirect_url
    if expiration_time:
        params["expiration-time"] = expiration_time
    if customer_email:
        params["customer-data:email"] = customer_email
    if customer_name:
        params["customer-data:full-name"] = customer_name
    return f"{CHECKOUT_URL}?{urlencode(params)}"


def pick_transaction(transactions: list[dict]) -> dict | None:
    """The transaction that decides a reference: an approved one, else a pending one, else the latest."""
    if not transactions:
        return None
    for status in ("APPROVED", "PENDING"):
        for transaction in transactions:
            if transaction.get("status") == status:
                return transaction
    return max(transactions, key=lambda t: str(t.get("created_at") or ""))


class WompiClient:
    """Minimal Wompi API client (httpx). Every failure raises ProviderError."""

    def __init__(self, *, environment="sandbox", public_key="", private_key="", timeout=TIMEOUT_SECONDS):
        self.environment = environment if environment in API_URLS else "sandbox"
        self.base_url = API_URLS[self.environment]
        self.public_key = public_key
        self.private_key = private_key
        self.timeout = timeout

    def _request(self, method: str, path: str, *, private: bool = True, **kwargs) -> dict:
        headers = {"Accept": "application/json"}
        if private:
            headers["Authorization"] = f"Bearer {self.private_key}"
        try:
            response = httpx.request(
                method, f"{self.base_url}{path}", headers=headers, timeout=self.timeout, **kwargs
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"No se pudo conectar con Wompi: {exc.__class__.__name__}") from exc
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code >= 400:
            error = payload.get("error") if isinstance(payload, dict) else None
            detail = error.get("type") if isinstance(error, dict) else ""
            raise ProviderError(
                f"Wompi respondió {response.status_code} {detail}".strip(),
                status=response.status_code,
                payload=payload if isinstance(payload, dict) else {},
            )
        if not isinstance(payload, dict):
            raise ProviderError("Respuesta inesperada de Wompi", status=response.status_code)
        return payload

    def get_transaction(self, transaction_id: str) -> dict:
        return self._request("GET", f"/transactions/{transaction_id}").get("data") or {}

    def find_transactions(self, reference: str) -> list[dict]:
        data = self._request("GET", "/transactions", params={"reference": reference}).get("data") or []
        return data if isinstance(data, list) else [data]

    def void_transaction(self, transaction_id: str, amount_in_cents: int | None = None) -> dict:
        body = {"amount_in_cents": int(amount_in_cents)} if amount_in_cents is not None else {}
        return self._request("POST", f"/transactions/{transaction_id}/void", json=body).get("data") or {}

    def create_refund(
        self, transaction_id: str, amount_in_cents: int, *, reason: str = "", reference: str = ""
    ) -> dict:
        """Refunds API V2 (`POST /refunds`, private key): total or partial refund of an APPROVED
        transaction. Answers 201 with `status` APPROVED | DECLINED | ERROR | CANCELLED. In sandbox the result
        is chosen with `test_scenario`; Housetel asks for "approved" there."""
        body: dict = {"transaction_id": transaction_id, "amount_in_cents": int(amount_in_cents)}
        if reason:
            body["reason"] = reason[:255]
        if reference:
            body["reference"] = reference[:255]
        if self.environment == "sandbox":
            body["test_scenario"] = "approved"
        return self._request("POST", "/refunds", json=body).get("data") or {}

    def merchant(self) -> dict:
        return self._request("GET", f"/merchants/{self.public_key}", private=False).get("data") or {}


def transaction_amount(transaction: dict) -> Decimal | None:
    cents = transaction.get("amount_in_cents")
    return (Decimal(int(cents)) / 100) if cents is not None else None
