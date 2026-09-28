"""CUFE / CUDE and QR content of a DIAN electronic invoice (Anexo técnico de factura electrónica v1.9).

CUFE = SHA-384( NumFac + FecFac + HorFac + ValFac + "01" + ValIva + "04" + ValInc + "03" + ValIca + ValTot
                + NitOFE + NumAdq + ClTec + TipoAmbiente )
Values with two decimals and a dot; NIT without check digit; TipoAmbiente 1 = production, 2 = test. The credit
note CUDE uses the same concatenation with the software PIN instead of the technical key. In simulated mode
this is the whole "validation"; in real mode the provider returns the official CUFE.
"""

import hashlib
import re
from datetime import date
from decimal import Decimal

ENVIRONMENT_CODES = {"production": "1", "test": "2"}
QR_URLS = {
    "production": "https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey=",
    "test": "https://catalogo-vpfe-hab.dian.gov.co/document/searchqr?documentkey=",
}


def money(value) -> str:
    return f"{Decimal(value or 0):.2f}"


def nit_without_dv(value: str) -> str:
    return re.sub(r"\D", "", (value or "").split("-")[0])


def compute_cufe(
    *,
    number: str,
    issue_date: date,
    issue_time: str,
    subtotal,
    iva,
    total,
    supplier_nit: str,
    customer_id: str,
    key: str,
    environment: str,
    inc=Decimal("0"),
    ica=Decimal("0"),
) -> str:
    raw = (
        f"{number}{issue_date:%Y-%m-%d}{issue_time}{money(subtotal)}"
        f"01{money(iva)}04{money(inc)}03{money(ica)}{money(total)}"
        f"{nit_without_dv(supplier_nit)}{customer_id}{key}{ENVIRONMENT_CODES[environment]}"
    )
    return hashlib.sha384(raw.encode()).hexdigest()


def validation_url(cufe: str, environment: str) -> str:
    return f"{QR_URLS[environment]}{cufe}"


def qr_payload(
    *,
    number: str,
    issue_date: date,
    issue_time: str,
    supplier_nit: str,
    customer_id: str,
    subtotal,
    iva,
    other_taxes,
    total,
    cufe: str,
    environment: str,
) -> str:
    return "\n".join(
        [
            f"NumFac={number}",
            f"FecFac={issue_date:%Y-%m-%d}",
            f"HorFac={issue_time}",
            f"NitFac={nit_without_dv(supplier_nit)}",
            f"DocAdq={customer_id}",
            f"ValFac={money(subtotal)}",
            f"ValIva={money(iva)}",
            f"ValOtroIm={money(other_taxes)}",
            f"ValTolFac={money(total)}",
            f"CUFE={cufe}",
            f"QRCode={validation_url(cufe, environment)}",
        ]
    )
