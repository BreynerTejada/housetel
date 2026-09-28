"""SIRE (Migración Colombia): bulk-upload file of foreigners' entries (E) and exits (S), missing data."""

from datetime import date, timedelta

import pytest

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.compliance.models import SireRecord, SireReport
from apps.compliance.services.config import get_settings
from apps.compliance.services.sire import (
    generate_sire,
    lodged_guests,
    mark_submitted,
    sire_daily_file,
    split_surnames,
)
from apps.core import integrations
from apps.core.errors import DomainError
from apps.core.models import Alert
from apps.guests.tests.factories import GuestFactory

pytestmark = pytest.mark.django_db

START, END = date(2026, 10, 10), date(2026, 10, 12)


def foreigner(prop, first, last, number, nationality, birth, **extra):
    return GuestFactory(
        organization=prop.organization,
        first_name=first,
        last_name=last,
        document_type="PA",
        document_number=number,
        nationality=nationality,
        country_of_residence=nationality,
        birth_date=birth,
        **extra,
    )


def stay_for(prop, booker, checkin, checkout, status, occupants=()):
    reservation = ReservationFactory(
        property=prop, booker=booker, status=status, checkin_date=checkin, checkout_date=checkout
    )
    return StayFactory(
        reservation=reservation,
        checkin_date=checkin,
        checkout_date=checkout,
        status=status,
        occupants=list(occupants),
    )


@pytest.fixture
def world(hotel):
    """John (US) with his companion Emily stayed 10→12; María (ES) arrived on the 11th and is in house; a
    Colombian and a French guest without birth date also stayed."""
    settings = get_settings(hotel)
    settings.sire_establishment_code = "123456"
    settings.sire_city_code = "13001"
    settings.save()
    john = foreigner(hotel, "John Michael", "Smith Brown", "X1234567", "US", date(1985, 3, 2))
    emily = foreigner(hotel, "Emily", "Smith", "X7654321", "US", date(1987, 7, 15))
    maria = foreigner(hotel, "María José", "García", "PAB998877", "ES", date(1990, 12, 24))
    claire = foreigner(hotel, "Claire", "Dubois", "FR112233", "FR", None)
    local = GuestFactory(organization=hotel.organization, nationality="CO", country_of_residence="CO")
    stay_for(hotel, john, START, END, "checked_out", occupants=[emily])
    stay_for(hotel, maria, date(2026, 10, 11), date(2026, 10, 14), "checked_in")
    stay_for(hotel, claire, date(2026, 10, 12), date(2026, 10, 15), "checked_in")
    stay_for(hotel, local, START, END, "checked_out")
    stay_for(hotel, foreigner(hotel, "Ana", "Silva", "BR1", "BR", date(1980, 1, 1)), START, END, "cancelled")
    return {"john": john, "emily": emily, "maria": maria, "claire": claire}


def file_lines(report):
    with report.file.open("rb") as handle:
        content = handle.read().decode("utf-8")
    assert content.endswith("\r\n")
    return content.split("\r\n")[:-1]


