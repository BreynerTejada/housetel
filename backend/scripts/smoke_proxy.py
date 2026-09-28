"""End-to-end smoke through the Vite proxy, like the SPA: cookie jar + CSRF (plan B-INT/C-INT; `make smoke`).

login owner@casaaurora.co → Today board (C1) → rooms → rate grid → offers → create a tentative reservation →
its folio → simulated payment link → the public simulated gateway approves it → the reservation is confirmed
and the payment recorded → its guest-portal link opens the public portal (C5) → BookSim books two nights and
the reservation arrives in the PMS through the channel, then the OTA cancels it (C3) → a WhatsApp message from
the simulator lands in the inbox (C6) → logout. Standard library only, runs on the host:
`python3 backend/scripts/smoke_proxy.py [base_url]`.
It leaves in the demo data one confirmed reservation (booker "Smoke Integración", 30 % deposit), one cancelled
BookSim reservation ("Smoke Canal") and one WhatsApp conversation (+57 300 555 0101, "Smoke WhatsApp").
"""

import http.cookiejar
import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from decimal import Decimal

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5173"
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
requests_made = 0


def cookie(name):
    return next((c.value for c in jar if c.name == name), None)


def call(method, path, body=None, *, prop=None, expect=(200,)):
    return call_status(method, path, body, prop=prop, expect=expect)[1]


def call_status(method, path, body=None, *, prop=None, expect=(200,)):
    """(status, payload); any status outside `expect` stops the smoke (so a caller can accept a 409)."""
    global requests_made
    headers = {"Accept": "application/json", "Origin": BASE}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if method != "GET" and cookie("csrftoken"):
        headers["X-CSRFToken"] = cookie("csrftoken")
    if prop:
        headers["X-Property-Id"] = prop
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with opener.open(request, timeout=60) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    requests_made += 1
    payload = json.loads(raw) if raw[:1] in (b"{", b"[") else raw.decode(errors="replace")[:200]
    print(f"{'OK ' if status in expect else 'ERR'} {status} {method} {path}")
    if status not in expect:
        print("    ", json.dumps(payload, ensure_ascii=False)[:600])
        raise SystemExit(1)
    return status, payload


def check(condition, message):
    if not condition:
        print(f"ERR {message}")
        raise SystemExit(1)


def main():
    call("GET", "/api/v1/accounts/auth/csrf/")
    login = {"email": "owner@casaaurora.co", "password": "housetel123"}
    me = call("POST", "/api/v1/accounts/auth/login/", login)
    prop = me["memberships"][0]["properties"][0]
    pid, today = prop["id"], date.fromisoformat(prop["business_date"])
    print(f"    {me['email']} · {prop['name']} · business date {today}")

    board = call("GET", "/api/v1/frontdesk/today/", prop=pid)
    check(board["business_date"] == str(today) and "kpis" in board, "the Today board does not answer")
    kpis = board["kpis"]
    print(f"    today: {kpis['arrivals_total']} arrivals, {kpis['departures_total']} departures, "
          f"{kpis['in_house']} in house")  # fmt: skip

    rooms = call("GET", "/api/v1/inventory/rooms/", prop=pid)
    check(rooms, "the property has no rooms (is the demo seeded?)")
    print(f"    {len(rooms)} rooms")

    grid = call("GET", f"/api/v1/rates/grid/?start={today}&end={today + timedelta(days=14)}", prop=pid)
    prices = [row["price"] for room_type in grid["room_types"] for row in room_type["rows"]]
    check(len(grid["dates"]) == 14 and all(prices), "the rate grid has nights without a price")
    print(f"    grid {grid['rate_plan']['code']}: {len(grid['room_types'])} categories × 14 nights")

    offers, checkin = [], today
    for days in range(20, 80, 3):
        checkin = today + timedelta(days=days)
        query = f"checkin={checkin}&checkout={checkin + timedelta(days=2)}&adults=2&children=0"
        offers = call("GET", f"/api/v1/bookings/offers/?{query}", prop=pid)
        if offers:
            break
    check(offers, "no offers in the next 80 days")
    offer = offers[0]
    print(f"    cheapest {offer['room_type']['code']}/{offer['rate_plan']['code']} = {offer['total']}")

    booker = {
        "first_name": "Smoke",
        "last_name": "Integración",
        "email": "smoke.bint@example.com",
        "phone": "+573001112233",
        "document_type": "CC",
        "document_number": "1012345678",
        "nationality": "CO",
        "country_of_residence": "CO",
        "data_processing_consent": True,
    }
    stay = {
        "room_type_id": offer["room_type_id"],
        "rate_plan_id": offer["rate_plan_id"],
        "checkin": str(checkin),
        "checkout": str(checkin + timedelta(days=2)),
        "adults": 2,
    }
    body = {"booker": booker, "stays": [stay], "source": "phone", "status": "tentative", "hold_minutes": 120}
    reservation = call("POST", "/api/v1/bookings/reservations/", body, prop=pid, expect=(201,))
    total = Decimal(reservation["total_amount"])
    check(reservation["status"] == "tentative", "the new booking is not tentative")
    check(Decimal(reservation["balance"]) == total, "the new booking does not owe its total")
    print(f"    {reservation['code']} tentative · total {total}")

    folio = call("GET", f"/api/v1/finance/folios/{reservation['folio_id']}/", prop=pid)
    check(Decimal(folio["totals"]["reservation_balance"]) == total, "the folio does not owe the total")

    deposit = (total * Decimal("0.3")).quantize(Decimal("1"))
    link = call(
        "POST", f"/api/v1/finance/folios/{folio['id']}/payment-link/", {"amount": str(deposit)},
        prop=pid, expect=(201,),
    )  # fmt: skip
    reference = link["intent"]["reference"]
    check(link["checkout_url"].endswith(f"/sim/pay/{reference}"), "not a simulated gateway link")

    call("GET", f"/api/v1/public/finance/sim/intents/{reference}/")
    decided = call(
        "POST", f"/api/v1/public/finance/sim/intents/{reference}/decide/",
        {"outcome": "approved", "method": "card"},
    )  # fmt: skip
    status = call("GET", f"/api/v1/public/finance/intents/{reference}/status/")
    check(decided["status"] == "approved" and status["paid"] is True, "the payment was not approved")

    after = call("GET", f"/api/v1/bookings/reservations/{reservation['id']}/", prop=pid)
    folio = call("GET", f"/api/v1/finance/folios/{folio['id']}/", prop=pid)
    payments = [p for p in folio["payments"] if p["status"] == "approved"]
    check(after["status"] == "confirmed" and after["hold_expires_at"] is None, "the payment did not confirm")
    check(len(payments) == 1 and Decimal(payments[0]["amount"]) == deposit, "not recorded exactly once")
    check(Decimal(after["balance"]) == total - deposit, "the balance does not include the deposit")
    method = payments[0]["method"]
    print(f"    {after['code']} confirmed · paid {deposit} ({method}) · balance {after['balance']}")

    phase_c(pid, today, after)

    call("POST", "/api/v1/accounts/auth/logout/", expect=(204,))
    call("GET", "/api/v1/accounts/me/", expect=(401,))
    print(f"SMOKE OK · {requests_made} requests · reservation {after['code']}")


