"""Copilot tools: read tools return the hotel's real data (scoped to the property and filtered by the user's
permissions); action tools only create a proposal."""

import pytest

from apps.ai.copilot.tools import ToolContext, available_tools, run_tool
from apps.ai.models import CopilotAction, CopilotSession
from apps.bookings.models import Reservation
from apps.bookings.services.reservations import check_in
from apps.bookings.tests.helpers import book, build_hotel, oct_

pytestmark = pytest.mark.django_db

READ_TOOLS = {
    "get_today_summary",
    "list_arrivals",
    "list_departures",
    "search_reservations",
    "get_reservation",
    "check_availability",
    "get_occupancy",
    "find_guest",
    "get_balance",
    "list_alerts",
    "get_rates",
}
ACTION_TOOLS = {
    "create_reservation",
    "move_room",
    "check_in",
    "check_out",
    "send_message",
    "block_room",
    "add_extra",
}


@pytest.fixture
def hotel(prop):
    return build_hotel(prop)  # business date 2026-10-01; DBL 101/102/201, STE 301, DORM D1 (4 beds)


@pytest.fixture
def session(hotel, owner):
    return CopilotSession.objects.create(property=hotel.prop, user=owner)


def ctx(user, prop, session=None, lang="es"):
    return ToolContext(property=prop, user=user, session=session, lang=lang)


def names(user, prop):
    return {tool.name for tool in available_tools(user, prop)}


# ---- permissions ----------------------------------------------------------------------------------------


def test_the_tools_offered_follow_the_user_permissions(hotel, make_member):
    owner, front, accountant, housekeeper = (
        make_member(role) for role in ("owner", "front_desk", "accountant", "housekeeping")
    )

    assert names(owner, hotel.prop) == READ_TOOLS | ACTION_TOOLS
    assert names(front, hotel.prop) == READ_TOOLS | ACTION_TOOLS - {"block_room"}
    assert names(accountant, hotel.prop) == READ_TOOLS | {"add_extra"}
    assert names(housekeeper, hotel.prop) == set()


def test_a_tool_the_user_cannot_use_is_refused(hotel, make_member):
    front = make_member("front_desk")

    output = run_tool(ctx(front, hotel.prop), "block_room", {"room_number": "101"})

    assert "error" in output
    assert not CopilotAction.objects.exists()


# ---- read tools -----------------------------------------------------------------------------------------


def test_list_arrivals_returns_todays_arrivals_with_room_and_balance(hotel, owner):
    arriving = book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["101"].pk})
    book(hotel, oct_(2), oct_(4))

    data = run_tool(ctx(owner, hotel.prop), "list_arrivals", {})

    assert (data["date"], data["count"]) == ("2026-10-01", 1)
    (item,) = data["items"]
    assert (item["code"], item["guest"], item["rooms"], item["balance"], item["status"]) == (
        arriving.code,
        "Laura Gómez",
        ["101"],
        "761600.00",
        "confirmed",
    )
    assert item["room_status"] == "clean"


def test_list_arrivals_of_another_date(hotel, owner):
    tomorrow = book(hotel, oct_(2), oct_(4))

    data = run_tool(ctx(owner, hotel.prop), "list_arrivals", {"date": "2026-10-02"})

    assert [item["code"] for item in data["items"]] == [tomorrow.code]
    assert data["items"][0]["rooms"] == []


def test_list_departures_shows_who_leaves_and_owes(hotel, owner):
    staying = book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["102"].pk})
    check_in(staying.stays.get(), actor=owner)

    data = run_tool(ctx(owner, hotel.prop), "list_departures", {"date": "2026-10-03"})

    (item,) = data["items"]
    assert (item["code"], item["rooms"], item["status"]) == (staying.code, ["102"], "checked_in")


