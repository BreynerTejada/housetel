"""End-to-end smoke through the Vite proxy, like the SPA: cookie jar + CSRF (B-INT/C-INT/P-INT; `make smoke`).

login owner@casaaurora.co → Today board (C1) → rooms → rate grid → offers → create a tentative reservation →
its folio → simulated payment link → the public simulated gateway approves it → the reservation is confirmed
and the payment recorded → its guest-portal link opens the public portal (C5) → BookSim books two nights and
the reservation arrives in the PMS through the channel, then the OTA cancels it (C3) → a WhatsApp message from
the simulator lands in the inbox (C6) → phase P: runtime config and readiness (P1); forgot password and email
verification (P2); a 2-room booking that opens a group, an allotment, a pickup from it and its release (P3);
companies, a statement and the receivables (P4); a guests import in dry-run, then discarded (P5); the
retention automation, the revenue rounding reason, the iCal SSRF guard and a legal page (P6) → logout.
Standard library only, runs on the host: `python3 backend/scripts/smoke_proxy.py [base_url]`.
It leaves in the demo data one confirmed reservation (booker "Smoke Integración", 30 % deposit), one cancelled
BookSim reservation ("Smoke Canal"), one WhatsApp conversation (+57 300 555 0101, "Smoke WhatsApp") and two
cancelled group reservations (booker "Smoke Grupo"; their group is deleted).
"""

import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
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


def call_multipart(path, fields, files, *, prop=None, expect=(201,)):
    """POST multipart/form-data (the importer's upload): `files` = {name: (filename, bytes, content type)}."""
    global requests_made
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    for name, (filename, content, content_type) in files.items():
        head = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        )
        parts.append(head.encode() + content + b"\r\n")
    data = b"".join(parts) + f"--{boundary}--\r\n".encode()
    headers = {
        "Accept": "application/json",
        "Origin": BASE,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "X-CSRFToken": cookie("csrftoken") or "",
    }
    if prop:
        headers["X-Property-Id"] = prop
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method="POST")
    try:
        with opener.open(request, timeout=60) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    requests_made += 1
    payload = json.loads(raw) if raw[:1] in (b"{", b"[") else raw.decode(errors="replace")[:200]
    print(f"{'OK ' if status in expect else 'ERR'} {status} POST {path} (multipart)")
    if status not in expect:
        print("    ", json.dumps(payload, ensure_ascii=False)[:600])
        raise SystemExit(1)
    return payload


def page_status(path):
    """Status of an SPA page as a browser asks for it (Accept: text/html)."""
    global requests_made
    request = urllib.request.Request(BASE + path, headers={"Accept": "text/html"})
    try:
        with opener.open(request, timeout=60) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    requests_made += 1
    print(f"{'OK ' if status == 200 else 'ERR'} {status} GET {path} (page)")
    return status


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
    phase_p(pid, today, after)

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


