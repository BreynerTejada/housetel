"""TRA (Tarjeta de Registro Alojamiento, MinCIT): one registration per guest at check-in, companions."""

import json
from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest
import respx

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.compliance.models import TraRegistration
from apps.compliance.providers import SimulatedTraProvider
from apps.compliance.services.config import get_settings
from apps.compliance.services.tra import register_stay, retry_pending_tra, retry_registration
from apps.core import integrations, signals
from apps.core.errors import DomainError
from apps.core.models import Alert, AuditEvent
from apps.guests.tests.factories import GuestFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def stay(hotel, room):
    """Laura (booker) and her partner Andrés checked in to room 101 for two nights."""
    laura = GuestFactory(
        organization=hotel.organization,
        first_name="Laura",
        last_name="Gómez Díaz",
        document_type="CC",
        document_number="52123456",
        nationality="CO",
        country_of_residence="CO",
        city_of_residence="Bogotá",
    )
    andres = GuestFactory(
        organization=hotel.organization,
        first_name="Andrés",
        last_name="Ruiz",
        document_type="CC",
        document_number="80111222",
        nationality="CO",
        country_of_residence="CO",
        city_of_residence="Medellín",
    )
    checkin = hotel.business_date
    reservation = ReservationFactory(
        property=hotel,
        booker=laura,
        status="checked_in",
        checkin_date=checkin,
        checkout_date=checkin + timedelta(days=2),
    )
    return StayFactory(
        reservation=reservation,
        room=room,
        status="checked_in",
        occupants=[andres],
        total_amount=Decimal("761600"),
    )


def registrations(stay):
    return list(TraRegistration.objects.filter(stay=stay).order_by("-is_main", "created_at"))