def test_today_summary_counts_arrivals_departures_in_house_and_occupancy(hotel, owner):
    first = book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["101"].pk})
    book(hotel, oct_(1), oct_(2))
    check_in(first.stays.get(), actor=owner)

    data = run_tool(ctx(owner, hotel.prop), "get_today_summary", {})

    assert data["date"] == "2026-10-01"
    assert data["arrivals"] == {"total": 2, "done": 1}
    assert data["departures"] == {"total": 0, "done": 0}
    assert data["in_house"] == 1
    assert (data["units_sold"], data["units_total"], data["occupancy_pct"]) == (2, 8, 25.0)


def test_check_availability_gives_the_cheapest_offer_per_category(hotel, owner):
    book(hotel, oct_(12), oct_(14))

    data = run_tool(
        ctx(owner, hotel.prop),
        "check_availability",
        {"checkin": "2026-10-12", "checkout": "2026-10-14", "adults": 2},
    )

    options = {option["room_type_code"]: option for option in data["options"]}
    assert (options["DBL"]["available"], options["DBL"]["total"]) == (2, "761600.00")
    assert options["STE"]["total"] == "1547000.00"
    assert (data["nights"], data["adults"]) == (2, 2)


def test_check_availability_explains_invalid_dates(hotel, owner):
    output = run_tool(
        ctx(owner, hotel.prop), "check_availability", {"checkin": "2026-10-14", "checkout": "2026-10-12"}
    )

    assert "error" in output


def test_get_occupancy_by_night(hotel, owner):
    book(hotel, oct_(5), oct_(7))
    book(hotel, oct_(6), oct_(7))

    data = run_tool(ctx(owner, hotel.prop), "get_occupancy", {"start": "2026-10-05", "end": "2026-10-07"})

    assert [(night["date"], night["sold"], night["total"]) for night in data["nights"]] == [
        ("2026-10-05", 1, 8),
        ("2026-10-06", 2, 8),
    ]
    assert data["average_pct"] == 18.8


def test_get_balance_of_a_reservation(hotel, owner):
    reservation = book(hotel, oct_(3), oct_(5))

    data = run_tool(ctx(owner, hotel.prop), "get_balance", {"code": reservation.code.lower()})

    assert (data["code"], data["balance"], data["total"], data["paid"]) == (
        reservation.code,
        "761600.00",
        "761600.00",
        "0.00",
    )


def test_get_reservation_and_search_reservations(hotel, owner):
    reservation = book(hotel, oct_(3), oct_(5), notes="Aniversario")

    detail = run_tool(ctx(owner, hotel.prop), "get_reservation", {"code": reservation.code})
    found = run_tool(ctx(owner, hotel.prop), "search_reservations", {"query": "gómez"})

    assert (detail["code"], detail["checkin"], detail["checkout"], detail["nights"], detail["notes"]) == (
        reservation.code,
        "2026-10-03",
        "2026-10-05",
        2,
        "Aniversario",
    )
    assert [item["code"] for item in found["items"]] == [reservation.code]


def test_reservations_of_another_property_are_invisible(hotel, owner, organization):
    from apps.core.tests.factories import PropertyFactory

    other = build_hotel(PropertyFactory(organization=organization))
    foreign = book(other, oct_(3), oct_(5))

    output = run_tool(ctx(owner, hotel.prop), "get_reservation", {"code": foreign.code})

    assert "error" in output


def test_find_guest_only_searches_the_organization(hotel, owner):
    from apps.core.tests.factories import OrganizationFactory
    from apps.guests.tests.factories import GuestFactory

    GuestFactory(organization=hotel.prop.organization, first_name="Mariana", last_name="Ríos")
    GuestFactory(organization=OrganizationFactory(), first_name="Mariana", last_name="Otra")

    data = run_tool(ctx(owner, hotel.prop), "find_guest", {"query": "mariana"})

    assert [item["name"] for item in data["items"]] == ["Mariana Ríos"]