class TestFile:
    def test_the_file_has_one_tab_separated_line_per_movement_of_a_foreigner(self, world, hotel):
        report = generate_sire(hotel, START, END)

        assert file_lines(report) == [
            "123456\t13001\t3\tX7654321\t249\tSMITH\tEMILY\tE\t10/10/2026\t249\t13001\t15/07/1987",
            "123456\t13001\t3\tX1234567\t249\tSMITH BROWN\tJOHN MICHAEL\tE\t10/10/2026\t249\t13001\t02/03/1985",  # noqa: E501
            "123456\t13001\t3\tPAB998877\t245\tGARCIA\tMARIA JOSE\tE\t11/10/2026\t245\t13001\t24/12/1990",
            "123456\t13001\t3\tX7654321\t249\tSMITH\tEMILY\tS\t12/10/2026\t13001\t249\t15/07/1987",
            "123456\t13001\t3\tX1234567\t249\tSMITH BROWN\tJOHN MICHAEL\tS\t12/10/2026\t13001\t249\t02/03/1985",  # noqa: E501
        ]
        assert report.records_count == 5
        assert (report.period_start, report.period_end, report.status) == (START, END, "generated")

    def test_the_13_column_layout_splits_the_surnames(self, world, hotel):
        settings = get_settings(hotel)
        settings.sire_second_surname_column = True
        settings.save()

        lines = file_lines(generate_sire(hotel, START, END))

        assert lines[1] == (
            "123456\t13001\t3\tX1234567\t249\tSMITH\tBROWN\tJOHN MICHAEL\tE\t10/10/2026\t249\t13001\t02/03/1985"  # noqa: E501
        )
        assert lines[0].split("\t")[5:8] == ["SMITH", "", "EMILY"]

    def test_hotel_overrides_of_the_code_tables_are_used(self, world, hotel):
        settings = get_settings(hotel)
        settings.sire_document_codes = {"PA": "30"}
        settings.sire_country_codes = {"us": "840"}
        settings.save()

        line = file_lines(generate_sire(hotel, START, END))[0].split("\t")

        assert (line[2], line[4], line[9]) == ("30", "840", "840")

    def test_the_travel_data_of_the_online_checkin_sets_origin_and_destination(self, world, hotel):
        from apps.guestportal.models import OnlineCheckin

        john = world["john"]
        reservation = john.reservations.get()
        OnlineCheckin.objects.create(
            reservation=reservation,
            status="completed",
            data={
                "travel": {
                    str(john.pk): {"travel_reason": "leisure", "origin": "Bogotá", "destination": "Medellín"}
                }
            },
        )

        lines = [
            line.split("\t") for line in file_lines(generate_sire(hotel, START, END)) if "X1234567" in line
        ]

        assert [(cols[7], cols[9], cols[10]) for cols in lines] == [
            ("E", "11001", "13001"),
            ("S", "13001", "05001"),
        ]


class TestMissingData:
    def test_incomplete_guests_stay_out_of_the_file_and_are_listed_with_an_alert(self, world, hotel):
        report = generate_sire(hotel, START, END)

        record = SireRecord.objects.get(report=report, guest=world["claire"])
        assert (record.complete, record.missing_fields, record.movement) == (False, ["birth_date"], "E")
        assert not any("FR112233" in line for line in file_lines(report))
        [missing] = report.missing
        assert (missing["guest_name"], missing["fields"], missing["movement"]) == (
            "Claire Dubois",
            ["birth_date"],
            "E",
        )
        alert = Alert.objects.get(
            property=hotel, dedupe_key="compliance:sire:missing", resolved_at__isnull=True
        )
        assert alert.severity == "warning"
        assert alert.data["count"] == 1

    def test_without_the_establishment_code_every_row_is_incomplete(self, world, hotel):
        settings = get_settings(hotel)
        settings.sire_establishment_code = ""
        settings.save()

        report = generate_sire(hotel, START, END)

        assert report.records_count == 0
        assert all("establishment" in r.missing_fields for r in report.records.all())

    def test_a_report_without_missing_data_resolves_the_alert(self, world, hotel):
        generate_sire(hotel, START, END)
        world["claire"].birth_date = date(1992, 5, 5)
        world["claire"].save()

        report = generate_sire(hotel, START, END)

        assert report.missing == []
        assert not Alert.objects.filter(
            dedupe_key="compliance:sire:missing", resolved_at__isnull=True
        ).exists()