def check_in(stay, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        signals.send_on_commit(signals.stay_checked_in, stay=stay)


class TestCheckIn:
    def test_every_guest_of_the_stay_gets_a_tra_at_check_in(self, stay, django_capture_on_commit_callbacks):
        check_in(stay, django_capture_on_commit_callbacks)

        main, companion = registrations(stay)
        assert (main.guest, main.is_main, main.status) == (stay.reservation.booker, True, "registered")
        assert main.tra_number.startswith("TRA-") and main.registered_at is not None
        assert (companion.is_main, companion.parent, companion.status) == (False, main, "registered")
        assert companion.mode == "simulated"
        assert AuditEvent.objects.filter(action="compliance.tra_registered").count() == 2

    def test_the_payload_carries_the_mincit_fields(self, stay, hotel, django_capture_on_commit_callbacks):
        check_in(stay, django_capture_on_commit_callbacks)

        main, companion = registrations(stay)
        assert main.payload == {
            "tipo_identificacion": "CC",
            "numero_identificacion": "52123456",
            "nombres": "Laura",
            "apellidos": "Gómez Díaz",
            "cuidad_residencia": "Bogotá",
            "cuidad_procedencia": "Bogotá",
            "numero_habitacion": "101",
            "motivo": "Vacaciones, recreo y ocio",
            "numero_acompanantes": 1,
            "check_in": stay.checkin_date.isoformat(),
            "check_out": stay.checkout_date.isoformat(),
            "tipo_acomodacion": "Hotel",
            "costo": 761600.0,
            "nombre_establecimiento": "Casa Aurora Hoteles S.A.S.",
            "rnt_establecimiento": "98765",
        }
        assert companion.payload == {
            "tipo_identificacion": "CC",
            "numero_identificacion": "80111222",
            "nombres": "Andrés",
            "apellidos": "Ruiz",
            "cuidad_residencia": "Medellín",
            "cuidad_procedencia": "Medellín",
            "numero_habitacion": "101",
            "check_in": stay.checkin_date.isoformat(),
            "check_out": stay.checkout_date.isoformat(),
        }

    def test_the_travel_reason_and_origin_of_the_online_checkin_are_used(
        self, stay, django_capture_on_commit_callbacks
    ):
        from apps.guestportal.models import OnlineCheckin

        booker = stay.reservation.booker
        OnlineCheckin.objects.create(
            reservation=stay.reservation,
            status="completed",
            data={
                "travel": {
                    str(booker.pk): {"travel_reason": "business", "origin": "Cali", "destination": "Bogotá"}
                }
            },
        )

        check_in(stay, django_capture_on_commit_callbacks)

        main = registrations(stay)[0]
        assert (main.payload["motivo"], main.payload["cuidad_procedencia"]) == (
            "Negocios y motivos profesionales",
            "Cali",
        )

    def test_registering_twice_does_not_duplicate(self, stay, django_capture_on_commit_callbacks):
        check_in(stay, django_capture_on_commit_callbacks)

        register_stay(stay)

        assert len(registrations(stay)) == 2

    def test_nothing_happens_when_the_hotel_registers_by_hand(
        self, stay, hotel, django_capture_on_commit_callbacks
    ):
        settings = get_settings(hotel)
        settings.tra_auto_register = False
        settings.save()

        check_in(stay, django_capture_on_commit_callbacks)

        assert registrations(stay) == []

    def test_the_demo_seed_replay_registers_nothing(self, stay, django_capture_on_commit_callbacks):
        with signals.seeding():
            check_in(stay, django_capture_on_commit_callbacks)

        assert registrations(stay) == []


class TestMissingData:
    def test_a_guest_without_document_waits_with_the_missing_fields_and_an_alert(self, stay, hotel):
        companion = stay.occupants.get()
        companion.document_type, companion.document_number = "", ""
        companion.save()

        register_stay(stay)

        main, pending = registrations(stay)
        assert main.status == "registered"
        assert (pending.status, pending.missing_fields) == (
            "pending",
            ["tipo_identificacion", "numero_identificacion"],
        )
        assert pending.attempts == 0
        alert = Alert.objects.get(
            property=hotel, dedupe_key="compliance:tra:missing", resolved_at__isnull=True
        )
        assert alert.data["count"] == 1

        companion.document_type, companion.document_number = "CC", "80111222"
        companion.save()
        retried = retry_registration(pending)

        assert (retried.status, retried.missing_fields) == ("registered", [])
        assert not Alert.objects.filter(
            dedupe_key="compliance:tra:missing", resolved_at__isnull=True
        ).exists()

    def test_without_the_rnt_nobody_can_be_registered(self, stay, hotel):
        hotel.rnt_number = ""
        hotel.save()

        register_stay(stay)

        assert {r.status for r in registrations(stay)} == {"pending"}
        assert all("rnt_establecimiento" in r.missing_fields for r in registrations(stay))


class TestFailures:
    def test_a_service_error_is_retried_and_companions_wait_for_the_main_guest(
        self, stay, hotel, monkeypatch
    ):
        failing = {"status": "error", "tra_number": "", "message": "Servicio no disponible", "response": {}}
        monkeypatch.setattr(SimulatedTraProvider, "register", lambda self, payload, parent_number="": failing)

        register_stay(stay)

        main, companion = registrations(stay)
        assert (main.status, main.error, main.attempts) == ("error", "Servicio no disponible", 1)
        assert (companion.status, companion.attempts) == ("pending", 0)
        assert Alert.objects.filter(dedupe_key="compliance:tra:error", resolved_at__isnull=True).exists()

        monkeypatch.undo()
        report = retry_pending_tra(hotel)

        main, companion = registrations(stay)
        assert (main.status, main.attempts) == ("registered", 2)
        assert companion.status == "registered"
        assert report == {"retried": 2, "registered": 2, "failed": 0}
        assert not Alert.objects.filter(dedupe_key="compliance:tra:error", resolved_at__isnull=True).exists()

    def test_a_registered_guest_cannot_be_registered_again(self, stay):
        main = register_stay(stay)[0]

        with pytest.raises(DomainError) as caught:
            retry_registration(main)

        assert (caught.value.code, caught.value.status_code) == ("invalid_state", 409)

    def test_the_automation_leaves_old_stays_alone(self, stay, hotel, monkeypatch):
        failing = {"status": "error", "tra_number": "", "message": "caído", "response": {}}
        monkeypatch.setattr(SimulatedTraProvider, "register", lambda self, payload, parent_number="": failing)
        register_stay(stay)
        monkeypatch.undo()
        hotel.business_date = stay.checkin_date + timedelta(days=30)
        hotel.save()

        assert retry_pending_tra(hotel) == {"retried": 0, "registered": 0, "failed": 0}


class TestMincit:
    @respx.mock
    def test_the_main_guest_and_the_companion_go_to_the_mincit_service(self, stay, hotel):
        setting = integrations.get_setting(hotel, "tra")
        setting.mode = "real"
        setting.save()
        integrations.set_secrets(setting, {"token": "rnt-token"})
        main_route = respx.post("https://pms.mincit.gov.co/one/").mock(
            return_value=httpx.Response(201, json={"code": 991})
        )
        companion_route = respx.post("https://pms.mincit.gov.co/two/").mock(
            return_value=httpx.Response(201, json={"code": 992})
        )

        main, companion = register_stay(stay)

        sent = json.loads(main_route.calls.last.request.content)
        assert (sent["numero_identificacion"], sent["numero_acompanantes"], sent["rnt_establecimiento"]) == (
            "52123456",
            1,
            "98765",
        )
        assert json.loads(companion_route.calls.last.request.content)["padre"] == "991"
        assert (main.tra_number, companion.tra_number) == ("991", "992")
        assert (main.mode, companion.mode) == ("real", "real")


def test_a_dorm_bed_reports_its_room_and_bed(hotel):
    from apps.inventory.tests.factories import BedFactory

    bed = BedFactory(room__room_type__property=hotel, label="C3")
    booker = GuestFactory(
        organization=hotel.organization,
        document_type="PA",
        document_number="X1",
        nationality="US",
        country_of_residence="US",
        city_of_residence="Austin",
    )
    reservation = ReservationFactory(
        property=hotel,
        booker=booker,
        status="checked_in",
        checkin_date=date(2026, 10, 1),
        checkout_date=date(2026, 10, 3),
    )
    stay = StayFactory(
        reservation=reservation, room=bed.room, bed=bed, room_type=bed.room.room_type, status="checked_in"
    )

    [registration] = register_stay(stay)

    assert registration.payload["numero_habitacion"] == f"{bed.room.number}-C3"
    assert registration.payload["tipo_identificacion"] == "PA"
    assert registration.payload["cuidad_residencia"] == "Austin"
