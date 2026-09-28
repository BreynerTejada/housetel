"""`today_board(property)` — the numbers and lists of the Today panel (plan C1), by business date.

Definitions (business date `bd`):
- arrivals: stays arriving on `bd` (tentative, confirmed, or already checked in/out = done); pending stays
  whose arrival already passed are listed as `late_arrival` but not counted.
- departures: checked-in stays leaving on `bd` (pending) or checked out with checkout on `bd` (done);
  checked-in stays whose checkout already passed are listed as `overdue` but not counted.
- in house: every checked-in stay.
- occupancy: stays confirmed / in house / checked out covering the night `bd` (C10 definition) over the
  sellable units of the night (InventoryDay total − blocked). Tentative stays are not sold.
- room revenue: net of the night `bd` per sold stay (the posted room charge, else the night's `net`); other
  revenue: net of non-room, non-voided charges with business date `bd`. ADR = room revenue / occupied.
"""

from datetime import date
from decimal import Decimal

import pytest
from freezegun import freeze_time

from apps.bookings.services.reservations import check_in
from apps.bookings.tests.helpers import oct_
from apps.finance.services import get_or_create_folio, post_charge, record_payment, void_charge
from apps.frontdesk.services.today import today_board
from apps.frontdesk.tests.helpers import (
    arrived,
    cancelled,
    departed,
    eta,
    fresh,
    new_stay,
    no_show,
    vip_booker,
)
from apps.guests.models import Guest
from apps.inventory.services import block_room

pytestmark = pytest.mark.django_db


@pytest.fixture
def day(hotel, owner):
    """Business date 2026-10-01 at the front desk of `hotel` (see the module docstring of test_today)."""
    stays = {}
    stays["J"] = cancelled(hotel, oct_(1), oct_(2))  # cancelled arrival: nowhere
    stays["K"] = no_show(hotel, oct_(0), oct_(1))  # no-show of yesterday: nowhere; its fee is today's
    stays["E"] = new_stay(hotel, oct_(0), oct_(2), room=hotel.rooms["102"])  # late arrival
    booker = vip_booker()
    stays["A"] = new_stay(hotel, oct_(1), oct_(3), room=hotel.rooms["101"], booker=booker, eta=eta(15, 30))
    Guest.objects.filter(pk=stays["A"].reservation.booker_id).update(is_vip=True)
    stays["B"] = new_stay(hotel, oct_(1), oct_(2))  # arrival without room
    stays["C"] = new_stay(hotel, oct_(1), oct_(4), room_type=hotel.ste, room=hotel.rooms["301"])
    check_in(stays["C"])  # arrived today
    stays["D"] = new_stay(hotel, oct_(1), oct_(2), room_type=hotel.dorm_type, status="tentative")
    beds = hotel.beds
    stays["F"] = arrived(
        hotel, date(2026, 9, 29), oct_(1), room_type=hotel.dorm_type, room=hotel.dorm, bed=beds["A"]
    )
    stays["G"] = departed(
        hotel, date(2026, 9, 29), oct_(1), room_type=hotel.dorm_type, room=hotel.dorm, bed=beds["B"]
    )
    stays["H"] = arrived(
        hotel, date(2026, 9, 28), oct_(0), room_type=hotel.dorm_type, room=hotel.dorm, bed=beds["C"]
    )
    stays["I"] = arrived(hotel, oct_(0), oct_(4), room_type=hotel.dorm_type, room=hotel.dorm, bed=beds["D"])

    folio = get_or_create_folio(stays["A"].reservation)
    post_charge(folio, kind="extra", amount=Decimal("50000"), description="Minibar", actor=owner)
    wrong = post_charge(folio, kind="fee", amount=Decimal("20000"), description="Error", actor=owner)
    void_charge(wrong, reason="Cargado por error", actor=owner, confirm=True)
    record_payment(folio, amount=Decimal("111600"), method="bank_transfer", reference="TRX-1", actor=owner)
    return {key: fresh(stay) for key, stay in stays.items()}


def by_code(rows):
    return {row["code"]: row for row in rows}


def codes(stays, *keys):
    return {stays[key].reservation.code for key in keys}


