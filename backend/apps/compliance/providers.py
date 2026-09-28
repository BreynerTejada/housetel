"""Integration providers of the Colombian legal reports (spec §1.2: every integration is real or simulated).

- `einvoice` (DIAN electronic invoicing): `simulated` validates locally (deterministic CUFE/CUDE, QR,
  accepted);
  `real` = Factus API v2 (OAuth2 password grant, `POST /v2/bills/validate`, `POST /v2/credit-notes/validate`).
- `sire` (Migración Colombia): there is no public API. `real` = the file is uploaded by hand in the SIRE
  portal
  (marking it "submitted" records that); `simulated` also returns an acknowledgement code.
- `tra` (MinCIT, Tarjeta de Registro de Alojamiento): `real` = the PMS integration of the TRA service
  (token of the RNT, main guest and companions); `simulated` = a local TRA number.

Providers never write to the database; the services (`apps.compliance.services.*`) apply what they return:

- e-invoicing: `issue(invoice, *, supplier) -> {"status": accepted|issued|rejected|error, "number", "cufe",
  "qr_data", "provider_ref", "message", "response", "xml"}` and `refresh(invoice)` (same shape) for documents
  still waiting for the DIAN.
- SIRE: `submit(report) -> {"status": submitted|acknowledged, "ack_code", "message"}`.
- TRA: `register(payload, *, parent_number="") -> {"status": registered|error, "tra_number", "message",
  "response"}`.

What was verified in each service's documentation (and what is assumed) is in
docs/integration-notes/C7-compliance.md.
"""

from __future__ import annotations

import base64
import logging
from decimal import Decimal

import httpx
from django.core.cache import cache

from apps.compliance.codes import divipola_code
from apps.compliance.services.builder import tax_totals
from apps.compliance.services.cufe import compute_cufe, qr_payload
from apps.core.codes import generate_code
from apps.core.integrations import BaseProvider, register_provider

logger = logging.getLogger("housetel.compliance")

TIMEOUT = httpx.Timeout(20.0, connect=8.0)
ERROR = "error"


