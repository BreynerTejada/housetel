"""Corporate demo seed (pilot plan P4): Hotel Casa Aurora gets three companies — a travel agency and two
corporate accounts — five reservations billed to them, a split folio and receivables of every age.

- Viajes Caribe Mágico (agency, credit 30 days): a past stay 45 days ago with lodging billed to it (the guest
  paid the breakfasts) → 31–60 and overdue; a legacy invoice from 75 days ago (opening balance) → 61–90; a
  future group-like stay (everything, voucher) → in progress.
- Inversiones Portuarias del Caribe (corporate, gran contribuyente, credit 45 days): a past stay 12 days ago
  (everything) → 0–30; the guest in house now with lodging billed to it and a business dinner split 50/50
  between the guest and the company (split folio); a legacy invoice from 118 days ago partly paid by a
  transfer that left credit on account → 90+ and "saldo a favor".
- Tecnologías Andinas del Norte (corporate, credit 30 days): a past stay 25 days ago paid in full by a bank
  transfer on account (the folio is closed: history in its statement).

Reservations are created through the booking services in free rooms (past stays are checked in and out
with `force`, like the bookings seed; the room's housekeeping state of today is kept). Company invoices of the
past stays are issued (dated at the check-out) when the hotel already has an active DIAN resolution —
otherwise the compliance seed invoices them later, one invoice per folio.

Runs anywhere after `bookings` (P-INT: put "corporate" right after "bookings" in `core.seed.SEED_ORDER`, so
the finance seed collects the guests' parts and the compliance seed invoices the company folios in date
order); `python manage.py seed_corporate` runs it on an already seeded demo. Idempotent: an organization that
already has companies is skipped.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction

from apps.bookings.models import Reservation, Stay
from apps.bookings.services.assignment import load_units
from apps.bookings.services.charges import post_room_charges
from apps.bookings.services.reservations import check_in, check_out, create_reservation
from apps.bookings.types import ReservationRequest, StayRequest
from apps.core.errors import DomainError
from apps.corporate import services
from apps.corporate.models import AccountPayment, Company
from apps.corporate.nit import check_digit
from apps.finance import services as finance
from apps.finance.models import Payment
from apps.guests.services import upsert_guest
from apps.guests.types import GuestInput
from apps.inventory.models import Room, RoomType
from apps.rates.models import Extra, RatePlan, Tax

COMPANIES = {
    "agency": {
        "kind": "travel_agency",
        "legal_name": "Viajes Caribe Mágico S.A.S.",
        "trade_name": "Caribe Mágico Travel",
        "nit": "900482731",
        "vat_responsible": True,
        "tax_responsibilities": ["R-99-PN"],
        "address": "Av. San Martín #8-40, Bocagrande",
        "city": "Cartagena",
        "department": "Bolívar",
        "billing_email": "facturacion@caribemagico.co",
        "phone": "+57 605 642 1100",
        "credit_enabled": True,
        "credit_limit": Decimal("15000000"),
        "payment_terms_days": 30,
        "contacts": [
            {
                "name": "Daniela Ospina",
                "role": "Ejecutiva de cuenta",
                "email": "daniela.ospina@caribemagico.co",
                "phone": "+57 310 555 2231",
            }
        ],
        "notes": "Agencia receptiva: envía vouchers con el número de reserva. Tarifa neta (sin comisión).",
    },
    "port": {
        "kind": "corporate",
        "legal_name": "Inversiones Portuarias del Caribe S.A.S.",
        "trade_name": "Portuarias del Caribe",
        "nit": "901345678",
        "vat_responsible": True,
        "tax_responsibilities": ["O-13", "O-15", "O-23"],
        "address": "Manga, Calle 29 #24-10, Edificio Terminal Piso 5",
        "city": "Cartagena",
        "department": "Bolívar",
        "billing_email": "cuentasporpagar@portuariascaribe.co",
        "phone": "+57 605 660 8800",
        "credit_enabled": True,
        "credit_limit": Decimal("40000000"),
        "payment_terms_days": 45,
        "contacts": [
            {
                "name": "Mauricio Salgado",
                "role": "Jefe de compras",
                "email": "msalgado@portuariascaribe.co",
                "phone": "+57 315 555 7788",
            },
            {
                "name": "Paola Ríos",
                "role": "Tesorería",
                "email": "tesoreria@portuariascaribe.co",
                "phone": "+57 605 660 8812",
            },
        ],
        "notes": "Exige orden de compra en cada reserva. Radicar facturas en el portal de proveedores.",
    },
    "tech": {
        "kind": "corporate",
        "legal_name": "Tecnologías Andinas del Norte Ltda.",
        "trade_name": "TecAndina",
        "nit": "830512946",
        "vat_responsible": True,
        "tax_responsibilities": ["O-47"],
        "address": "Carrera 7 #71-21, Torre B Of. 902",
        "city": "Bogotá",
        "department": "Cundinamarca",
        "billing_email": "facturas@tecandina.co",
        "phone": "+57 601 745 3300",
        "credit_enabled": True,
        "credit_limit": Decimal("10000000"),
        "payment_terms_days": 30,
        "contacts": [
            {
                "name": "Natalia Cárdenas",
                "role": "Viajes corporativos",
                "email": "viajes@tecandina.co",
                "phone": "+57 320 555 1144",
            }
        ],
        "notes": "",
    },
}

BOOKERS = {
    "agency_past": ("Laura Marcela", "Quintero Gil", "1037612345", "laura.quintero@gmail.com"),
    "agency_future": ("Juan David", "Pardo Salazar", "80123456", "jdpardo@hotmail.com"),
    "port_past": ("Andrés Felipe", "Morales Rendón", "1045678901", "amorales@portuariascaribe.co"),
    "port_house": ("Camila Andrea", "Rojas Duque", "1143987654", "crojas@portuariascaribe.co"),
    "tech_past": ("Sebastián", "Ortiz Medina", "1020456789", "sortiz@tecandina.co"),
}


def seed(ctx) -> None:
    prop = ctx.properties.get("aurora")
    if prop is None:
        return
    if Company.objects.filter(organization=prop.organization).exists():
        ctx.log(f"  corporate: {prop.organization.name} ya tiene empresas, se omite")
        return
    with transaction.atomic():
        stats = CorporateSeeder(ctx, prop).run()
    ctx.log(
        f"  corporate {prop.name}: {stats['companies']} empresas, {stats['reservations']} reservas, "
        f"{stats['invoices']} facturas, {stats['payments']} pagos a cuenta"
    )


class CorporateSeeder:
    def __init__(self, ctx, prop):
        self.ctx, self.prop = ctx, prop
        self.today = prop.business_date
        self.tz = ZoneInfo(prop.timezone or "America/Bogota")
        self.stats = {"companies": 0, "reservations": 0, "invoices": 0, "payments": 0}
        self.plan = (
            RatePlan.objects.filter(property=prop, code="FLEX").first()
            or RatePlan.objects.filter(property=prop, kind="base", is_active=True).first()
        )
        self.room_types = list(
            RoomType.objects.filter(property=prop, is_active=True, kind="private").order_by(
                "sort_order", "code"
            )
        )

    def run(self) -> dict:
        companies = {key: self._company(values) for key, values in COMPANIES.items()}
        agency, port, tech = companies["agency"], companies["port"], companies["tech"]

        # Past stays (checked out), billed to the companies.
        port_past = self._stay(
            "port_past",
            port,
            checkin=self.today - timedelta(days=15),
            nights=3,
            routing=["all"],
            po="OC-4521",
        )
        agency_past = self._stay(
            "agency_past",
            agency,
            checkin=self.today - timedelta(days=47),
            nights=2,
            routing=["lodging"],
            po="VCM-2187",
        )
        tech_past = self._stay(
            "tech_past", tech, checkin=self.today - timedelta(days=27), nights=2, routing=["all"], po=""
        )
        if agency_past is not None:  # the guest paid the breakfasts at check-out (card terminal)
            self._guest_extras(agency_past, nights=2)
        past = [reservation for reservation in (port_past, agency_past, tech_past) if reservation is not None]
        for reservation in sorted(past, key=lambda item: item.checkout_date):  # numbers in date order
            self._finish(reservation)

        # In house now: lodging to the company, the guest pays the rest; a business dinner split 50/50.
        port_house = self._stay(
            "port_house",
            port,
            checkin=self.today - timedelta(days=2),
            nights=4,
            routing=["lodging"],
            po="OC-4630",
            state="in_house",
        )
        if port_house is not None:
            self._guest_extras(port_house, nights=2, pay=False)
            self._split_dinner(port_house, port)

        # Future stay billed entirely to the agency (voucher).
        self._stay(
            "agency_future",
            agency,
            checkin=self.today + timedelta(days=10),
            nights=3,
            routing=["all"],
            po="VCM-2210",
            state="future",
        )

        # Legacy invoices (opening balances) and payments on account.
        services.add_opening_balance(
            agency, self.prop, amount=Decimal("1850000"), document_date=self.today - timedelta(days=75),
            reference="FV-2024-0891", description="Saldo inicial · factura FV-2024-0891 (sistema anterior)",
        )  # fmt: skip
        port_legacy = services.add_opening_balance(
            port, self.prop, amount=Decimal("3200000"), document_date=self.today - timedelta(days=118),
            reference="FE-1187", description="Saldo inicial · factura FE-1187 (sistema anterior)",
        )  # fmt: skip
        self._account_payment(
            port, amount=Decimal("1500000"), days_ago=20, reference="TRF 88412033",
            allocations=[(port_legacy, Decimal("1200000"))], notes="Abono a la FE-1187; el resto a favor",
        )  # fmt: skip
        if tech_past is not None:
            folio = tech_past.folios.filter(folio_type="company").first()
            balance = finance.folio_balance(folio) if folio is not None else Decimal("0")
            if balance > 0:
                self._account_payment(
                    tech,
                    amount=balance,
                    days_ago=5,
                    reference="TRF 00458812",
                    allocations=[(folio, balance)],
                    notes="Pago total de la factura",
                )
        return self.stats

    # --- companies ------------------------------------------------------------------------------------------

    def _company(self, values) -> Company:
        company = Company.objects.create(
            organization=self.prop.organization, dv=check_digit(values["nit"]), **values
        )
        self.stats["companies"] += 1
        return company

    # --- reservations ---------------------------------------------------------------------------------------

    def _booker(self, key):
        first, last, document, email = BOOKERS[key]
        return upsert_guest(
            self.prop.organization,
            GuestInput(
                first_name=first,
                last_name=last,
                email=email,
                phone="+57 300 555 " + document[-4:],
                document_type="CC",
                document_number=document,
                nationality="CO",
                country_of_residence="CO",
                city_of_residence="Cartagena" if key != "tech_past" else "Bogotá",
                data_processing_consent=True,
            ),
        )

    def _free_unit(self, checkin, checkout):
        units = load_units(self.prop, [room_type.pk for room_type in self.room_types], checkin, checkout)
        for room_type in self.room_types:
            for unit in units.get(room_type.pk, []):
                if unit.bed is None and unit.is_free(checkin, checkout):
                    return room_type, unit
        return None, None

    def _stay(self, key, company, *, checkin, nights, routing, po, state="past"):
        """Book a unit free on those nights (shifting a few days when the hotel is full), bill it to the
        company and bring it to its state."""
        booker = self._booker(key)
        for shift in (0, 1, -1, 2, -2, 3, -3, 4):
            start = checkin + timedelta(days=shift)
            if state == "past" and start + timedelta(days=nights) >= self.today:
                continue
            if state == "in_house" and not (start < self.today < start + timedelta(days=nights)):
                continue
            if state == "future" and start <= self.today:
                continue
            end = start + timedelta(days=nights)
            room_type, unit = self._free_unit(start, end)
            if unit is None:
                continue
            request = ReservationRequest(
                property=self.prop,
                booker=booker,
                stays=[
                    StayRequest(
                        room_type_id=room_type.pk,
                        rate_plan_id=self.plan.pk,
                        checkin=start,
                        checkout=end,
                        adults=min(2, room_type.max_adults),
                        room_id=unit.room.pk,
                    )
                ],
                source="email" if company.kind == "travel_agency" else "phone",
                enforce_restrictions=False,
                guarantee="none",
                notes=f"Reserva corporativa · {company.display_name}",
            )
            try:
                with transaction.atomic():
                    reservation = create_reservation(request, source_label="system")
                    self._backdate(reservation, lead_days=12)
                    services.set_billing(
                        reservation, bill_to="company", company=company, routing=routing, purchase_order=po
                    )
                    if state in ("past", "in_house"):
                        self._arrive(reservation, leave=state == "past")
            except DomainError as exc:
                self.ctx.log(f"    corporate: omitida {key} {start}: {exc.message}")
                continue
            self.stats["reservations"] += 1
            return Reservation.objects.get(pk=reservation.pk)
        self.ctx.log(f"    corporate: sin habitación libre para {key}")
        return None

    def _backdate(self, reservation, *, lead_days) -> None:
        created = datetime.combine(
            reservation.checkin_date - timedelta(days=lead_days), time(10, 30), self.tz
        )
        Reservation.objects.filter(pk=reservation.pk).update(created_at=min(created, datetime.now(self.tz)))

    def _arrive(self, reservation, *, leave: bool) -> None:
        """Check in (and out, for past stays) with `force`, keeping today's housekeeping state of the room."""
        for stay in Stay.objects.filter(reservation=reservation).select_related("room"):
            before = (
                Room.objects.filter(pk=stay.room_id).values_list("housekeeping_status", flat=True).first()
            )
            check_in(stay, force=True)
            Stay.objects.filter(pk=stay.pk).update(
                checked_in_at=datetime.combine(stay.checkin_date, time(15, 40), self.tz)
            )
            if leave:
                check_out(stay, force=True)
                Stay.objects.filter(pk=stay.pk).update(
                    checked_out_at=datetime.combine(stay.checkout_date, time(10, 5), self.tz)
                )
            else:
                post_room_charges(stay, until_date=self.today, source="system")
            if before is not None:
                Room.objects.filter(pk=stay.room_id).update(housekeeping_status=before)

    def _guest_extras(self, reservation, *, nights, pay=True) -> None:
        """Breakfasts on the guest's folio (not routed: the company pays only the lodging)."""
        extra = Extra.objects.filter(property=self.prop, code="BREAKFAST", is_active=True).first()
        if extra is None:
            return
        guest_folio = finance.get_or_create_folio(reservation)
        if guest_folio.status != "open":
            return
        stay = reservation.stays.first()
        for offset in range(nights):
            finance.post_extra_charge(
                guest_folio, extra, quantity=stay.adults if stay else 1, source="system"
            )
            day = reservation.checkin_date + timedelta(days=offset + 1)
            charge = guest_folio.charges.order_by("-created_at").first()
            if charge is not None and day <= self.today:
                type(charge).objects.filter(pk=charge.pk).update(business_date=day)
        if pay:
            due = finance.folio_balance(guest_folio)
            if due > 0:
                payment = finance.record_payment(
                    guest_folio, amount=due, method="card_terminal", reference="VOUCHER-DESAYUNOS"
                )
                Payment.objects.filter(pk=payment.pk).update(business_date=reservation.checkout_date)

    def _split_dinner(self, reservation, company) -> None:
        tax = Tax.objects.filter(property=self.prop, code="IVA-EXTRAS", is_active=True).first()
        guest_folio = finance.get_or_create_folio(reservation)
        company_folio = finance.get_or_create_company_folio(reservation, company)
        with finance.explicit_folio():
            dinner = finance.post_charge(
                guest_folio,
                kind="fee",
                amount=Decimal("180000"),
                description="Cena de negocios · restaurante La Muralla",
                tax=tax,
                source="system",
                business_date=self.today - timedelta(days=1),
            )
        finance.split_charge(
            dinner,
            amount=(dinner.amount + dinner.tax_amount) / 2,
            to_folio=company_folio,
            reason="Acuerdo con la empresa: paga la mitad de la cena de negocios",
        )

    def _finish(self, reservation) -> None:
        """Company invoices of a past stay, dated at its check-out (only with an active DIAN resolution)."""
        from apps.compliance.models import InvoiceResolution
        from apps.compliance.services import invoices as invoice_service

        if not InvoiceResolution.objects.filter(
            property=self.prop, document_kind="invoice", is_active=True
        ).exists():
            return
        moment = datetime.combine(reservation.checkout_date, time(11, 20), self.tz)
        try:
            issued = invoice_service.issue_reservation_invoices(
                reservation, source="automation", issued_at=moment, render=False
            )
        except DomainError as exc:
            self.ctx.log(f"    corporate: sin factura para {reservation.code}: {exc.message}")
            return
        self.stats["invoices"] += len(issued)

    # --- payments on account --------------------------------------------------------------------------------

    def _account_payment(self, company, *, amount, days_ago, reference, allocations, notes) -> None:
        received = self.today - timedelta(days=days_ago)
        payment = services.record_account_payment(
            company,
            self.prop,
            amount=amount,
            method="bank_transfer",
            reference=reference,
            notes=notes,
            received_on=received,
            allocations=[{"folio_id": folio.pk, "amount": value} for folio, value in allocations],
        )
        # the money arrived that day: the folio payments carry it as their business date too
        Payment.objects.filter(account_allocation__account_payment=payment).update(business_date=received)
        AccountPayment.objects.filter(pk=payment.pk).update(
            created_at=datetime.combine(received, time(9, 15), self.tz)
        )
        self.stats["payments"] += 1