class TestKpis:
    def test_counters_revenue_and_occupancy_of_the_business_date(self, hotel, day):
        board = today_board(hotel.prop)

        assert board["business_date"] == "2026-10-01"
        assert board["currency"] == "COP"
        assert board["kpis"] == {
            "occupancy_pct": 62.5,
            "rooms_occupied": 5,
            "rooms_available": 8,
            "rooms_blocked": 0,
            "rooms_free": 3,
            "arrivals_total": 4,
            "arrivals_done": 1,
            "arrivals_late": 1,
            "departures_total": 2,
            "departures_done": 1,
            "departures_overdue": 1,
            "in_house": 4,
            "guests_in_house": 5,
            "room_revenue_today": "1675000.00",
            "other_revenue_today": "430800.00",
            "revenue_today": "2105800.00",
            "adr_today": "335000.00",
            "collected_today": "111600.00",
        }

    def test_a_block_takes_its_units_out_of_the_sellable_capacity(
        self, hotel, django_capture_on_commit_callbacks
    ):
        new_stay(hotel, oct_(1), oct_(2), room=hotel.rooms["101"])
        with django_capture_on_commit_callbacks(execute=True):  # bookings rebuilds InventoryDay on commit
            block_room(hotel.rooms["201"], start=oct_(1), end=oct_(3), kind="maintenance", reason="Pintura")

        kpis = today_board(hotel.prop)["kpis"]

        assert (kpis["rooms_available"], kpis["rooms_blocked"], kpis["rooms_occupied"]) == (7, 1, 1)
        assert kpis["occupancy_pct"] == 14.3
        assert kpis["rooms_free"] == 6

    def test_an_empty_hotel_has_zero_everywhere(self, hotel):
        kpis = today_board(hotel.prop)["kpis"]

        assert kpis["occupancy_pct"] == 0.0
        assert (kpis["rooms_occupied"], kpis["rooms_available"]) == (0, 8)
        assert kpis["revenue_today"] == "0.00"
        assert kpis["adr_today"] == "0.00"

    def test_a_posted_room_charge_counts_instead_of_the_planned_night(self, hotel, owner):
        stay = arrived(hotel, oct_(0), oct_(3), room=hotel.rooms["101"])
        folio = get_or_create_folio(stay.reservation)
        post_charge(
            folio,
            kind="room",
            amount=Decimal("300000"),
            description="Noche con descuento",
            stay=stay,
            night_date=oct_(1),
            actor=owner,
            business_date=oct_(1),
        )

        kpis = today_board(hotel.prop)["kpis"]

        assert kpis["room_revenue_today"] == "300000.00"
        assert kpis["other_revenue_today"] == "0.00"


class TestArrivals:
    def test_arrivals_of_the_day_with_their_readiness_and_issues(self, hotel, day):
        rows = by_code(today_board(hotel.prop)["arrivals"])

        assert set(rows) == codes(day, "A", "B", "C", "D", "E")
        a = rows[day["A"].reservation.code]
        assert {
            key: a[key]
            for key in (
                "stay_id",
                "reservation_id",
                "status",
                "guest_name",
                "is_vip",
                "room",
                "room_id",
                "bed",
                "room_status",
                "eta",
                "checkin",
                "checkout",
                "nights",
                "adults",
                "children",
                "balance",
                "balance_due",
                "online_checkin_done",
                "ready",
                "done",
                "issues",
            )
        } == {
            "stay_id": str(day["A"].pk),
            "reservation_id": str(day["A"].reservation_id),
            "status": "confirmed",
            "guest_name": "Valeria Mejía",
            "is_vip": True,
            "room": "101",
            "room_id": str(hotel.rooms["101"].pk),
            "bed": None,
            "room_status": "clean",
            "eta": "15:30",
            "checkin": "2026-10-01",
            "checkout": "2026-10-03",
            "nights": 2,
            "adults": 2,
            "children": 0,
            "balance": "700000.00",
            "balance_due": "700000.00",
            "online_checkin_done": False,
            "ready": True,
            "done": False,
            "issues": [],
        }
        assert a["room_type"]["code"] == "DBL"
        b = rows[day["B"].reservation.code]
        assert (b["room"], b["ready"], b["issues"]) == (None, False, ["unassigned"])
        c = rows[day["C"].reservation.code]
        assert (c["status"], c["done"], c["room"], c["issues"]) == ("checked_in", True, "301", [])
        d = rows[day["D"].reservation.code]
        assert (d["status"], d["ready"], d["issues"]) == ("tentative", False, ["tentative", "unassigned"])
        e = rows[day["E"].reservation.code]
        assert (e["room"], e["ready"], e["issues"]) == ("102", False, ["late_arrival"])

    def test_a_dirty_room_is_not_ready(self, hotel):
        stay = new_stay(hotel, oct_(1), oct_(2), room=hotel.rooms["101"])
        hotel.rooms["101"].housekeeping_status = "dirty"
        hotel.rooms["101"].save(update_fields=["housekeeping_status"])

        (row,) = today_board(hotel.prop)["arrivals"]

        assert row["stay_id"] == str(stay.pk)
        assert (row["room_status"], row["ready"], row["issues"]) == ("dirty", False, ["room_not_ready"])

    def test_pending_arrivals_come_before_the_ones_already_in_house(self, hotel):
        done = new_stay(hotel, oct_(1), oct_(2), room=hotel.rooms["101"])
        check_in(done)
        waiting = new_stay(hotel, oct_(1), oct_(2), room=hotel.rooms["102"])

        rows = today_board(hotel.prop)["arrivals"]

        assert [row["stay_id"] for row in rows] == [str(waiting.pk), str(done.pk)]