def test_list_alerts_shows_the_open_alerts_of_the_property(hotel, owner, organization):
    from apps.core.alerts import raise_alert, resolve_alert
    from apps.core.tests.factories import PropertyFactory

    raise_alert(
        property=hotel.prop, kind="x", severity="critical", title="Sobreventa", message="", dedupe_key="a"
    )
    raise_alert(property=hotel.prop, kind="x", severity="info", title="Resuelta", message="", dedupe_key="b")
    resolve_alert(hotel.prop, "b")
    raise_alert(
        property=PropertyFactory(organization=organization),
        kind="x",
        severity="info",
        title="Ajena",
        message="",
        dedupe_key="c",
    )

    data = run_tool(ctx(owner, hotel.prop), "list_alerts", {})

    assert [(item["title"], item["severity"]) for item in data["items"]] == [("Sobreventa", "critical")]


def test_get_rates_by_night(hotel, owner):
    data = run_tool(
        ctx(owner, hotel.prop), "get_rates", {"start": "2026-10-12", "end": "2026-10-14", "room_type": "dbl"}
    )

    (room_type,) = data["room_types"]
    assert room_type["code"] == "DBL"
    assert [(night["date"], night["price"]) for night in room_type["nights"]] == [
        ("2026-10-12", "320000.00"),
        ("2026-10-13", "320000.00"),
    ]


# ---- action tools: proposals ---------------------------------------------------------------------------


def test_create_reservation_only_proposes(hotel, owner, session):
    output = run_tool(
        ctx(owner, hotel.prop, session),
        "create_reservation",
        {
            "checkin": "2026-10-12",
            "checkout": "2026-10-14",
            "adults": 2,
            "room_type": "DBL",
            "guest_name": "Ana Pérez",
            "guest_email": "ana@example.com",
        },
    )

    proposal = output["proposal"]
    action = CopilotAction.objects.get(pk=proposal["id"])
    assert (action.status, action.action_code, action.permission) == (
        "proposed",
        "create_reservation",
        "bookings.manage",
    )
    assert "Ana Pérez" in action.summary
    assert (action.details["total"], action.details["nights"], action.details["room_type_code"]) == (
        "761600.00",
        2,
        "DBL",
    )
    assert action.params["room_type_id"] == str(hotel.dbl.pk)
    assert not Reservation.objects.exists()


def test_create_reservation_without_availability_is_explained(hotel, owner, session):
    for _ in range(3):
        book(hotel, oct_(12), oct_(14))

    output = run_tool(
        ctx(owner, hotel.prop, session),
        "create_reservation",
        {"checkin": "2026-10-12", "checkout": "2026-10-14", "room_type": "DBL", "guest_name": "Ana Pérez"},
    )

    assert "error" in output
    assert not CopilotAction.objects.exists()


def test_move_room_proposal_flags_a_category_change(hotel, owner, session):
    reservation = book(hotel, oct_(3), oct_(5), stay_kwargs={"room_id": hotel.rooms["101"].pk})

    output = run_tool(
        ctx(owner, hotel.prop, session),
        "move_room",
        {"reservation_code": reservation.code, "room_number": "301"},
    )

    action = CopilotAction.objects.get(pk=output["proposal"]["id"])
    assert (action.details["from_room"], action.details["to_room"], action.details["category_change"]) == (
        "101",
        "301",
        True,
    )
    assert reservation.stays.get().room == hotel.rooms["101"]  # not moved yet


def test_check_in_proposal_warns_about_a_dirty_room(hotel, owner, session):
    from apps.inventory.services import set_housekeeping_status

    reservation = book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["101"].pk})
    set_housekeeping_status(hotel.rooms["101"], "dirty")

    output = run_tool(ctx(owner, hotel.prop, session), "check_in", {"reservation_code": reservation.code})

    action = CopilotAction.objects.get(pk=output["proposal"]["id"])
    assert action.details["warnings"]
    assert reservation.stays.get().status == "confirmed"


def test_an_unknown_reservation_code_is_an_error_not_a_proposal(hotel, owner, session):
    output = run_tool(ctx(owner, hotel.prop, session), "check_out", {"reservation_code": "HT-ZZZZZZ"})

    assert "error" in output
    assert not CopilotAction.objects.exists()
