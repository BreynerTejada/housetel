"""Invoice content: lines grouped from the folio, customer, totals, IVA exemption, CUFE and QR."""

import hashlib
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.compliance.services.builder import EXEMPT_NOTE, build_document, check_digit, invoice_customer
from apps.compliance.services.cufe import compute_cufe, qr_payload
from apps.compliance.tests.factories import post
from apps.finance.tests.factories import FolioFactory
from apps.guests.tests.factories import ForeignGuestFactory, GuestFactory
from apps.inventory.tests.factories import RoomTypeFactory
from apps.rates.tests.factories import TaxFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def lodging_tax(prop):
    return TaxFactory(property=prop, code="IVA", name="IVA 19% alojamiento")


@pytest.fixture
def extras_tax(prop):
    return TaxFactory(
        property=prop,
        code="IVA-EXT",
        name="IVA 19% extras",
        applies_to="extras",
        exempt_foreign_non_residents=False,
    )


def folio_for(prop, booker=None, *, room_type_name="Estándar"):
    reservation = ReservationFactory(property=prop, **({"booker": booker} if booker else {}))
    room_type = RoomTypeFactory(property=prop, code="DBL", name={"es": room_type_name, "en": "Standard"})
    stay = StayFactory(reservation=reservation, room_type=room_type)
    return FolioFactory(reservation=reservation), stay


def night(folio, stay, day, amount, tax=None, tax_amount="0"):
    return post(
        folio,
        kind="room",
        amount=amount,
        description=f"Noche {day}",
        tax=tax,
        tax_amount=tax_amount,
        stay=stay,
        night_date=day,
        business_date=day,
    )


class TestLines:
    def test_room_nights_are_grouped_by_category_and_price(self, prop, lodging_tax):
        folio, stay = folio_for(prop)
        d = date(2026, 10, 12)
        night(folio, stay, d, "320000", lodging_tax, "60800")
        night(folio, stay, d + timedelta(days=1), "320000", lodging_tax, "60800")
        night(folio, stay, d + timedelta(days=2), "368000", lodging_tax, "69920")  # weekend +15 %

        doc = build_document(folio, list(folio.charges.all()))

        assert [
            (line["description"], line["quantity"], line["unit_price"], line["net"], line["tax_amount"])
            for line in doc.lines
        ] == [
            ("Alojamiento Estándar · 2 noches", 2, "320000.00", "640000.00", "121600.00"),
            ("Alojamiento Estándar · 1 noche", 1, "368000.00", "368000.00", "69920.00"),
        ]
        assert {line["tax_status"] for line in doc.lines} == {"taxed"}
        assert doc.lines[0]["tax_rate"] == "19.00"

    def test_extras_and_penalties_get_their_own_lines(self, prop, lodging_tax, extras_tax):
        folio, stay = folio_for(prop)
        night(folio, stay, date(2026, 10, 12), "320000", lodging_tax, "60800")
        post(
            folio,
            kind="extra",
            amount="35000",
            quantity=2,
            description="Desayuno",
            tax=extras_tax,
            tax_amount="13300",
        )
        post(
            folio,
            kind="extra",
            amount="35000",
            quantity=1,
            description="Desayuno",
            tax=extras_tax,
            tax_amount="6650",
        )
        post(folio, kind="cancellation_fee", amount="320000", description="Penalidad por cancelación")

        doc = build_document(folio, list(folio.charges.all()))

        assert [
            (line["kind"], line["description"], line["quantity"], line["tax_status"]) for line in doc.lines
        ] == [
            ("room", "Alojamiento Estándar · 1 noche", 1, "taxed"),
            ("extra", "Desayuno", 3, "taxed"),
            ("cancellation_fee", "Penalidad por cancelación", 1, "excluded"),
        ]
        assert doc.lines[1]["net"] == "105000.00" and doc.lines[1]["tax_amount"] == "19950.00"
        assert doc.lines[2]["tax_rate"] == "0.00"

    def test_totals_are_the_folio_totals_without_voided_charges(self, prop, lodging_tax, extras_tax):
        folio, stay = folio_for(prop)
        night(folio, stay, date(2026, 10, 12), "320000", lodging_tax, "60800")
        post(
            folio, kind="extra", amount="25000", description="Parqueadero", tax=extras_tax, tax_amount="4750"
        )
        post(folio, kind="adjustment", amount="-20000", description="Descuento cortesía")
        voided = post(
            folio, kind="fee", amount="50000", description="Lavandería", tax=extras_tax, tax_amount="9500"
        )
        voided.voided_at = voided.created_at
        voided.save()

        doc = build_document(folio, list(folio.charges.filter(voided_at__isnull=True)))

        # net 320000 + 25000 − 20000 = 325000; IVA 60800 + 4750 = 65550
        assert (doc.subtotal, doc.tax_total, doc.total) == (
            Decimal("325000"),
            Decimal("65550"),
            Decimal("390550"),
        )
        assert voided.pk not in doc.charge_ids
        assert len(doc.charge_ids) == 3


