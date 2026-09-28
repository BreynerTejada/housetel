"""Printable platform invoice (reportlab). Generated on demand; nothing is stored."""

from __future__ import annotations

from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.core.i18n import t

PLATFORM = {
    "name": "Housetel S.A.S.",
    "nit": "NIT 901.555.010-3",
    "address": "Carrera 7 #71-21, Bogotá D.C., Colombia",
    "email": "facturacion@housetel.co",
}
ACCENT = colors.HexColor("#B4583B")
MUTED = colors.HexColor("#6E675E")
BORDER = colors.HexColor("#E7E2DA")
STATUS = {
    "es": {"open": "PENDIENTE", "paid": "PAGADA", "void": "ANULADA", "failed": "COBRO FALLIDO"},
    "en": {"open": "DUE", "paid": "PAID", "void": "VOID", "failed": "PAYMENT FAILED"},
}
LABELS = {
    "es": {
        "invoice": "Factura de plataforma", "billed": "Facturado a", "period": "Periodo", "issued": "Emitida",
        "due": "Vence", "paid": "Pagada", "concept": "Concepto", "qty": "Cant.", "amount": "Valor",
        "subtotal": "Subtotal", "tax": "IVA", "total": "Total", "ref": "Referencia de pago",
        "note": "Todos los módulos de Housetel están incluidos en tu plan. Gracias por confiar en nosotros.",
    },
    "en": {
        "invoice": "Platform invoice", "billed": "Billed to", "period": "Period", "issued": "Issued",
        "due": "Due", "paid": "Paid", "concept": "Item", "qty": "Qty", "amount": "Amount",
        "subtotal": "Subtotal", "tax": "VAT", "total": "Total", "ref": "Payment reference",
        "note": "Every Housetel module is included in your plan. Thank you for trusting us.",
    },
}  # fmt: skip


def _money(value) -> str:
    return "$ " + f"{int(round(float(value))):,}".replace(",", ".")


def invoice_pdf(invoice, lang: str = "es") -> bytes:
    lang = lang if lang in LABELS else "es"
    L = LABELS[lang]
    org = invoice.organization
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"{L['invoice']} {invoice.number}",
    )  # fmt: skip
    styles = getSampleStyleSheet()
    base = ParagraphStyle("base", parent=styles["Normal"], fontName="Helvetica", fontSize=9.5, leading=13)
    muted = ParagraphStyle("muted", parent=base, textColor=MUTED, fontSize=8.5, leading=11)
    title = ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=22)
    brand = ParagraphStyle("brand", parent=base, fontName="Helvetica-Bold", fontSize=14, textColor=ACCENT)

    story = []
    header = Table(
        [
            [
                [Paragraph("Housetel", brand), Paragraph(
                    f"{PLATFORM['name']} · {PLATFORM['nit']}<br/>{PLATFORM['address']}<br/>"
                    f"{PLATFORM['email']}",
                    muted)],
                [Paragraph(L["invoice"], muted), Paragraph(invoice.number, title),
                 Paragraph(STATUS[lang].get(invoice.status, invoice.status.upper()), brand)],
            ]
        ],
        colWidths=[95 * mm, 79 * mm],
    )  # fmt: skip
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    story += [header, Spacer(1, 8 * mm)]

    issued = timezone.localtime(invoice.issued_at).strftime("%d/%m/%Y")
    facts = [
        [Paragraph(f"<b>{L['billed']}</b>", base), Paragraph(f"<b>{L['period']}</b>", base)],
        [
            Paragraph(f"{org.legal_name or org.name}<br/>{('NIT ' + org.nit) if org.nit else ''}", base),
            Paragraph(
                f"{invoice.period_start:%d/%m/%Y} – {invoice.period_end:%d/%m/%Y}<br/>"
                f"{L['issued']}: {issued} · {L['due']}: {invoice.due_date:%d/%m/%Y}"
                + (
                    f"<br/>{L['paid']}: {timezone.localtime(invoice.paid_at):%d/%m/%Y}"
                    if invoice.paid_at
                    else ""
                ),
                base,
            ),
        ],
    ]
    facts_table = Table(facts, colWidths=[95 * mm, 79 * mm])
    facts_table.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)])
    )
    story += [facts_table, Spacer(1, 8 * mm)]

    rows = [[L["concept"], L["qty"], L["amount"]]]
    for line in invoice.lines or []:
        rows.append([Paragraph(t(line.get("description"), lang), base), str(line.get("quantity", 1)),
                     _money(line.get("amount", 0))])  # fmt: skip
    rows += [
        ["", L["subtotal"], _money(invoice.subtotal)],
        ["", f"{L['tax']} {invoice.tax_rate.normalize():f} %", _money(invoice.tax)],
        ["", L["total"], _money(invoice.total)],
    ]
    table = Table(rows, colWidths=[120 * mm, 22 * mm, 32 * mm], repeatRows=1)
    n = len(rows)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, BORDER),
                ("LINEBELOW", (0, 1), (-1, n - 4), 0.4, BORDER),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (1, n - 1), (-1, n - 1), "Helvetica-Bold"),
                ("FONTSIZE", (1, n - 1), (-1, n - 1), 11),
                ("LINEABOVE", (1, n - 1), (-1, n - 1), 0.8, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story += [table, Spacer(1, 10 * mm)]
    if invoice.payment_reference:
        story.append(Paragraph(f"{L['ref']}: {invoice.payment_reference}", muted))
    story.append(Paragraph(L["note"], muted))
    doc.build(story)
    return buffer.getvalue()