class TestDeparturesAndInHouse:
    def test_departures_of_the_day_and_overdue_ones(self, hotel, day):
        rows = by_code(today_board(hotel.prop)["departures"])

        assert set(rows) == codes(day, "F", "G", "H")
        f = rows[day["F"].reservation.code]
        assert (f["status"], f["done"], f["room"], f["bed"]) == ("checked_in", False, "D1", "A")
        assert (f["balance_due"], f["issues"]) == ("154700.00", ["balance_due"])
        g = rows[day["G"].reservation.code]
        assert (g["status"], g["done"], g["issues"]) == ("checked_out", True, ["balance_due"])
        h = rows[day["H"].reservation.code]
        assert (h["done"], h["issues"]) == (False, ["overdue", "balance_due"])

    def test_every_guest_in_house_is_listed(self, hotel, day):
        rows = by_code(today_board(hotel.prop)["in_house"])

        assert set(rows) == codes(day, "C", "F", "H", "I")
        assert rows[day["F"].reservation.code]["departs_today"] is True
        assert rows[day["I"].reservation.code]["departs_today"] is False
        assert rows[day["H"].reservation.code]["issues"] == ["overdue"]
        assert rows[day["I"].reservation.code]["issues"] == []

    def test_a_paid_departure_has_no_issue(self, hotel, owner):
        stay = arrived(hotel, oct_(0), oct_(1), room=hotel.rooms["101"])
        folio = get_or_create_folio(stay.reservation)
        record_payment(folio, amount=Decimal("380800"), method="bank_transfer", actor=owner)

        (row,) = today_board(hotel.prop)["departures"]

        assert (row["balance"], row["balance_due"], row["issues"]) == ("0.00", "0.00", [])