class TestSubmission:
    def test_in_simulated_mode_marking_it_submitted_gets_an_acknowledgement(self, world, hotel, owner):
        report = generate_sire(hotel, START, END)

        report = mark_submitted(report, actor=owner)

        assert report.status == "acknowledged"
        assert report.ack_code.startswith("SIRE-")
        assert report.submitted_by == owner and report.submitted_at is not None

    def test_in_real_mode_it_records_the_manual_upload_and_the_receipt_typed_by_the_user(self, world, hotel):
        setting = integrations.get_setting(hotel, "sire")
        setting.mode = "real"
        setting.save()
        report = generate_sire(hotel, START, END)

        submitted = mark_submitted(report)
        assert (submitted.status, submitted.ack_code) == ("submitted", "")
        acknowledged = mark_submitted(submitted, ack_code="MC-2026-000123")
        assert (acknowledged.status, acknowledged.ack_code) == ("acknowledged", "MC-2026-000123")

    def test_an_acknowledged_report_cannot_be_submitted_again(self, world, hotel):
        report = mark_submitted(generate_sire(hotel, START, END))

        with pytest.raises(DomainError) as caught:
            mark_submitted(report)

        assert (caught.value.code, caught.value.status_code) == ("invalid_state", 409)

    def test_an_invalid_period_is_rejected(self, hotel):
        with pytest.raises(DomainError) as caught:
            generate_sire(hotel, END, START)

        assert caught.value.code == "invalid_period"


class TestDailyAutomation:
    def test_it_generates_yesterdays_file_once(self, world, hotel):
        hotel.business_date = date(2026, 10, 13)
        hotel.save()

        first = sire_daily_file(hotel)
        second = sire_daily_file(hotel)

        report = SireReport.objects.get(property=hotel)
        assert (report.period_start, report.period_end) == (date(2026, 10, 12), date(2026, 10, 12))
        assert first["status"] == "generated" and second["status"] == "skipped"
        assert Alert.objects.filter(
            dedupe_key="compliance:sire:unsubmitted", resolved_at__isnull=True
        ).exists()

    def test_a_day_without_foreigners_creates_no_file(self, hotel):
        hotel.business_date = date(2026, 1, 2)
        hotel.save()

        assert sire_daily_file(hotel)["status"] == "skipped"
        assert not SireReport.objects.exists()

    def test_submitting_the_last_pending_file_resolves_the_alert(self, world, hotel):
        hotel.business_date = date(2026, 10, 13)
        hotel.save()
        sire_daily_file(hotel)

        mark_submitted(SireReport.objects.get(property=hotel))

        assert not Alert.objects.filter(
            dedupe_key="compliance:sire:unsubmitted", resolved_at__isnull=True
        ).exists()


class TestGuests:
    def test_the_booker_and_the_occupants_are_lodged_in_the_first_stay(self, hotel):
        booker = GuestFactory(organization=hotel.organization)
        friend = GuestFactory(organization=hotel.organization)
        reservation = ReservationFactory(property=hotel, booker=booker)
        first = StayFactory(reservation=reservation, occupants=[friend])
        second = StayFactory(reservation=reservation)

        assert lodged_guests(first) == [booker, friend]
        assert lodged_guests(second) == []

    def test_a_booker_registered_in_another_stay_is_not_repeated(self, hotel):
        booker = GuestFactory(organization=hotel.organization)
        reservation = ReservationFactory(property=hotel, booker=booker)
        first = StayFactory(reservation=reservation)
        second = StayFactory(reservation=reservation, occupants=[booker])

        assert lodged_guests(first) == []
        assert lodged_guests(second) == [booker]

    @pytest.mark.parametrize(
        ("last_name", "surnames"),
        [
            ("Smith Brown", ("SMITH", "BROWN")),
            ("García", ("GARCIA", "")),
            ("de la Hoz Pérez", ("DE LA HOZ", "PEREZ")),
            ("Van der Berg", ("VAN DER BERG", "")),
            ("", ("", "")),
        ],
    )
    def test_surnames_are_split_keeping_particles_together(self, last_name, surnames):
        assert split_surnames(last_name) == surnames


def test_the_report_period_is_inclusive(world, hotel):
    report = generate_sire(hotel, START, START)

    assert [(r.movement, r.movement_date) for r in report.records.filter(complete=True)] == [
        ("E", START),
        ("E", START),
    ]
    assert report.period_end - report.period_start == timedelta(0)