def phase_p(pid, today, reservation):
    """Phase P (pilot): a few steps per task, read-only or cleaned up (P-INT)."""
    # P1: the runtime facts the SPA reads, and the readiness probe (database + Redis).
    config = call("GET", "/api/v1/public/core/config/")
    check(
        "simulations_enabled" in config and config["environment"] in ("development", "production"),
        "the runtime config does not answer",
    )
    ready = call("GET", "/api/v1/public/core/health/ready/")
    check(ready["status"] == "ok", "the readiness probe is not ok")
    print(
        f"    runtime: {config['environment']} · simulations {config['simulations_enabled']} · "
        f"public URL {config['public_base_url']} · ready"
    )

    # P2: "forgot password" answers the same whether the account exists or not; demo users are verified and a
    # resend sends nothing; a tampered verification link is rejected.
    same = call("POST", "/api/v1/public/accounts/password/forgot/", {"email": "nadie-smoke@example.com"})
    check("detail" in same, "forgot password does not answer 200")
    me = call("GET", "/api/v1/accounts/me/")
    check(me.get("email_verified") is True, "the demo owner is not verified")
    resent = call("POST", "/api/v1/accounts/me/verify-email/resend/")
    check(resent["sent"] is False and resent["email_verified"] is True, "a verified account got a new link")
    bad = call("POST", "/api/v1/public/accounts/verify-email/", {"token": "x"}, expect=(400,))
    check(bad["code"] == "invalid_token", "a tampered verification link was accepted")
    print("    accounts: forgot password 200 · owner verified · tampered link rejected")

    # P3: a 2-room booking that opens a group → an allotment of 2 → a room picked up from it (general
    # availability does not move) → release (the unpicked unit goes back on sale) → clean up.
    def free_units(room_type_id, checkin, checkout):
        query = f"checkin={checkin}&checkout={checkout}"
        offers = call("GET", f"/api/v1/bookings/room-offers/?{query}", prop=pid)
        units = [o["available_units"] for o in offers if o["room_type_id"] == room_type_id]
        return max(units) if units else 0

    offer, checkin = None, today
    for days in range(120, 240, 7):
        checkin = today + timedelta(days=days)
        query = f"checkin={checkin}&checkout={checkin + timedelta(days=2)}"
        offers = call("GET", f"/api/v1/bookings/room-offers/?{query}", prop=pid)
        offer = next(
            (o for o in offers if o["available_units"] >= 5 and o["room_type"]["kind"] == "private"), None
        )
        if offer:
            break
    check(offer is not None, "no category with 5 free rooms in the next 240 days")
    checkout = checkin + timedelta(days=2)
    room_type_id = offer["room_type_id"]
    baseline = free_units(room_type_id, checkin, checkout)
    stay = {
        "room_type_id": room_type_id,
        "rate_plan_id": offer["rate_plan_id"],
        "checkin": str(checkin),
        "checkout": str(checkout),
        "adults": 2,
    }
    booker = {
        "first_name": "Smoke",
        "last_name": "Grupo",
        "email": "smoke.grupo@example.com",
        "phone": "+573001112244",
        "document_type": "CC",
        "document_number": "1012345699",
        "nationality": "CO",
        "country_of_residence": "CO",
        "data_processing_consent": True,
    }
    body = {"booker": booker, "stays": [stay, stay], "source": "phone", "group_name": "Smoke Grupo Fase P"}
    grouped = call("POST", "/api/v1/bookings/reservations/", body, prop=pid, expect=(201,))
    check(len(grouped["stays"]) == 2 and grouped["group"], "the 2-room booking did not open its group")
    group_id = grouped["group"]["id"]
    block_body = {
        "room_type_id": room_type_id,
        "start": str(checkin),
        "end": str(checkout),
        "units": 2,
        "release_date": str(max(today, checkin - timedelta(days=7))),
    }
    block = call("POST", f"/api/v1/bookings/groups/{group_id}/blocks/", block_body, prop=pid, expect=(201,))
    held = free_units(room_type_id, checkin, checkout)
    check(held == baseline - 4, f"the allotment did not hold 2 rooms ({baseline} → {held})")
    pickup_body = {
        "booker_id": grouped["booker"]["id"],
        "stays": [{**stay, "group_block_id": block["id"]}],
        "source": "phone",
        "enforce_restrictions": False,
    }
    pickup = call("POST", "/api/v1/bookings/reservations/", pickup_body, prop=pid, expect=(201,))
    check(free_units(room_type_id, checkin, checkout) == held, "a pickup took general availability")
    detail = call("GET", f"/api/v1/bookings/groups/{group_id}/", prop=pid)
    picked = detail["blocks"][0]["pickup"]["picked_rooms"]
    check(picked == 1 and len(detail["rooming"]) == 3, "the group does not show its pickup and rooming list")
    call("POST", f"/api/v1/bookings/blocks/{block['id']}/release/", {}, prop=pid)
    check(
        free_units(room_type_id, checkin, checkout) == held + 1, "the release did not free the unpicked room"
    )
    cancel = {"reason": "Smoke Fase P", "waive_fee": True, "confirm": True}
    for reservation_id in (grouped["id"], pickup["id"]):
        call("POST", f"/api/v1/bookings/reservations/{reservation_id}/cancel/", cancel, prop=pid)
    call("DELETE", f"/api/v1/bookings/groups/{group_id}/", prop=pid, expect=(204,))
    check(free_units(room_type_id, checkin, checkout) == baseline, "the availability did not come back")
    print(
        f"    group: {grouped['code']} (2 rooms) + allotment of 2 + pickup {pickup['code']} → released, "
        "cancelled and deleted; availability back to the start"
    )

    # P4: the seed's companies, one statement with its aging, the receivables and a reservation's billing tab.
    companies = call("GET", "/api/v1/corporate/companies/", prop=pid)["results"]
    check(companies, "the corporate seed left no companies")
    statement = call("GET", f"/api/v1/corporate/companies/{companies[0]['id']}/statement/", prop=pid)
    check({"current", "d31_60", "d61_90", "d90_plus"} <= set(statement["aging"]), "a statement without aging")
    receivables = call("GET", "/api/v1/corporate/receivables/", prop=pid)
    check(receivables["companies"], "no company in the receivables")
    billing = call("GET", f"/api/v1/corporate/reservations/{reservation['id']}/billing/", prop=pid)
    check(billing["billing"]["bill_to"] in ("guest", "company"), "no billing tab for the reservation")
    print(
        f"    corporate: {len(companies)} companies · receivables {receivables['totals']['balance']} · "
        f"billing tab of {reservation['code']}: {billing['billing']['bill_to']}"
    )

    # P5: a small guests CSV through the importer's dry-run (nothing is saved), then the job is discarded.
    csv = "Nombre;Apellido;Email;Documento\nSmoke;Importación;smoke.import@example.com;1099887766\n".encode()
    job = call_multipart(
        "/api/v1/imports/jobs/",
        {"kind": "guests", "preset": "generic", "source_label": "Smoke"},
        {"file": ("smoke-huespedes.csv", csv, "text/csv")},
        prop=pid,
    )
    job = call("PATCH", f"/api/v1/imports/jobs/{job['id']}/", {"mapping": job["mapping"]}, prop=pid)
    check(job["status"] == "validated" and job["counts"].get("error", 0) == 0, "the import did not validate")
    call("POST", f"/api/v1/imports/jobs/{job['id']}/dry-run/", {}, prop=pid, expect=(202,))
    for _ in range(60):
        job = call("GET", f"/api/v1/imports/jobs/{job['id']}/", prop=pid)
        if job["status"] == "validated" and job["dry_run_at"]:
            break
        time.sleep(1)
    summary = job.get("dry_run_summary") or {}
    check(job["dry_run_at"] and summary.get("fail", 0) == 0, "the import dry-run did not finish cleanly")
    call("DELETE", f"/api/v1/imports/jobs/{job['id']}/", prop=pid, expect=(204,))
    print(f"    import: guests CSV dry-run {summary} → discarded")

    # P6: Habeas Data retention (180 days by default), the revenue rounding reason, the iCal guard against
    # internal addresses and the public legal pages.
    retention = call("GET", "/api/v1/control/automations/guests.purge_identity_documents/", prop=pid)
    days = (retention.get("params") or {}).get("retention_days")
    check(days == 180, f"retention_days is {days}, not 180")
    simulated = call("POST", "/api/v1/revenue/simulate/", {}, prop=pid)
    rounded = [
        rec
        for rec in simulated["recommendations"]
        if any(reason.get("kind") == "rounding" for reason in rec.get("reasons") or [])
    ]
    check(rounded, "no recommendation explains its rounding")
    ical = {
        "channel_code": "ical",
        "name": "Smoke iCal interno",
        "room_mappings": [{"room_type": room_type_id, "ical_import_url": "https://10.0.0.5/cal.ics"}],
    }
    refused = call("POST", "/api/v1/distribution/connections/", ical, prop=pid, expect=(400,))
    check("red interna" in json.dumps(refused, ensure_ascii=False), "an internal iCal URL was accepted")
    check(page_status("/legal/privacidad") == 200, "the privacy policy page does not open")
    print(
        f"    P6: retention {days} days · {len(rounded)} recommendations with rounding · "
        "iCal to 10.0.0.5 refused · /legal/privacidad 200"
    )


if __name__ == "__main__":
    main()