class TestRack:
    """`rooms`: the key rack of the house tonight, one entry per active room (by floor, then room order)."""

    def test_every_room_with_who_is_in_it_and_who_arrives(self, hotel, day):
        rooms = {room["number"]: room for room in today_board(hotel.prop)["rooms"]}

        assert [room["number"] for room in today_board(hotel.prop)["rooms"]] == [
            "101",
            "102",
            "D1",
            "201",
            "301",
        ]
        a, e, c = day["A"], day["E"], day["C"]
        assert rooms["101"] == {
            "id": str(hotel.rooms["101"].pk),
            "number": "101",
            "floor": "1",
            "room_type": {
                "id": str(hotel.dbl.pk),
                "code": "DBL",
                "color": hotel.dbl.color,
                "kind": "private",
            },
            "housekeeping_status": "clean",
            "blocked": False,
            "occupant": None,
            "arrival": {
                "stay_id": str(a.pk),
                "reservation_id": str(a.reservation_id),
                "guest_name": "Valeria Mejía",
                "checkin": "2026-10-01",
                "late": False,
            },
            "beds": None,
        }
        assert rooms["102"]["arrival"]["stay_id"] == str(e.pk)
        assert rooms["102"]["arrival"]["late"] is True
        assert rooms["301"]["occupant"] == {
            "stay_id": str(c.pk),
            "reservation_id": str(c.reservation_id),
            "guest_name": c.reservation.booker.full_name,
            "checkout": "2026-10-04",
            "departing": False,
        }
        assert rooms["301"]["arrival"] is None
        assert (rooms["201"]["occupant"], rooms["201"]["arrival"]) == (None, None)

    def test_a_dorm_counts_its_beds(self, hotel, day):
        rooms = {room["number"]: room for room in today_board(hotel.prop)["rooms"]}

        dorm = rooms["D1"]
        assert (dorm["occupant"], dorm["arrival"], dorm["housekeeping_status"]) == (None, None, "dirty")
        # beds A (leaves today), C (overdue) and D (stays) are in house; B checked out this morning
        assert dorm["beds"] == {"total": 4, "occupied": 3, "departing": 2, "arriving": 0, "blocked": 0}

    def test_a_guest_due_out_is_marked_departing(self, hotel):
        stay = arrived(hotel, oct_(0), oct_(1), room=hotel.rooms["201"])

        (room,) = [room for room in today_board(hotel.prop)["rooms"] if room["number"] == "201"]

        assert room["occupant"]["stay_id"] == str(stay.pk)
        assert room["occupant"]["departing"] is True

    def test_a_blocked_room_is_marked(self, hotel, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            block_room(hotel.rooms["201"], start=oct_(1), end=oct_(3), kind="maintenance", reason="Pintura")
            block_room(
                hotel.dorm,
                start=oct_(1),
                end=oct_(2),
                kind="maintenance",
                reason="Litera",
                bed=hotel.beds["A"],
            )

        rooms = {room["number"]: room for room in today_board(hotel.prop)["rooms"]}

        assert rooms["201"]["blocked"] is True
        assert rooms["101"]["blocked"] is False
        assert rooms["D1"]["beds"]["blocked"] == 1

    def test_inactive_rooms_are_not_on_the_rack(self, hotel):
        hotel.rooms["201"].is_active = False
        hotel.rooms["201"].save(update_fields=["is_active"])

        numbers = [room["number"] for room in today_board(hotel.prop)["rooms"]]

        assert "201" not in numbers


class TestOnlineCheckin:
    def test_without_the_guest_portal_model_nobody_checked_in_online(self, hotel, monkeypatch):
        from apps.frontdesk.services import today

        def missing(app_label, model_name):
            raise LookupError(model_name)

        stay = new_stay(hotel, oct_(1), oct_(2))
        monkeypatch.setattr(today.django_apps, "get_model", missing)

        assert today.online_checkins_done({stay.reservation_id}) == set()
        assert today_board(hotel.prop)["arrivals"][0]["online_checkin_done"] is False

    def test_a_completed_online_checkin_marks_the_arrival(self, hotel):
        from django.apps import apps as django_apps

        try:
            online_checkin = django_apps.get_model("guestportal", "OnlineCheckin")
        except LookupError:
            pytest.skip("guestportal.OnlineCheckin no existe todavía (C5)")
        done = new_stay(hotel, oct_(1), oct_(2))
        waiting = new_stay(hotel, oct_(1), oct_(2))
        online_checkin.objects.create(reservation=done.reservation, status="completed")

        rows = {row["stay_id"]: row for row in today_board(hotel.prop)["arrivals"]}

        assert rows[str(done.pk)]["online_checkin_done"] is True
        assert rows[str(waiting.pk)]["online_checkin_done"] is False


class TestScope:
    def test_other_properties_do_not_leak(self, hotel, organization):
        from apps.bookings.tests.helpers import build_hotel
        from apps.core.tests.factories import PropertyFactory

        other = build_hotel(PropertyFactory(organization=organization))
        new_stay(other, oct_(1), oct_(2), room=other.rooms["101"])

        board = today_board(hotel.prop)

        assert board["arrivals"] == []
        assert board["kpis"]["rooms_occupied"] == 0

    def test_the_night_audit_is_due_when_the_business_date_is_behind_the_calendar(self, hotel):
        with freeze_time("2026-10-02 08:00:00-05:00"):
            late = today_board(hotel.prop)
        with freeze_time("2026-10-01 23:00:00-05:00"):
            on_time = today_board(hotel.prop)

        assert (late["calendar_date"], late["night_audit"]["due"]) == ("2026-10-02", True)
        assert (on_time["calendar_date"], on_time["night_audit"]["due"]) == ("2026-10-01", False)
        assert late["night_audit"]["last_report"] is None


class TestYesterday:
    """`previous`: the closed figures of the day before (its night audit report), to compare against."""

    def test_the_figures_of_the_last_closed_day(self, hotel):
        from apps.frontdesk.models import NightAuditReport

        NightAuditReport.objects.create(
            property=hotel.prop,
            business_date=date(2026, 9, 30),
            status="completed",
            summary={
                "figures": {
                    "occupancy_pct": 50.0,
                    "rooms_occupied": 4,
                    "adr": "300000.00",
                    "revenue": "1400000.00",
                    "room_revenue": "1200000.00",
                }
            },
        )

        previous = today_board(hotel.prop)["previous"]

        assert previous == {
            "business_date": "2026-09-30",
            "occupancy_pct": 50.0,
            "rooms_occupied": 4,
            "adr": "300000.00",
            "revenue": "1400000.00",
        }

    def test_nothing_to_compare_without_the_report_of_the_day_before(self, hotel):
        from apps.frontdesk.models import NightAuditReport

        NightAuditReport.objects.create(
            property=hotel.prop,
            business_date=date(2026, 9, 20),
            status="completed",
            summary={"figures": {"occupancy_pct": 10.0}},
        )

        assert today_board(hotel.prop)["previous"] is None
