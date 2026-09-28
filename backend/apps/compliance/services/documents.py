"""Graphic representation (PDF) and UBL 2.1 XML of invoices and credit notes.

- PDF (reportlab, A4): issuer and document box, DIAN numbering authorization, customer and stay, lines, taxes,
  totals (with the amount in words), the IVA exemption note, the CUFE/CUDE with its QR and, in simulated mode,
  a "sin validez fiscal" watermark on every page. Files are stored by `apps.compliance.services.invoices`.
- XML: UBL 2.1 with the structure of the DIAN's technical annex (supplier/customer parties, tax totals,
  monetary
  totals, lines; credit notes with BillingReference and DiscrepancyResponse). It is not signed: in real mode
  the technological provider signs and sends the official XML (and we keep the one it returns when it does).
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from django.utils import timezone
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.compliance.models import ComplianceSettings, Invoice
from apps.compliance.services.config import supplier_info
from apps.compliance.services.cufe import ENVIRONMENT_CODES, validation_url

INK = colors.HexColor("#1F1C19")
MUTED = colors.HexColor("#6E675E")
RULE = colors.HexColor("#E7E2DA")
SURFACE = colors.HexColor("#F3F0EB")
ACCENT = colors.HexColor("#B4583B")
ACCENT_INK = colors.HexColor("#8A3F28")
ACCENT_SOFT = colors.HexColor("#F5E7E0")
WATERMARK = colors.Color(0.706, 0.345, 0.231, alpha=0.07)

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 16 * mm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

TITLES = {
    Invoice.Kind.INVOICE: "FACTURA ELECTRÓNICA DE VENTA",
    Invoice.Kind.CREDIT_NOTE: "NOTA CRÉDITO ELECTRÓNICA",
}
DOCUMENT_LABELS = {
    "CC": "C.C.",
    "CE": "C.E.",
    "TI": "T.I.",
    "NIT": "NIT",
    "PA": "Pasaporte",
    "PEP": "PEP",
    "PPT": "PPT",
    "DNI": "Doc. extranjero",
    "OTHER": "Documento",
}
TAX_LABELS = {"exempt": "Exento", "excluded": "Excluido"}
PROVIDER_LABELS = {"simulated": "Simulado (Housetel)", "factus": "Factus"}
ENVIRONMENT_LABELS = {"test": "Ambiente de pruebas (habilitación)", "production": "Ambiente de producción"}
UBL = {
    "invoice": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "credit_note": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}
ET.register_namespace("cac", UBL["cac"])
ET.register_namespace("cbc", UBL["cbc"])

# ---------------------------------------------------------------------------------------------- amounts


def money(value, currency: str = "COP") -> str:
    """ "761600.00" → "$ 761.600" (COP without decimals); other currencies with two decimals."""
    amount = Decimal(value or 0)
    sign = "-" if amount < 0 else ""
    if currency == "COP":
        text = f"{abs(amount).quantize(Decimal('1'), ROUND_HALF_UP):,.0f}".replace(",", ".")
    else:
        text = f"{abs(amount):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}$ {text}"


_UNITS = [
    "cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce",
    "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno",
    "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho",
    "veintinueve",
]  # fmt: skip
_TENS = {3: "treinta", 4: "cuarenta", 5: "cincuenta", 6: "sesenta", 7: "setenta", 8: "ochenta", 9: "noventa"}
_HUNDREDS = {
    1: "ciento", 2: "doscientos", 3: "trescientos", 4: "cuatrocientos", 5: "quinientos", 6: "seiscientos",
    7: "setecientos", 8: "ochocientos", 9: "novecientos",
}  # fmt: skip


def _below_thousand(n: int) -> str:
    if n == 100:
        return "cien"
    hundreds, rest = divmod(n, 100)
    words = [_HUNDREDS[hundreds]] if hundreds else []
    if rest >= 30:
        tens, unit = divmod(rest, 10)
        words.append(_TENS[tens] + (f" y {_UNITS[unit]}" if unit else ""))
    elif rest:
        words.append(_UNITS[rest])
    return " ".join(words)


def _apocope(words: str) -> str:
    """ "uno" becomes "un" before a noun ("un mil", "veintiún pesos")."""
    if words.endswith("veintiuno"):
        return words[: -len("veintiuno")] + "veintiún"
    if words.endswith("uno"):
        return words[:-3] + "un"
    return words


def _number_words(n: int) -> str:
    if n == 0:
        return "cero"
    millions, rest = divmod(n, 1_000_000)
    thousands, units = divmod(rest, 1000)
    words = []
    if millions:
        words.append("un millón" if millions == 1 else f"{_apocope(_number_words(millions))} millones")
    if thousands:
        words.append("mil" if thousands == 1 else f"{_apocope(_below_thousand(thousands))} mil")
    if units:
        words.append(_below_thousand(units))
    return " ".join(words)


def amount_in_words(value) -> str:
    """Pesos in Spanish words, the way Colombian invoices print them ("… pesos M/CTE")."""
    number = int(abs(Decimal(value or 0)).quantize(Decimal("1"), ROUND_HALF_UP))
    if number == 1:
        return "un peso M/CTE"
    words = _apocope(_number_words(number))
    if number and number % 1_000_000 == 0:
        return f"{words} de pesos M/CTE"
    return f"{words} pesos M/CTE"


def issue_moment(invoice) -> datetime:
    moment = invoice.issued_at or timezone.now()
    return timezone.localtime(moment, ZoneInfo(invoice.property.timezone or "America/Bogota"))


def issue_time(invoice) -> str:
    """ "12:30:00-05:00" (DIAN HoraFac / IssueTime)."""
    moment = issue_moment(invoice)
    offset = moment.strftime("%z")
    return f"{moment:%H:%M:%S}{offset[:3]}:{offset[3:]}"


def _taxable_base(invoice) -> Decimal:
    return sum(
        (Decimal(line["net"]) for line in invoice.lines if line.get("tax_status") in ("taxed", "exempt")),
        Decimal("0"),
    )


def _tax_groups(invoice) -> list[dict]:
    """IVA by rate: [{"rate", "taxable", "tax"}] (exempt lines are a 0 % group; excluded lines are not
    taxed)."""
    groups: dict[str, dict] = {}
    for line in invoice.lines:
        if line.get("tax_status") not in ("taxed", "exempt"):
            continue
        rate = line.get("tax_rate", "0.00")
        group = groups.setdefault(rate, {"rate": rate, "taxable": Decimal("0"), "tax": Decimal("0")})
        group["taxable"] += Decimal(line["net"])
        group["tax"] += Decimal(line["tax_amount"])
    return sorted(groups.values(), key=lambda g: Decimal(g["rate"]), reverse=True)


# --------------------------------------------------------------------------------------------------- PDF


def _styles() -> dict:
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK)
    return {
        "base": base,
        "strong": ParagraphStyle("strong", parent=base, fontName="Helvetica-Bold"),
        "muted": ParagraphStyle("muted", parent=base, textColor=MUTED, fontSize=7.8, leading=10),
        "small": ParagraphStyle("small", parent=base, textColor=MUTED, fontSize=6.8, leading=8.6),
        "legal_name": ParagraphStyle(
            "legal_name", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=16
        ),
        "eyebrow": ParagraphStyle(
            "eyebrow", parent=base, fontName="Helvetica-Bold", fontSize=6.6, leading=8.5, textColor=ACCENT_INK
        ),
        "doc_number": ParagraphStyle(
            "doc_number", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21
        ),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8, leading=10),
        "cell_right": ParagraphStyle("cell_right", parent=base, fontSize=8, leading=10, alignment=TA_RIGHT),
        "head": ParagraphStyle("head", parent=base, fontName="Helvetica-Bold", fontSize=6.8, textColor=MUTED),
        "head_right": ParagraphStyle(
            "head_right",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=6.8,
            textColor=MUTED,
            alignment=TA_RIGHT,
        ),
        "total_label": ParagraphStyle("total_label", parent=base, alignment=TA_RIGHT, textColor=MUTED),
        "total_value": ParagraphStyle("total_value", parent=base, alignment=TA_RIGHT),
        "grand_label": ParagraphStyle(
            "grand_label", parent=base, fontName="Helvetica-Bold", fontSize=10, leading=13, alignment=TA_RIGHT
        ),
        "grand_value": ParagraphStyle(
            "grand_value",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            alignment=TA_RIGHT,
            textColor=ACCENT_INK,
        ),
        "mono": ParagraphStyle("mono", parent=base, fontName="Courier", fontSize=7.2, leading=9),
        "url": ParagraphStyle("url", parent=base, textColor=MUTED, fontSize=6.4, leading=8, wordWrap="CJK"),
        "note": ParagraphStyle("note", parent=base, textColor=ACCENT_INK, fontSize=8, leading=10.5),
    }


def _p(text, style) -> Paragraph:
    return Paragraph(escape(str(text or "")), style)


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:]


def _customer_document(customer: dict) -> str:
    label = DOCUMENT_LABELS.get(customer.get("document_type", ""), "Documento")
    number = customer.get("document_number", "")
    dv = customer.get("dv", "")
    return f"{label} {number}-{dv}" if dv else f"{label} {number}"


def _header(invoice, supplier, s) -> Table:
    moment = issue_moment(invoice)
    contact = " · ".join(x for x in (supplier["phone"], supplier["email"]) if x)
    place = ", ".join(x for x in (supplier["city"], supplier["department"]) if x)
    issuer = [_p(supplier["legal_name"], s["legal_name"])]
    if supplier["trade_name"] and supplier["trade_name"] != supplier["legal_name"]:
        issuer.append(_p(supplier["trade_name"], s["muted"]))
    ids = f"NIT {supplier['nit_display']}" if supplier["nit_display"] else "NIT sin configurar"
    if supplier["rnt"]:
        ids += f" · RNT {supplier['rnt']}"
    issuer += [
        _p(ids, s["base"]),
        _p(supplier["address"], s["muted"]),
        _p(place, s["muted"]),
        _p(contact, s["muted"]),
    ]
    box_rows = [
        [_p(TITLES[invoice.kind], s["eyebrow"])],
        [_p(invoice.full_number or "Borrador", s["doc_number"])],
        [_p(f"Emitida el {moment:%d/%m/%Y} a las {moment:%H:%M}", s["muted"])],
        [_p("Forma de pago: contado", s["muted"])],
        [_p(ENVIRONMENT_LABELS.get(invoice.environment, ""), s["small"])],
    ]
    box = Table(box_rows, colWidths=[64 * mm])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                ("LINEABOVE", (0, 0), (-1, 0), 2, ACCENT),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 7),
                ("TOPPADDING", (0, 1), (-1, -1), 1),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 7),
            ]
        )
    )
    header = Table([[issuer, box]], colWidths=[CONTENT_WIDTH - 64 * mm, 64 * mm])
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
            ]
        )
    )
    return header


def _authorization(invoice, s) -> Paragraph:
    resolution = invoice.resolution
    if invoice.kind == Invoice.Kind.CREDIT_NOTE:
        text = (
            f"Nota crédito con numeración {invoice.prefix or '—'} · ajuste a una factura electrónica de venta"
        )
    elif resolution is None:
        text = "Sin resolución de numeración asociada"
    else:
        text = (
            f"Autorización de numeración de facturación DIAN No. {resolution.resolution_number or '—'} del "
            f"{resolution.valid_from:%d/%m/%Y} · Prefijo {resolution.prefix or '—'} del "
            f"{resolution.from_number} al "
            f"{resolution.to_number} · Vigente hasta el {resolution.valid_to:%d/%m/%Y}"
        )
    return _p(text, s["small"])


def _stay_block(invoice, s) -> list:
    reservation = invoice.reservation
    if reservation is None:
        return [_p("CONCEPTO", s["eyebrow"]), _p("Servicios del hotel", s["base"])]
    nights = (reservation.checkout_date - reservation.checkin_date).days
    rooms = sorted({stay.room.number for stay in reservation.stays.select_related("room") if stay.room_id})
    block = [
        _p("ESTADÍA", s["eyebrow"]),
        _p(f"Reserva {reservation.code}", s["strong"]),
        _p(
            f"Llegada {reservation.checkin_date:%d/%m/%Y} · Salida {reservation.checkout_date:%d/%m/%Y} "
            f"({nights} {'noche' if nights == 1 else 'noches'})",
            s["base"],
        ),
    ]
    if rooms:
        block.append(
            _p(("Habitación " if len(rooms) == 1 else "Habitaciones ") + ", ".join(rooms), s["muted"])
        )
    return block


def _parties(invoice, s) -> Table:
    customer = invoice.customer or {}
    place = ", ".join(x for x in (customer.get("city"), customer.get("country")) if x)
    buyer = [_p("ADQUIRIENTE", s["eyebrow"]), _p(customer.get("name", ""), s["strong"])]
    buyer.append(_p(_customer_document(customer), s["base"]))
    for value in (customer.get("address"), place, customer.get("email"), customer.get("phone")):
        if value:
            buyer.append(_p(value, s["muted"]))
    table = Table([[buyer, _stay_block(invoice, s)]], colWidths=[CONTENT_WIDTH / 2, CONTENT_WIDTH / 2])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEABOVE", (0, 0), (-1, 0), 0.6, RULE),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _reference(invoice, s) -> Table | None:
    original = invoice.related_invoice
    if invoice.kind != Invoice.Kind.CREDIT_NOTE or original is None:
        return None
    rows = [
        [_p("DOCUMENTO REFERENCIADO", s["eyebrow"])],
        [_p(f"Factura electrónica {original.full_number} del {original.issue_date:%d/%m/%Y}", s["strong"])],
        [_p(f"CUFE {original.cufe or 'pendiente'}", s["mono"])],
        [_p("Concepto de corrección: 2 · Anulación de factura electrónica", s["muted"])],
        [_p(f"Motivo: {invoice.reason}", s["base"])],
    ]
    table = Table(rows, colWidths=[CONTENT_WIDTH])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 1), (-1, -1), 1),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
            ]
        )
    )
    return table


def _lines(invoice, s) -> Table:
    currency = invoice.currency
    head = ["Código", "Descripción", "Cant.", "Vr. unitario", "IVA", "Vr. IVA", "Total"]
    rows = [[_p(h, s["head_right"] if i >= 2 else s["head"]) for i, h in enumerate(head)]]
    for line in invoice.lines:
        status = line.get("tax_status", "excluded")
        rate = TAX_LABELS.get(status) or f"{Decimal(line.get('tax_rate', '0')).normalize():f}%"
        rows.append(
            [
                _p(line.get("code", ""), s["small"]),
                _p(line.get("description", ""), s["cell"]),
                _p(line.get("quantity", ""), s["cell_right"]),
                _p(money(line.get("unit_price"), currency), s["cell_right"]),
                _p(rate, s["cell_right"]),
                _p(money(line.get("tax_amount"), currency), s["cell_right"]),
                _p(money(line.get("total"), currency), s["cell_right"]),
            ]
        )
    widths = [22 * mm, 60 * mm, 12 * mm, 24 * mm, 14 * mm, 22 * mm, CONTENT_WIDTH - 154 * mm]
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SURFACE),
                ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _totals(invoice, s) -> Table:
    currency = invoice.currency
    by_status: dict[str, Decimal] = {}
    for line in invoice.lines:
        status = line.get("tax_status", "excluded")
        by_status[status] = by_status.get(status, Decimal("0")) + Decimal(line["net"])
    rows = [[_p("Subtotal", s["total_label"]), _p(money(invoice.subtotal, currency), s["total_value"])]]
    if by_status.get("exempt"):
        rows.append(
            [
                _p("Base exenta de IVA", s["total_label"]),
                _p(money(by_status["exempt"], currency), s["total_value"]),
            ]
        )
    if by_status.get("excluded"):
        rows.append(
            [_p("No gravado", s["total_label"]), _p(money(by_status["excluded"], currency), s["total_value"])]
        )
    for group in _tax_groups(invoice):
        if group["tax"]:
            label = f"IVA {Decimal(group['rate']).normalize():f}% sobre {money(group['taxable'], currency)}"
            rows.append([_p(label, s["total_label"]), _p(money(group["tax"], currency), s["total_value"])])
    rows.append([_p("Total", s["grand_label"]), _p(money(invoice.total, currency), s["grand_value"])])
    totals = Table(rows, colWidths=[46 * mm, 30 * mm])
    totals.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, -1), (-1, -1), 1, ACCENT),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, -1), (-1, -1), 5),
                ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
            ]
        )
    )
    words = [
        _p("VALOR EN LETRAS", s["eyebrow"]),
        _p(_sentence(amount_in_words(invoice.total)), s["base"]),
    ]
    table = Table([[words, totals]], colWidths=[CONTENT_WIDTH - 76 * mm, 76 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _note(text, s) -> Table:
    table = Table([[_p(text, s["note"])]], colWidths=[CONTENT_WIDTH])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), ACCENT_SOFT),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _qr(value: str, size: float) -> Drawing:
    widget = QrCodeWidget(value, barLevel="M")
    left, bottom, right, top = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (right - left), 0, 0, size / (top - bottom), 0, 0])
    drawing.add(widget)
    return drawing


def _validation(invoice, s) -> KeepTogether:
    code_name = "CUDE" if invoice.kind == Invoice.Kind.CREDIT_NOTE else "CUFE"
    settings = ComplianceSettings.objects.filter(property=invoice.property_id).first()
    right = [_p(code_name, s["eyebrow"])]
    if invoice.cufe:
        right += [_p(invoice.cufe[:48], s["mono"]), _p(invoice.cufe[48:], s["mono"])]
        right.append(_p("Consulta en la DIAN:", s["small"]))
        right.append(_p(validation_url(invoice.cufe, invoice.environment), s["url"]))
    else:
        right.append(_p("Pendiente de validación por la DIAN", s["muted"]))
    provider = PROVIDER_LABELS.get(invoice.provider, invoice.provider or PROVIDER_LABELS["simulated"])
    right.append(
        _p(
            f"Representación gráfica de la {TITLES[invoice.kind].lower()} · Proveedor tecnológico: "
            f"{provider}",
            s["small"],
        )
    )
    if settings is not None and settings.invoice_notes:
        right.append(_p(settings.invoice_notes, s["small"]))
    qr_value = invoice.qr_data or (validation_url(invoice.cufe, invoice.environment) if invoice.cufe else "")
    left = _qr(qr_value, 30 * mm) if qr_value else _p("", s["small"])
    table = Table([[left, right]], colWidths=[34 * mm, CONTENT_WIDTH - 34 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEABOVE", (0, 0), (-1, 0), 0.6, RULE),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return KeepTogether([table])


def _decorate(invoice, supplier):
    simulated = invoice.mode == "simulated"

    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(ACCENT)
        canvas.rect(0, PAGE_HEIGHT - 3, PAGE_WIDTH, 3, stroke=0, fill=1)
        if simulated:
            canvas.setFillColor(WATERMARK)
            canvas.setFont("Helvetica-Bold", 44)
            canvas.translate(PAGE_WIDTH / 2, PAGE_HEIGHT / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "SIMULADA · SIN VALIDEZ FISCAL")
            canvas.rotate(-35)
            canvas.translate(-PAGE_WIDTH / 2, -PAGE_HEIGHT / 2)
            canvas.setFillColor(ACCENT_INK)
            canvas.setFont("Helvetica-Bold", 7)
            canvas.drawString(MARGIN, PAGE_HEIGHT - 10 * mm, "DOCUMENTO SIMULADO — SIN VALIDEZ FISCAL")
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.8)
        footer = f"{supplier['legal_name']} · {invoice.full_number or 'Borrador'} · Generado con Housetel"
        canvas.drawString(MARGIN, 9 * mm, footer)
        canvas.drawRightString(PAGE_WIDTH - MARGIN, 9 * mm, f"Página {doc.page}")
        canvas.restoreState()

    return draw


def render_invoice_pdf(invoice) -> bytes:
    """The invoice / credit note as a PDF (bytes)."""
    s = _styles()
    supplier = supplier_info(invoice.property)
    buffer = BytesIO()
    title = TITLES[invoice.kind]
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=15 * mm,
        bottomMargin=16 * mm,
        title=f"{title.capitalize()} {invoice.full_number}",
        author=supplier["legal_name"],
        subject=title.capitalize(),
        creator="Housetel",
    )
    story = [_header(invoice, supplier, s), Spacer(1, 4 * mm), _authorization(invoice, s), Spacer(1, 3 * mm)]
    story.append(_parties(invoice, s))
    reference = _reference(invoice, s)
    if reference is not None:
        story += [Spacer(1, 3 * mm), reference]
    story += [Spacer(1, 5 * mm), _lines(invoice, s), _totals(invoice, s)]
    if invoice.exempt_note:
        story += [Spacer(1, 4 * mm), _note(invoice.exempt_note, s)]
    story += [Spacer(1, 6 * mm), _validation(invoice, s)]
    decorate = _decorate(invoice, supplier)
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()


# --------------------------------------------------------------------------------------------------- XML


def _el(parent, tag: str, text=None, **attrs) -> ET.Element:
    prefix, name = tag.split(":")
    element = ET.SubElement(parent, f"{{{UBL[prefix]}}}{name}", {k: str(v) for k, v in attrs.items()})
    if text is not None:
        element.text = str(text)
    return element


def _amount(parent, tag, value, currency) -> ET.Element:
    return _el(parent, tag, f"{Decimal(value or 0):.2f}", currencyID=currency)


def _supplier_party(root, supplier) -> None:
    party = _el(_el(root, "cac:AccountingSupplierParty"), "cac:Party")
    _el(_el(party, "cac:PartyName"), "cbc:Name", supplier["trade_name"])
    address = _el(_el(party, "cac:PhysicalLocation"), "cac:Address")
    _el(address, "cbc:ID", supplier["municipality_code"])
    _el(address, "cbc:CityName", supplier["city"])
    _el(address, "cbc:CountrySubentity", supplier["department"])
    _el(_el(address, "cac:AddressLine"), "cbc:Line", supplier["address"])
    _el(_el(address, "cac:Country"), "cbc:IdentificationCode", supplier["country"])
    scheme = _el(party, "cac:PartyTaxScheme")
    _el(scheme, "cbc:RegistrationName", supplier["legal_name"])
    _el(scheme, "cbc:CompanyID", supplier["nit"], schemeID=supplier["dv"], schemeName="31")
    tax = _el(scheme, "cac:TaxScheme")
    _el(tax, "cbc:ID", "01")
    _el(tax, "cbc:Name", "IVA")
    _el(_el(party, "cac:PartyLegalEntity"), "cbc:RegistrationName", supplier["legal_name"])
    contact = _el(party, "cac:Contact")
    _el(contact, "cbc:Telephone", supplier["phone"])
    _el(contact, "cbc:ElectronicMail", supplier["email"])


def _customer_party(root, customer) -> None:
    wrapper = _el(root, "cac:AccountingCustomerParty")
    _el(wrapper, "cbc:AdditionalAccountID", "1" if customer.get("legal_organization") == "company" else "2")
    party = _el(wrapper, "cac:Party")
    _el(_el(party, "cac:PartyName"), "cbc:Name", customer.get("name", ""))
    scheme = _el(party, "cac:PartyTaxScheme")
    _el(scheme, "cbc:RegistrationName", customer.get("name", ""))
    attrs = {"schemeName": customer.get("dian_document_code", "13")}
    if customer.get("dv"):
        attrs["schemeID"] = customer["dv"]
    _el(scheme, "cbc:CompanyID", customer.get("document_number", ""), **attrs)
    tax = _el(scheme, "cac:TaxScheme")
    _el(tax, "cbc:ID", "ZZ")
    _el(tax, "cbc:Name", "No aplica")
    contact = _el(party, "cac:Contact")
    _el(contact, "cbc:ElectronicMail", customer.get("email", ""))


def _tax_total(parent, groups, currency) -> None:
    total = _el(parent, "cac:TaxTotal")
    _amount(total, "cbc:TaxAmount", sum((g["tax"] for g in groups), Decimal("0")), currency)
    for group in groups:
        subtotal = _el(total, "cac:TaxSubtotal")
        _amount(subtotal, "cbc:TaxableAmount", group["taxable"], currency)
        _amount(subtotal, "cbc:TaxAmount", group["tax"], currency)
        category = _el(subtotal, "cac:TaxCategory")
        _el(category, "cbc:Percent", group["rate"])
        scheme = _el(category, "cac:TaxScheme")
        _el(scheme, "cbc:ID", "01")
        _el(scheme, "cbc:Name", "IVA")


def render_invoice_xml(invoice) -> bytes:
    """UBL 2.1 XML of the invoice (`Invoice`) or credit note (`CreditNote`), UTF-8 with declaration."""
    credit = invoice.kind == Invoice.Kind.CREDIT_NOTE
    currency = invoice.currency
    root = ET.Element(
        f"{{{UBL['credit_note' if credit else 'invoice']}}}{'CreditNote' if credit else 'Invoice'}"
    )
    environment = ENVIRONMENT_CODES.get(invoice.environment, "2")
    _el(root, "cbc:UBLVersionID", "UBL 2.1")
    _el(root, "cbc:CustomizationID", "20" if credit else "10")
    profile = "Nota Crédito de Factura Electrónica de Venta" if credit else "Factura Electrónica de Venta"
    _el(root, "cbc:ProfileID", f"DIAN 2.1: {profile}")
    _el(root, "cbc:ProfileExecutionID", environment)
    _el(root, "cbc:ID", invoice.full_number)
    _el(
        root,
        "cbc:UUID",
        invoice.cufe,
        schemeID=environment,
        schemeName="CUDE-SHA384" if credit else "CUFE-SHA384",
    )
    _el(root, "cbc:IssueDate", invoice.issue_date.isoformat())
    _el(root, "cbc:IssueTime", issue_time(invoice))
    _el(root, "cbc:CreditNoteTypeCode" if credit else "cbc:InvoiceTypeCode", "91" if credit else "01")
    note = invoice.reason if credit else invoice.exempt_note
    if note:
        _el(root, "cbc:Note", note)
    _el(root, "cbc:DocumentCurrencyCode", currency)
    _el(root, "cbc:LineCountNumeric", len(invoice.lines))
    original = invoice.related_invoice if credit else None
    if credit:
        discrepancy = _el(root, "cac:DiscrepancyResponse")
        _el(discrepancy, "cbc:ReferenceID", original.full_number if original else "")
        _el(discrepancy, "cbc:ResponseCode", "2")
        _el(discrepancy, "cbc:Description", invoice.reason)
        if original is not None:
            reference = _el(_el(root, "cac:BillingReference"), "cac:InvoiceDocumentReference")
            _el(reference, "cbc:ID", original.full_number)
            _el(reference, "cbc:UUID", original.cufe, schemeName="CUFE-SHA384")
            _el(reference, "cbc:IssueDate", original.issue_date.isoformat())
    _supplier_party(root, supplier_info(invoice.property))
    _customer_party(root, invoice.customer or {})
    means = _el(root, "cac:PaymentMeans")
    _el(means, "cbc:ID", "1")
    _el(means, "cbc:PaymentMeansCode", "10")
    groups = _tax_groups(invoice)
    _tax_total(root, groups, currency)
    totals = _el(root, "cac:LegalMonetaryTotal")
    _amount(totals, "cbc:LineExtensionAmount", invoice.subtotal, currency)
    _amount(totals, "cbc:TaxExclusiveAmount", _taxable_base(invoice), currency)
    _amount(totals, "cbc:TaxInclusiveAmount", invoice.total, currency)
    _amount(totals, "cbc:PayableAmount", invoice.total, currency)
    for index, line in enumerate(invoice.lines, start=1):
        element = _el(root, "cac:CreditNoteLine" if credit else "cac:InvoiceLine")
        _el(element, "cbc:ID", index)
        _el(
            element,
            "cbc:CreditedQuantity" if credit else "cbc:InvoicedQuantity",
            line["quantity"],
            unitCode="94",
        )
        _amount(element, "cbc:LineExtensionAmount", line["net"], currency)
        if line.get("tax_status") in ("taxed", "exempt"):
            _tax_total(
                element,
                [
                    {
                        "rate": line["tax_rate"],
                        "taxable": Decimal(line["net"]),
                        "tax": Decimal(line["tax_amount"]),
                    }
                ],
                currency,
            )
        item = _el(element, "cac:Item")
        _el(item, "cbc:Description", line["description"])
        _el(_el(item, "cac:StandardItemIdentification"), "cbc:ID", line["code"], schemeID="999")
        price = _el(element, "cac:Price")
        _amount(price, "cbc:PriceAmount", line["unit_price"], currency)
        _el(price, "cbc:BaseQuantity", line["quantity"], unitCode="94")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
