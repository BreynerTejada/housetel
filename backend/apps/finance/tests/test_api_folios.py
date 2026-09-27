"""Staff API: folios (list, detail with totals, ensure), charge options, posting and voiding charges."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core.tests.factories import OrganizationFactory, PropertyFactory
from apps.finance.models import Charge, Folio, Refund
from apps.finance.services import get_or_create_folio, post_charge, record_payment
from apps.finance.tests.factories import FolioFactory, PaymentFactory
from apps.guests.tests.factories import ForeignGuestFactory
from apps.rates.models import Extra
from apps.rates.tests.factories import ExtraFactory, TaxFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/finance/"


@pytest.fixture
def reservation(prop):
    today = prop.business_date
    reservation = ReservationFactory(
        property=prop,
        code="HT-API001",
        checkin_date=today,
        checkout_date=today + timedelta(days=2),
        adults=2,
        children=1,
    )
    StayFactory(reservation=reservation, total_amount=Decimal("700000"))
    return reservation


@pytest.fixture
def folio(reservation):
    return get_or_create_folio(reservation)


@pytest.fixture
def iva_extras(prop):
    return TaxFactory(
        property=prop,
        code="IVA-EXT",
        name="IVA extras",
        rate=Decimal("19"),
        applies_to="extras",
        exempt_foreign_non_residents=False,
    )


class TestList:
    def test_lists_the_folios_of_a_reservation_with_totals(self, api, reservation, folio):
        post_charge(folio, kind="extra", amount=Decimal("50000"), description="Minibar")

        response = api.get(f"{URL}folios/", {"reservation": str(reservation.pk)})

        assert response.status_code == 200
        (item,) = response.json()["results"]
        assert (item["id"], item["folio_type"], item["status"], item["currency"]) == (
            str(folio.pk),
            "guest",
            "open",
            "COP",
        )
        assert item["reservation"]["code"] == "HT-API001"
        assert item["guest"]["full_name"] == reservation.booker.full_name
        assert item["totals"]["charges_total"] == "50000.00"
        assert item["totals"]["balance"] == "50000.00"

    def test_other_reservations_and_hotels_stay_out(self, api, prop, reservation, folio):
        FolioFactory(reservation__property=prop)  # another reservation of the hotel
        FolioFactory(reservation__property=PropertyFactory(organization=OrganizationFactory()))
        response = api.get(f"{URL}folios/", {"reservation": str(reservation.pk)})
        assert [row["id"] for row in response.json()["results"]] == [str(folio.pk)]
        assert api.get(f"{URL}folios/").json()["count"] == 2


class TestDetail:
    def test_shows_every_line_and_the_totals(self, api, reservation, folio, iva_extras, owner):
        post_charge(folio, kind="extra", amount=Decimal("100000"), description="Tour", tax=iva_extras)
        voided = post_charge(folio, kind="extra", amount=Decimal("50000"), description="Minibar")
        Charge.objects.filter(pk=voided.pk).update(voided_at=timezone.now(), void_reason="Error")
        paid = record_payment(folio, amount=Decimal("100000"), method="bank_transfer", actor=owner)
        PaymentFactory(folio=folio, amount=Decimal("5000"), status="declined")
        Refund.objects.create(payment=paid, amount=Decimal("20000"), status="approved", reason="Descuento")

        body = api.get(f"{URL}folios/{folio.pk}/").json()

        assert body["totals"] == {
            "charges_net": "100000.00",
            "tax_total": "19000.00",
            "charges_total": "119000.00",
            "payments_total": "100000.00",
            "refunds_total": "20000.00",
            "balance": "39000.00",
            "reservation_balance": "739000.00",
        }
        tour, minibar = body["charges"]
        assert (tour["description"], tour["amount"], tour["tax_amount"], tour["total"], tour["voided"]) == (
            "Tour",
            "100000.00",
            "19000.00",
            "119000.00",
            False,
        )
        assert tour["tax"]["code"] == "IVA-EXT" and tour["tax_exempt"] is False
        assert (minibar["voided"], minibar["void_reason"]) == (True, "Error")
        transfer, declined = body["payments"]
        assert (transfer["status"], transfer["refunded_amount"], transfer["refundable_amount"]) == (
            "approved",
            "20000.00",
            "80000.00",
        )
        assert transfer["received_by"]["id"] == str(owner.pk)
        assert declined["status"] == "declined"
        assert [r["amount"] for r in body["refunds"]] == ["20000.00"]
        assert body["reservation"]["code"] == "HT-API001"

    def test_exempt_lines_are_flagged(self, api, prop, folio):
        iva = TaxFactory(property=prop, code="IVA", rate=Decimal("19"))
        post_charge(
            folio, kind="room", amount=Decimal("300000"), description="Noche", tax=iva, tax_exempt=True
        )
        (charge,) = api.get(f"{URL}folios/{folio.pk}/").json()["charges"]
        assert (charge["tax_amount"], charge["tax_exempt"]) == ("0.00", True)

    def test_folios_of_other_hotels_are_not_found(self, api):
        other = FolioFactory(reservation__property=PropertyFactory(organization=OrganizationFactory()))
        assert api.get(f"{URL}folios/{other.pk}/").status_code == 404


class TestEnsureFolio:
    def test_gets_or_creates_the_reservation_folio(self, api, reservation):
        first = api.post(f"{URL}folios/", {"reservation_id": str(reservation.pk)})
        second = api.post(f"{URL}folios/", {"reservation_id": str(reservation.pk)})
        assert (first.status_code, second.status_code) == (201, 200)
        assert first.json()["id"] == second.json()["id"] == str(Folio.objects.get(reservation=reservation).pk)

    def test_reservations_of_other_hotels_are_not_found(self, api):
        other = ReservationFactory(property=PropertyFactory(organization=OrganizationFactory()))
        assert api.post(f"{URL}folios/", {"reservation_id": str(other.pk)}).status_code == 404


class TestChargeOptions:
    def test_extras_come_with_their_default_quantity_and_tax(self, api, prop, folio, iva_extras):
        for code, charge_type in [
            ("STAY", "per_stay"),
            ("NIGHT", "per_night"),
            ("PERSON", "per_person"),
            ("PN", "per_person_night"),
        ]:
            ExtraFactory(property=prop, code=code, charge_type=charge_type, tax=iva_extras)
        ExtraFactory(property=prop, code="OFF", is_active=False)
        ExtraFactory(property=PropertyFactory(organization=prop.organization), code="ELSEWHERE")

        body = api.get(f"{URL}folios/{folio.pk}/charge-options/").json()

        quantities = {extra["code"]: extra["default_quantity"] for extra in body["extras"]}
        assert quantities == {"NIGHT": 2, "PERSON": 3, "PN": 6, "STAY": 1}  # 2 nights, 2 adults + 1 child
        stay = next(extra for extra in body["extras"] if extra["code"] == "STAY")
        assert stay["name"] == {"es": "Desayuno", "en": "Breakfast"}
        assert (stay["price"], stay["unit_price"], stay["tax"]["rate"], stay["tax"]["exempt"]) == (
            "35000.00",
            "35000.00",
            "19.00",
            False,
        )
        assert [tax["code"] for tax in body["taxes"]] == ["IVA-EXT"]
        assert body["manual_kinds"] == ["extra", "fee", "adjustment", "other"]
        assert body["guest_is_foreign_non_resident"] is False


class TestPostCharges:
    def test_posts_an_extra_with_its_tax(self, api, prop, folio, iva_extras, owner):
        extra = ExtraFactory(
            property=prop,
            charge_type="per_stay",
            price=Decimal("80000"),
            tax=iva_extras,
            name={"es": "Late check-out", "en": "Late check-out"},
        )

        response = api.post(f"{URL}folios/{folio.pk}/charges/", {"extra_id": str(extra.pk), "quantity": 2})

        assert response.status_code == 201, response.json()
        body = response.json()
        assert (body["kind"], body["description"], body["quantity"], body["amount"], body["tax_amount"]) == (
            "extra",
            "Late check-out",
            2,
            "160000.00",
            "30400.00",
        )
        assert body["extra_id"] == str(extra.pk) and body["posted_by"]["id"] == str(owner.pk)

    def test_the_quantity_defaults_by_charge_type(self, api, prop, folio):
        extra = ExtraFactory(
            property=prop, charge_type=Extra.ChargeType.PER_PERSON_NIGHT, price=Decimal("35000")
        )
        body = api.post(f"{URL}folios/{folio.pk}/charges/", {"extra_id": str(extra.pk)}).json()
        assert (body["quantity"], body["amount"]) == (6, "210000.00")

    def test_prices_with_tax_included_are_split_into_net_and_tax(self, api, prop, folio):
        included = TaxFactory(
            property=prop,
            code="INC",
            rate=Decimal("19"),
            applies_to="extras",
            included_in_price=True,
            exempt_foreign_non_residents=False,
        )
        extra = ExtraFactory(property=prop, charge_type="per_stay", price=Decimal("119000"), tax=included)
        body = api.post(f"{URL}folios/{folio.pk}/charges/", {"extra_id": str(extra.pk)}).json()
        assert (body["unit_price"], body["amount"], body["tax_amount"], body["total"]) == (
            "100000.00",
            "100000.00",
            "19000.00",
            "119000.00",
        )

    def test_foreign_non_residents_are_exempt_when_the_tax_says_so(self, api, prop):
        booker = ForeignGuestFactory(organization=prop.organization)
        folio = get_or_create_folio(ReservationFactory(property=prop, booker=booker))
        exempting = TaxFactory(property=prop, code="IVA-A", rate=Decimal("19"), applies_to="all")
        extra = ExtraFactory(property=prop, charge_type="per_stay", price=Decimal("90000"), tax=exempting)
        body = api.post(f"{URL}folios/{folio.pk}/charges/", {"extra_id": str(extra.pk)}).json()
        assert (body["tax_amount"], body["tax_exempt"]) == ("0.00", True)

    def test_posts_a_manual_charge(self, api, folio, iva_extras):
        payload = {
            "kind": "fee",
            "description": "Lavandería",
            "amount": "25000",
            "quantity": 1,
            "tax_id": str(iva_extras.pk),
        }
        response = api.post(f"{URL}folios/{folio.pk}/charges/", payload)
        assert response.status_code == 201
        assert (response.json()["amount"], response.json()["tax_amount"]) == ("25000.00", "4750.00")

    def test_adjustments_can_be_credits(self, api, folio):
        payload = {"kind": "adjustment", "description": "Cortesía", "amount": "-30000"}
        assert api.post(f"{URL}folios/{folio.pk}/charges/", payload).json()["total"] == "-30000.00"

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"kind": "room", "description": "Noche", "amount": "1000"}, "kind"),
            ({"kind": "fee", "description": "", "amount": "1000"}, "description"),
            ({"kind": "fee", "description": "Algo"}, "amount"),
            ({"kind": "fee", "description": "Algo", "amount": "1000", "quantity": 0}, "quantity"),
            ({}, "extra_id"),
        ],
    )
    def test_invalid_charges(self, api, folio, payload, field):
        response = api.post(f"{URL}folios/{folio.pk}/charges/", payload)
        assert response.status_code == 400
        assert response.json()["code"] == "validation_error" and field in response.json()["fields"]

    def test_taxes_and_extras_of_other_hotels_are_rejected(self, api, prop, folio):
        elsewhere = PropertyFactory(organization=prop.organization)
        tax = TaxFactory(property=elsewhere)
        extra = ExtraFactory(property=elsewhere)
        manual = {"kind": "fee", "description": "Algo", "amount": "1000", "tax_id": str(tax.pk)}
        assert "tax_id" in api.post(f"{URL}folios/{folio.pk}/charges/", manual).json()["fields"]
        assert (
            "extra_id"
            in api.post(f"{URL}folios/{folio.pk}/charges/", {"extra_id": str(extra.pk)}).json()["fields"]
        )

    def test_a_closed_folio_is_a_conflict(self, api, folio):
        Folio.objects.filter(pk=folio.pk).update(status="closed")
        payload = {"kind": "fee", "description": "Algo", "amount": "1000"}
        response = api.post(f"{URL}folios/{folio.pk}/charges/", payload)
        assert (response.status_code, response.json()["code"]) == (409, "folio_closed")


class TestVoidCharge:
    def test_requires_confirmation(self, api, folio):
        charge = post_charge(folio, kind="extra", amount=Decimal("50000"), description="Minibar")
        response = api.post(f"{URL}charges/{charge.pk}/void/", {"reason": "Error"})
        assert (response.status_code, response.json()["code"]) == (400, "confirmation_required")

    def test_voids_with_a_reason(self, api, folio, owner):
        charge = post_charge(folio, kind="extra", amount=Decimal("50000"), description="Minibar")
        response = api.post(f"{URL}charges/{charge.pk}/void/", {"reason": "No lo consumió", "confirm": True})
        assert response.status_code == 200
        body = response.json()
        assert (body["voided"], body["void_reason"], body["voided_by"]["id"]) == (
            True,
            "No lo consumió",
            str(owner.pk),
        )

    def test_charges_of_other_hotels_are_not_found(self, api):
        other = FolioFactory(reservation__property=PropertyFactory(organization=OrganizationFactory()))
        charge = post_charge(other, kind="extra", amount=Decimal("1000"), description="x")
        assert (
            api.post(f"{URL}charges/{charge.pk}/void/", {"reason": "x", "confirm": True}).status_code == 404
        )