class TestExemption:
    def test_a_foreign_non_resident_gets_exempt_lodging_and_the_legal_note(
        self, prop, lodging_tax, extras_tax
    ):
        folio, stay = folio_for(prop, booker=ForeignGuestFactory(organization=prop.organization))
        night(folio, stay, date(2026, 10, 12), "320000", lodging_tax, "0")  # exempt: tax set, amount 0
        post(folio, kind="extra", amount="35000", description="Desayuno", tax=extras_tax, tax_amount="6650")

        doc = build_document(folio, list(folio.charges.all()))

        room, extra = doc.lines
        assert (room["tax_status"], room["tax_rate"], room["tax_amount"]) == ("exempt", "0.00", "0.00")
        assert (extra["tax_status"], extra["tax_amount"]) == ("taxed", "6650.00")
        assert doc.exempt_note == EXEMPT_NOTE
        assert "481" in doc.exempt_note and "no residentes" in doc.exempt_note
        assert doc.tax_total == Decimal("6650")

    def test_a_resident_invoice_has_no_exemption_note(self, prop, lodging_tax):
        folio, stay = folio_for(prop)
        night(folio, stay, date(2026, 10, 12), "320000", lodging_tax, "60800")

        assert build_document(folio, list(folio.charges.all())).exempt_note == ""


class TestCustomer:
    def test_the_booker_is_the_customer(self, prop):
        guest = GuestFactory(
            organization=prop.organization,
            first_name="Laura",
            last_name="Gómez",
            document_type="CC",
            document_number="52123456",
            email="laura@example.com",
        )

        customer = invoice_customer(guest, final_consumer_id="222222222222")

        assert customer["name"] == "Laura Gómez"
        assert (customer["document_type"], customer["dian_document_code"], customer["document_number"]) == (
            "CC",
            "13",
            "52123456",
        )
        assert customer["is_final_consumer"] is False
        assert customer["email"] == "laura@example.com"

    def test_a_foreigner_is_identified_by_passport(self, prop):
        guest = ForeignGuestFactory(organization=prop.organization, document_number="X1234567")

        customer = invoice_customer(guest, final_consumer_id="222222222222")

        assert (customer["dian_document_code"], customer["document_number"], customer["country"]) == (
            "41",
            "X1234567",
            "US",
        )

    def test_without_a_document_the_customer_is_the_final_consumer(self, prop):
        guest = GuestFactory(organization=prop.organization, document_type="", document_number="")

        customer = invoice_customer(guest, final_consumer_id="222222222222")

        assert customer["is_final_consumer"] is True
        assert (customer["name"], customer["document_number"], customer["dian_document_code"]) == (
            "Consumidor final",
            "222222222222",
            "13",
        )

    def test_a_company_nit_gets_its_check_digit(self, prop):
        guest = GuestFactory(
            organization=prop.organization,
            first_name="Viajes Andinos SAS",
            last_name="",
            document_type="NIT",
            document_number="890903938",
        )

        customer = invoice_customer(guest, final_consumer_id="222222222222")

        assert (customer["dian_document_code"], customer["dv"], customer["legal_organization"]) == (
            "31",
            "8",
            "company",
        )

    @pytest.mark.parametrize(
        ("nit", "dv"),
        [
            ("800197268", "4"),
            ("899999068", "1"),
            ("890903938", "8"),
            ("890900608", "9"),
            ("800197268-4", "4"),
        ],
    )
    def test_check_digit_follows_the_dian_algorithm(self, nit, dv):
        assert check_digit(nit) == dv


class TestCufe:
    def test_cufe_is_the_sha384_of_the_dian_concatenation(self):
        raw = (
            "SETT12026-10-1412:30:00-05:00640000.0001121600.00040.00030.00761600.00"
            "901234567"
            "52123456"
            "fc8eac422eba16e22ffd8c6f94b3f40a6e38162c"
            "2"
        )

        cufe = compute_cufe(
            number="SETT1",
            issue_date=date(2026, 10, 14),
            issue_time="12:30:00-05:00",
            subtotal=Decimal("640000"),
            iva=Decimal("121600"),
            total=Decimal("761600"),
            supplier_nit="901234567",
            customer_id="52123456",
            key="fc8eac422eba16e22ffd8c6f94b3f40a6e38162c",
            environment="test",
        )

        assert cufe == hashlib.sha384(raw.encode()).hexdigest()
        assert len(cufe) == 96

    def test_any_change_in_the_inputs_changes_the_cufe(self):
        base = dict(
            number="SETT1",
            issue_date=date(2026, 10, 14),
            issue_time="12:30:00-05:00",
            subtotal=Decimal("640000"),
            iva=Decimal("121600"),
            total=Decimal("761600"),
            supplier_nit="901234567",
            customer_id="52123456",
            key="k",
            environment="test",
        )

        assert compute_cufe(**base) == compute_cufe(**base)
        assert compute_cufe(**base) != compute_cufe(**{**base, "total": Decimal("761601")})
        assert compute_cufe(**base) != compute_cufe(**{**base, "environment": "production"})

    def test_the_qr_carries_the_dian_fields_and_the_validation_link(self):
        payload = qr_payload(
            number="SETT1",
            issue_date=date(2026, 10, 14),
            issue_time="12:30:00-05:00",
            supplier_nit="901234567",
            customer_id="52123456",
            subtotal=Decimal("640000"),
            iva=Decimal("121600"),
            other_taxes=Decimal("0"),
            total=Decimal("761600"),
            cufe="abc",
            environment="test",
        )

        assert payload.splitlines() == [
            "NumFac=SETT1",
            "FecFac=2026-10-14",
            "HorFac=12:30:00-05:00",
            "NitFac=901234567",
            "DocAdq=52123456",
            "ValFac=640000.00",
            "ValIva=121600.00",
            "ValOtroIm=0.00",
            "ValTolFac=761600.00",
            "CUFE=abc",
            "QRCode=https://catalogo-vpfe-hab.dian.gov.co/document/searchqr?documentkey=abc",
        ]