def phase_c(pid, today, reservation):
    # C5: the booking's guest-portal link opens its public portal (no session needed: the token is the key).
    link = call("GET", f"/api/v1/guestportal/reservations/{reservation['id']}/link/", prop=pid)
    token = link["url"].rstrip("/").rsplit("/", 1)[-1]
    portal = call("GET", f"/api/v1/public/guestportal/{token}/")
    check(portal["reservation"]["code"] == reservation["code"], "the portal shows another booking")
    print(f"    portal {portal['reservation']['code']}: check-in online {portal['checkin']['status']}")

    # C3: BookSim books two nights → the reservation arrives through the channel; then the OTA cancels it.
    connections = call("GET", "/api/v1/distribution/connections/", prop=pid)
    booksim = next((c for c in connections if c["channel_code"] == "booksim"), None)
    check(booksim is not None and booksim["status"] == "active", "no active BookSim connection")
    rate = booksim["rate_mappings"][0]["external_rate_id"]
    ota, checkin = None, today
    for room in booksim["room_mappings"]:
        for days in range(40, 100, 4):
            checkin = today + timedelta(days=days)
            body = {
                "external_room_id": room["external_room_id"],
                "external_rate_id": rate,
                "checkin": str(checkin),
                "checkout": str(checkin + timedelta(days=2)),
                "adults": 2,
                "children": 0,
                "guest": {"first_name": "Smoke", "last_name": "Canal", "email": "smoke.canal@example.com",
                          "country": "US"},
            }  # fmt: skip
            path = f"/api/v1/distribution/simulator/{booksim['id']}/bookings/"
            status, created = call_status("POST", path, body, prop=pid, expect=(201, 409))
            if status == 201:
                ota = created
                break
        if ota:
            break
    check(ota is not None, "BookSim found no sellable nights in the next 100 days")
    pms = ota["reservation"]
    check(
        ota["pms_status"] == "imported" and pms and pms["status"] == "confirmed",
        "the OTA booking did not import",
    )
    imported = call("GET", f"/api/v1/bookings/reservations/{pms['id']}/", prop=pid)
    check(imported["source"] == "ota" and imported["channel_code"] == "booksim", "not an OTA reservation")
    cancel = f"/api/v1/distribution/simulator/{booksim['id']}/bookings/{ota['external_id']}/cancel/"
    call("POST", cancel, {}, prop=pid)
    cancelled = call("GET", f"/api/v1/bookings/reservations/{pms['id']}/", prop=pid)
    check(cancelled["status"] == "cancelled", "the OTA cancellation did not cancel the PMS reservation")
    print(f"    BookSim {ota['external_id']} → {pms['code']} imported, then cancelled by the OTA")

    # C6: a WhatsApp message from the simulator opens (or reopens) an unread conversation in the inbox.
    before = call("GET", "/api/v1/messaging/conversations/unread-count/", prop=pid)
    inbound = {"phone": "+573005550101", "body": "Hola, ¿tienen parqueadero?", "name": "Smoke WhatsApp"}
    sent = call("POST", "/api/v1/messaging/simulator/whatsapp/inbound/", inbound, prop=pid, expect=(201,))
    unread = call("GET", "/api/v1/messaging/conversations/unread-count/", prop=pid)
    check(unread["messages"] > before["messages"], "the WhatsApp message did not reach the inbox")
    thread = call("GET", f"/api/v1/messaging/conversations/{sent['conversation_id']}/", prop=pid)
    check(thread["channel"] == "whatsapp", "the message landed in a non-WhatsApp thread")
    print(
        f"    WhatsApp inbox: {unread['conversations']} unread conversations, {unread['messages']} messages"
    )


if __name__ == "__main__":
    main()