def _field(
    name,
    label_es,
    label_en,
    type_,
    *,
    secret=False,
    required=True,
    help_es="",
    help_en="",
    options=None,
    default=None,
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
    if default is not None:
        field["default"] = default
    return field


def _failure(message: str, response: dict | None = None) -> dict:
    return {
        "status": ERROR,
        "number": "",
        "cufe": "",
        "qr_data": "",
        "provider_ref": "",
        "message": message,
        "response": response or {},
        "xml": None,
    }


# ------------------------------------------------------------------------------------------ e-invoicing


class EInvoiceProvider(BaseProvider):
    kind = "einvoice"
    code = ""  # stored in Invoice.provider

    def issue(self, invoice, *, supplier: dict) -> dict:
        raise NotImplementedError

    def refresh(self, invoice) -> dict:
        raise NotImplementedError

    def fetch_xml(self, invoice) -> bytes | None:
        """The provider's official (signed) XML, when it offers one."""
        return None


class SimulatedEInvoiceProvider(EInvoiceProvider):
    """Local DIAN: the CUFE (CUDE for credit notes) is the SHA-384 of the technical annex's concatenation, so
    it
    is deterministic, and every document is accepted at once."""

    mode = "simulated"
    code = "simulated"
    label = "DIAN simulada (sin validez fiscal)"
    CONFIG_FIELDS: list[dict] = []

    def issue(self, invoice, *, supplier: dict) -> dict:
        from apps.compliance.services.documents import issue_time

        taxes = tax_totals(invoice.lines)
        customer_id = (invoice.customer or {}).get("document_number", "")
        key = (invoice.resolution.technical_key if invoice.resolution_id else "") or "housetel-simulado"
        moment = issue_time(invoice)
        cufe = compute_cufe(
            number=invoice.full_number,
            issue_date=invoice.issue_date,
            issue_time=moment,
            subtotal=invoice.subtotal,
            iva=taxes["01"],
            inc=taxes["04"],
            total=invoice.total,
            supplier_nit=supplier["nit"],
            customer_id=customer_id,
            key=key,
            environment=invoice.environment,
        )
        qr = qr_payload(
            number=invoice.full_number,
            issue_date=invoice.issue_date,
            issue_time=moment,
            supplier_nit=supplier["nit"],
            customer_id=customer_id,
            subtotal=invoice.subtotal,
            iva=taxes["01"],
            other_taxes=invoice.tax_total - taxes["01"],
            total=invoice.total,
            cufe=cufe,
            environment=invoice.environment,
        )
        return {
            "status": "accepted",
            "number": invoice.full_number,
            "cufe": cufe,
            "qr_data": qr,
            "provider_ref": f"SIM-{invoice.full_number}",
            "message": "Validada por la DIAN simulada",
            "response": {"simulated": True, "is_validated": True},
            "xml": None,
        }

    def refresh(self, invoice) -> dict:
        return {
            "status": "accepted",
            "number": invoice.full_number,
            "cufe": invoice.cufe,
            "qr_data": invoice.qr_data,
            "provider_ref": invoice.provider_ref,
            "message": "Validada por la DIAN simulada",
            "response": invoice.provider_response or {"simulated": True},
            "xml": None,
        }


# Payment.method → DIAN payment means code (Factus table "Métodos de pago").
PAYMENT_MEANS = {
    "cash": "10",
    "card_terminal": "48",
    "wompi_card": "48",
    "bank_transfer": "47",
    "wompi_pse": "47",
    "wompi_nequi": "47",
}
FACTUS_HOSTS = {"sandbox": "https://api-sandbox.factus.com.co", "production": "https://api.factus.com.co"}


class FactusProvider(EInvoiceProvider):
    """Factus API v2 (developers.factus.com.co): the technological provider signs the XML, sends it to the
    DIAN and
    returns the official number, CUFE/CUDE and the DIAN QR link.

    Idempotent retries: `reference_code` = "HTL" + the invoice id, and Factus returns the existing document
    when the
    same reference arrives again."""

    mode = "real"
    code = "factus"
    label = "Factus (proveedor tecnológico autorizado por la DIAN)"
    CONFIG_FIELDS = [
        _field(
            "environment",
            "Ambiente",
            "Environment",
            "select",
            default="sandbox",
            options=[
                {"value": "sandbox", "label_es": "Pruebas (sandbox)", "label_en": "Sandbox"},
                {"value": "production", "label_es": "Producción", "label_en": "Production"},
            ],
        ),
        _field("client_id", "Client ID", "Client ID", "text"),
        _field("client_secret", "Client secret", "Client secret", "password", secret=True),
        _field("username", "Usuario (correo)", "User (email)", "text"),
        _field("password", "Contraseña", "Password", "password", secret=True),
        _field(
            "numbering_range_id",
            "ID del rango de facturas en Factus",
            "Factus invoice range ID",
            "number",
            required=False,
            help_es="Si se deja vacío se usa el de la resolución activa (o el único rango activo).",
            help_en="Empty: the active resolution's range (or the only active range).",
        ),
        _field(
            "credit_note_range_id",
            "ID del rango de notas crédito en Factus",
            "Factus credit note range ID",
            "number",
            required=False,
        ),
        _field(
            "send_email",
            "Factus envía la factura al correo del cliente",
            "Factus emails the invoice to the customer",
            "boolean",
            required=False,
            default=False,
        ),
    ]
    REQUIRED = ("client_id", "client_secret", "username", "password")

    # --- HTTP

    @property
    def base_url(self) -> str:
        return FACTUS_HOSTS.get(self.config.get("environment") or "sandbox", FACTUS_HOSTS["sandbox"])

    def _credentials(self) -> dict:
        values = {**{k: self.config.get(k, "") for k in ("client_id", "username")}, **self.secrets}
        return {key: str(values.get(key) or "") for key in self.REQUIRED}

    def _missing(self) -> list[str]:
        return [key for key, value in self._credentials().items() if not value]

    def _token_key(self) -> str:
        return f"compliance:factus:{self.setting.pk}:{self.config.get('environment') or 'sandbox'}:token"

    def _token(self, *, fresh: bool = False) -> str:
        key = self._token_key()
        if not fresh:
            token = cache.get(key)
            if token:
                return token
        response = httpx.post(
            f"{self.base_url}/oauth/token",
            data={"grant_type": "password", **self._credentials()},
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        body = response.json()
        token = body["access_token"]
        cache.set(key, token, max(int(body.get("expires_in") or 600) - 60, 60))
        return token

    def _call(self, method: str, path: str, **kwargs) -> httpx.Response:
        for attempt in (1, 2):
            headers = {
                "Authorization": f"Bearer {self._token(fresh=attempt == 2)}",
                "Accept": "application/json",
            }
            response = httpx.request(
                method, f"{self.base_url}{path}", headers=headers, timeout=TIMEOUT, **kwargs
            )
            if response.status_code != 401:
                return response
        return response

    # --- payloads

    def _range_id(self, invoice, config_key: str):
        value = self.config.get(config_key) or (
            invoice.resolution.provider_range_id if invoice.resolution_id else ""
        )
        return int(value) if str(value or "").strip().isdigit() else None

    @staticmethod
    def customer_payload(customer: dict) -> dict:
        company = customer.get("legal_organization") == "company"
        country = (customer.get("country") or "CO").upper()
        data = {
            "identification_document_code": customer.get("dian_document_code") or "13",
            "identification": customer.get("document_number", ""),
        }
        if customer.get("dv"):
            data["dv"] = customer["dv"]
        data["legal_organization_code"] = "1" if company else "2"
        data["tribute_code"] = "ZZ"
        data["company" if company else "names"] = customer.get("name", "")
        for key in ("address", "email", "phone"):
            if customer.get(key):
                data[key] = customer[key]
        data["country_code"] = country
        municipality = divipola_code(customer.get("city", "")) if country == "CO" else ""
        if municipality:
            data["municipality_code"] = municipality
        return data

    @staticmethod
    def item_payload(line: dict) -> dict:
        status = line.get("tax_status", "excluded")
        return {
            "code_reference": line["code"],
            "name": line["description"][:300],
            "quantity": f"{Decimal(str(line['quantity'])):.2f}",
            "discount_rate": "0.00",
            "price": f"{Decimal(line['unit_price']):.2f}",
            "unit_measure_code": "94",
            "standard_code": "999",
            "taxes": [
                {
                    "code": line.get("tax_code") or "01",
                    "rate": line["tax_rate"] if status == "taxed" else "0.00",
                    "is_excluded": status == "excluded",
                }
            ],
        }

    def _items_and_allowances(self, invoice) -> tuple[list, list]:
        items, allowances = [], []
        positive_base = sum(
            (Decimal(line["net"]) for line in invoice.lines if Decimal(line["net"]) > 0), Decimal("0")
        )
        for line in invoice.lines:
            if Decimal(line["net"]) < 0:  # discounts / negative adjustments go as document allowances
                allowances.append(
                    {
                        "concept_type": str(self.config.get("discount_concept_code") or "09"),
                        "is_surcharge": False,
                        "reason": line["description"][:200],
                        "base_amount": f"{positive_base:.2f}",
                        "amount": f"{abs(Decimal(line['net'])):.2f}",
                    }
                )
            else:
                items.append(self.item_payload(line))
        return items, allowances

    @staticmethod
    def _payment_means(invoice) -> str:
        from apps.finance.models import Payment

        payment = (
            Payment.objects.filter(folio=invoice.folio_id, status=Payment.Status.APPROVED)
            .order_by("-amount", "created_at")
            .first()
        )
        return PAYMENT_MEANS.get(payment.method, "ZZZ") if payment is not None else "ZZZ"

    def _common(self, invoice) -> dict:
        items, allowances = self._items_and_allowances(invoice)
        data = {
            "reference_code": f"HTL{invoice.pk.hex}",
            "payment_details": [
                {
                    "payment_form": "1",
                    "payment_method_code": self._payment_means(invoice),
                    "amount": f"{Decimal(invoice.total):.2f}",
                }
            ],
            "customer": self.customer_payload(invoice.customer or {}),
            "items": items,
        }
        if allowances:
            data["allowance_charges"] = allowances
        return data

    def bill_payload(self, invoice) -> dict:
        data = {"reference_code": None, "document": "01", "operation_type": "10"}
        range_id = self._range_id(invoice, "numbering_range_id")
        if range_id is not None:
            data["numbering_range_id"] = range_id
        observation = " ".join(x for x in (invoice.exempt_note,) if x)
        if observation:
            data["observation"] = observation[:500]
        data["send_email"] = bool(self.config.get("send_email", False))
        data.update(self._common(invoice))
        return data

    def credit_note_payload(self, note) -> dict:
        original = note.related_invoice
        data = {
            "reference_code": None,
            "correction_concept_code": "2",  # anulación de factura electrónica
            "customization_id": "20",  # nota crédito que referencia una factura electrónica
            "bill_number": original.full_number if original else "",
        }
        range_id = self._range_id(note, "credit_note_range_id")
        if range_id is not None:
            data["numbering_range_id"] = range_id
        data["observation"] = (note.reason or "Anulación de factura electrónica")[:500]
        data.update(self._common(note))
        return data

    # --- results

    @staticmethod
    def _messages(body) -> str:
        if not isinstance(body, dict):
            return str(body)[:500]
        parts = [str(body.get("message") or "")]
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        errors = data.get("errors") or body.get("errors") or {}
        if isinstance(errors, dict):
            for field, detail in errors.items():
                text = "; ".join(map(str, detail)) if isinstance(detail, list) else str(detail)
                parts.append(f"{field}: {text}")
        elif isinstance(errors, list):
            parts.extend(map(str, errors))
        return " · ".join(p for p in parts if p)[:2000]

    def _result(self, response: httpx.Response) -> dict:
        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text[:1000]}
        if response.status_code in (200, 201) and isinstance(body, dict):
            data = body.get("data") if isinstance(body.get("data"), dict) else {}
            document = data.get("bill") or data.get("credit_note") or data
            links = document.get("links") or {}
            number = str(document.get("number") or "")
            validated = bool(document.get("is_validated"))
            return {
                "status": "accepted" if validated else "issued",
                "number": number,
                "cufe": str(document.get("cufe") or document.get("cude") or ""),
                "qr_data": str(links.get("qr") or document.get("qr") or ""),
                "provider_ref": number,
                "message": str(body.get("message") or ""),
                "response": body,
                "xml": None,
            }
        message = self._messages(body) or f"Factus respondió {response.status_code}"
        if response.status_code in (400, 422):
            return {**_failure(message, body if isinstance(body, dict) else {}), "status": "rejected"}
        if response.status_code == 409:
            message = f"Factus tiene un documento pendiente por enviar a la DIAN: {message}"
        return _failure(message, body if isinstance(body, dict) else {})

    def issue(self, invoice, *, supplier: dict) -> dict:
        if missing := self._missing():
            return _failure(f"Faltan credenciales de Factus: {', '.join(missing)}")
        credit = invoice.kind == "credit_note"
        payload = self.credit_note_payload(invoice) if credit else self.bill_payload(invoice)
        payload["reference_code"] = f"HTL{invoice.pk.hex}"
        try:
            response = self._call(
                "POST", "/v2/credit-notes/validate" if credit else "/v2/bills/validate", json=payload
            )
        except httpx.HTTPError as exc:
            logger.warning("Factus request failed: %s", exc)
            return _failure(f"No se pudo conectar con Factus: {exc}")
        return self._result(response)

    def refresh(self, invoice) -> dict:
        if missing := self._missing():
            return _failure(f"Faltan credenciales de Factus: {', '.join(missing)}")
        path = "credit-notes" if invoice.kind == "credit_note" else "bills"
        try:
            response = self._call("GET", f"/v2/{path}/{invoice.full_number}")
        except httpx.HTTPError as exc:
            return _failure(f"No se pudo conectar con Factus: {exc}")
        return self._result(response)

    def fetch_xml(self, invoice) -> bytes | None:
        """The signed XML Factus sent to the DIAN (None if it cannot be downloaded)."""
        if self._missing() or not invoice.full_number:
            return None
        path = "credit-notes" if invoice.kind == "credit_note" else "bills"
        try:
            response = self._call("GET", f"/v2/{path}/{invoice.full_number}/download-xml")
            if response.status_code != 200:
                return None
            body = response.json()
            encoded = (body.get("data") or {}).get("xml_base_64_encoded") or body.get("xml_base_64_encoded")
            return base64.b64decode(encoded) if encoded else None
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            return None

    def test_connection(self) -> tuple[bool, str]:
        if missing := self._missing():
            return False, f"Faltan credenciales de Factus: {', '.join(missing)}"
        try:
            response = self._call("GET", "/v2/numbering-ranges", params={"filter[is_active]": 1})
        except httpx.HTTPError as exc:
            return False, f"No se pudo conectar con Factus: {exc}"
        if response.status_code != 200:
            return False, f"Factus respondió {response.status_code}"
        body = response.json()
        ranges = body.get("data") if isinstance(body, dict) else None
        if isinstance(ranges, dict):
            ranges = ranges.get("data") or []
        prefixes = ", ".join(sorted({str(r.get("prefix", "")) for r in ranges or [] if isinstance(r, dict)}))
        return True, f"Conectado a Factus ({len(ranges or [])} rangos activos: {prefixes or 'ninguno'})"


# ------------------------------------------------------------------------------------------------ SIRE


class SireProvider(BaseProvider):
    kind = "sire"

    def submit(self, report) -> dict:
        raise NotImplementedError


class SimulatedSireProvider(SireProvider):
    mode = "simulated"
    label = "Portal SIRE simulado (genera un acuse local)"
    CONFIG_FIELDS: list[dict] = []

    def submit(self, report) -> dict:
        return {
            "status": "acknowledged",
            "ack_code": f"SIRE-{generate_code('', 8)}",
            "message": "Acuse simulado",
        }


class PortalSireProvider(SireProvider):
    """Migración Colombia has no public API for SIRE: the hotel downloads the TXT and uploads it in the portal
    (apps.migracioncolombia.gov.co/sire), then marks the report as submitted (optionally with the receipt)."""

    mode = "real"
    label = "Portal SIRE de Migración Colombia (carga manual del archivo)"
    CONFIG_FIELDS: list[dict] = []

    def submit(self, report) -> dict:
        return {
            "status": "submitted",
            "ack_code": "",
            "message": "Archivo marcado como cargado en el portal SIRE",
        }

    def test_connection(self) -> tuple[bool, str]:
        return (
            True,
            "SIRE no tiene API pública: descarga el archivo y súbelo en el portal de Migración Colombia",
        )


# ------------------------------------------------------------------------------------------------- TRA


class TraProvider(BaseProvider):
    kind = "tra"

    def register(self, payload: dict, *, parent_number: str = "") -> dict:
        raise NotImplementedError


class SimulatedTraProvider(TraProvider):
    mode = "simulated"
    label = "TRA simulada (número local)"
    CONFIG_FIELDS: list[dict] = []

    def register(self, payload: dict, *, parent_number: str = "") -> dict:
        number = f"TRA-{generate_code('', 8)}"
        return {
            "status": "registered",
            "tra_number": number,
            "message": "Registro simulado",
            "response": {"simulated": True, "code": number},
        }


class MincitTraProvider(TraProvider):
    """PMS integration of the TRA (MinCIT, "Grupo 1: prestadores con PMS"): the main guest is posted to
    `<base_url>/one/` and each companion to `<base_url>/two/` with `padre` = the main guest's code, both with
    the
    header `Authorization: token <token del RNT>`. Paths and base URL are configurable (see the integration
    notes: the official manual could not be downloaded when this was written)."""

    mode = "real"
    label = "TRA de MinCIT (integración para PMS)"
    DEFAULT_BASE_URL = "https://pms.mincit.gov.co"
    CONFIG_FIELDS = [
        _field(
            "base_url",
            "URL del servicio TRA",
            "TRA service URL",
            "url",
            required=False,
            default=DEFAULT_BASE_URL,
        ),
        _field(
            "token",
            "Token PMS del RNT",
            "RNT PMS token",
            "password",
            secret=True,
            help_es="Se solicita en https://pms.mincit.gov.co/token/ con el RNT del establecimiento.",
            help_en="Request it at https://pms.mincit.gov.co/token/ with the establishment's RNT.",
        ),
        _field(
            "establishment_id",
            "RNT del establecimiento",
            "Establishment RNT",
            "text",
            required=False,
            help_es="Vacío: el RNT del perfil del hotel.",
            help_en="Empty: the hotel profile's RNT.",
        ),
        _field(
            "main_path",
            "Ruta del huésped principal",
            "Main guest path",
            "text",
            required=False,
            default="/one/",
        ),
        _field(
            "companion_path",
            "Ruta de acompañantes",
            "Companions path",
            "text",
            required=False,
            default="/two/",
        ),
    ]

    def _url(self, companion: bool) -> str:
        base = (self.config.get("base_url") or self.DEFAULT_BASE_URL).rstrip("/")
        path = self.config.get("companion_path" if companion else "main_path") or (
            "/two/" if companion else "/one/"
        )
        return f"{base}/{path.lstrip('/')}"

    def register(self, payload: dict, *, parent_number: str = "") -> dict:
        token = self.secrets.get("token")
        if not token:
            return {
                "status": ERROR,
                "tra_number": "",
                "message": "Falta el token PMS de la TRA",
                "response": {},
            }
        body = {**payload, "padre": parent_number} if parent_number else dict(payload)
        try:
            response = httpx.post(
                self._url(bool(parent_number)),
                json=body,
                headers={"Authorization": f"token {token}", "Accept": "application/json"},
                timeout=TIMEOUT,
            )
        except httpx.HTTPError as exc:
            return {
                "status": ERROR,
                "tra_number": "",
                "message": f"No se pudo conectar con la TRA: {exc}",
                "response": {},
            }
        try:
            data = response.json()
        except ValueError:
            data = {"raw": response.text[:1000]}
        if response.status_code in (200, 201) and isinstance(data, dict):
            number = data.get("code") or data.get("id") or data.get("numero") or data.get("tra")
            if number not in (None, ""):
                return {
                    "status": "registered",
                    "tra_number": str(number),
                    "message": str(data.get("message", "")),
                    "response": data,
                }
        detail = (
            data.get("detail") or data.get("message") or data.get("error") if isinstance(data, dict) else data
        )
        message = f"La TRA respondió {response.status_code}: {detail or 'sin detalle'}"
        return {
            "status": ERROR,
            "tra_number": "",
            "message": message[:2000],
            "response": data if isinstance(data, dict) else {"raw": str(data)},
        }

    def test_connection(self) -> tuple[bool, str]:
        if not self.secrets.get("token"):
            return False, "Falta el token PMS de la TRA (solicítalo en https://pms.mincit.gov.co/token/)"
        return True, f"Token configurado; los registros se envían a {self._url(False)}"


register_provider("einvoice", "simulated", SimulatedEInvoiceProvider)
register_provider("einvoice", "real", FactusProvider)
register_provider("sire", "simulated", SimulatedSireProvider)
register_provider("sire", "real", PortalSireProvider)
register_provider("tra", "simulated", SimulatedTraProvider)
register_provider("tra", "real", MincitTraProvider)
