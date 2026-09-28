"""Read-only sweep of the main staff and public endpoints of every module through the Vite proxy (C/P-INT).

Logs in like the SPA (cookie jar + CSRF) as each demo owner, walks their properties and GETs the main
endpoints of every app (phases B, C and P), then the platform admin API and the public APIs (marketplace,
guest portal, chatbot, plans, runtime config and health). Every call must answer 200; the table shows the
status and the latency. Nothing is written. Standard library only, runs on the host:
`python3 backend/scripts/endpoints_sweep.py [base_url]` (`make sweep`).
"""

import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5173"
PASSWORD = "housetel123"
OWNERS = ["owner@casaaurora.co", "owner@grupoandino.co"]
ADMIN = "admin@housetel.co"

results: list[tuple[str, int, float, str]] = []  # (label, status, ms, note)

MESSAGING = [
    "conversations/",
    "conversations/unread-count/",
    "templates/",
    "variables/",
    "lifecycle-rules/",
    "simulator/whatsapp/contacts/",
]
COMPLIANCE = [
    "resolutions/",
    "invoices/",
    "invoices/summary/",
    "sire/",
    "tra/",
    "settings/",
    "pending/",
    "pending/?summary=1",
]
REVENUE = [
    "settings/",
    "recommendations/?status=pending",
    "recommendations/summary/",
    "runs/",
    "options/",
    "rules/",
    "bounds/",
]
BILLING = ["billing/", "billing/status/", "billing/invoices/", "billing/commissions/", "getting-started/"]
CONTROL = [
    "integrations/",
    "automations/",
    "automation-runs/",
    "audit/",
    "audit/facets/",
    "alerts/",
    "alerts/count/",
]
ADMIN_PATHS = [
    "metrics/",
    "organizations/",
    "plans/",
    "invoices/",
    "commissions/",
    "settlements/",
    "subscriptions/",
    "billing-settings/",
]


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def cookie(self, name):
        return next((c.value for c in self.jar if c.name == name), None)

    def call(self, method, path, body=None, *, prop=None, label=None, expect=(200,), record=True):
        headers = {"Accept": "application/json", "Origin": BASE}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if method != "GET" and self.cookie("csrftoken"):
            headers["X-CSRFToken"] = self.cookie("csrftoken")
        if prop:
            headers["X-Property-Id"] = prop
        request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
        started = time.monotonic()
        try:
            with self.opener.open(request, timeout=90) as response:
                status, raw, ctype = (
                    response.status,
                    response.read(),
                    response.headers.get("Content-Type", ""),
                )
        except urllib.error.HTTPError as error:
            status, raw, ctype = error.code, error.read(), error.headers.get("Content-Type", "")
        ms = (time.monotonic() - started) * 1000
        payload = None
        if "json" in ctype and raw:
            payload = json.loads(raw)
        note = "" if status in expect else (raw[:300].decode(errors="replace") if raw else "")
        if record:
            results.append((label or f"{method} {path}", status, ms, note))
        return status, payload


def get(client, path, *, prop=None, label=None):
    return client.call("GET", path, prop=prop, label=label)[1]


def login(email):
    client = Client()
    client.call("GET", "/api/v1/accounts/auth/csrf/", record=False)
    status, me = client.call(
        "POST", "/api/v1/accounts/auth/login/", {"email": email, "password": PASSWORD}, record=False
    )
    if status != 200:
        print(f"ERR login {email}: {status}")
        raise SystemExit(1)
    return client, me


def first_id(payload):
    rows = payload.get("results", payload) if isinstance(payload, dict) else payload
    return rows[0]["id"] if rows else None


def sweep_property(client, prop):
    pid, name = prop["id"], prop["name"]
    today = date.fromisoformat(prop["business_date"])
    in14 = today + timedelta(days=14)
    tag = f"[{prop['slug']}]"

    def g(path, label=None):
        return get(client, path, prop=pid, label=f"{tag} {label or path}")

    # Phase A/B
    g("/api/v1/inventory/rooms/")
    g("/api/v1/inventory/room-types/")
    g(f"/api/v1/rates/grid/?start={today}&end={in14}")
    g(f"/api/v1/rates/holidays/?year={today.year}")
    reservations = g("/api/v1/bookings/reservations/?page_size=50")
    g(f"/api/v1/bookings/calendar/?start={today}&end={in14}")
    g("/api/v1/guests/guests/?page_size=50")
    g("/api/v1/finance/summary/")
    g("/api/v1/finance/cash-shifts/")
    reservation_id = first_id(reservations or {})

    # C1 frontdesk
    g("/api/v1/frontdesk/today/")
    g("/api/v1/frontdesk/night-audit/preview/")
    g("/api/v1/frontdesk/night-audit/reports/")
    # C2 housekeeping
    for path in ("tasks/", "board/", "summary/", "staff/", "settings/", "tickets/"):
        g(f"/api/v1/housekeeping/{path}")
    # C3 distribution
    connections = g("/api/v1/distribution/connections/") or []
    for path in ("logs/", "queue/", "options/"):
        g(f"/api/v1/distribution/{path}")
    simulated = [c for c in connections if c.get("channel_code") in ("booksim", "airsim")]
    if simulated:
        cid = simulated[0]["id"]
        g(f"/api/v1/distribution/simulator/{cid}/inventory/", "distribution simulator inventory")
        g(f"/api/v1/distribution/simulator/{cid}/bookings/", "distribution simulator bookings")
    # C4 marketplace (staff)
    for path in ("booking-engine/", "listing/", "embed-snippet/"):
        g(f"/api/v1/marketplace/{path}")
    # C5 guest portal (staff) + the public portal of one reservation
    for path in ("checkins/", "service-requests/", "settings/"):
        g(f"/api/v1/guestportal/{path}")
    portal_token = None
    if reservation_id:
        link = g(f"/api/v1/guestportal/reservations/{reservation_id}/link/", "guestportal reservation link")
        if link and link.get("url"):
            portal_token = link["url"].rstrip("/").rsplit("/", 1)[-1]
        g(f"/api/v1/compliance/reservations/{reservation_id}/", "compliance reservation tab")
        g(f"/api/v1/control/audit/?reservation={reservation_id}", "control audit of a reservation")
    # C6 messaging
    for path in MESSAGING:
        g(f"/api/v1/messaging/{path}")
    # C7 compliance
    for path in COMPLIANCE:
        g(f"/api/v1/compliance/{path}")
    # C8 revenue
    for path in (*REVENUE, f"recommendations/calendar/?start={today}&end={in14}&lang=es"):
        g(f"/api/v1/revenue/{path}")
    # C9 AI
    for path in ("copilot/status/?language=es", "settings/", "usage/", "faqs/", "chatbot-conversations/"):
        g(f"/api/v1/ai/{path}")
    # C10 reports: the catalog and every report of the current month
    catalog = g("/api/v1/reports/") or []
    reports = catalog.get("reports", catalog) if isinstance(catalog, dict) else catalog
    for report in reports:
        rid = report["id"] if isinstance(report, dict) else report
        g(f"/api/v1/reports/{rid}/?start={today.replace(day=1)}&end={today}", f"report {rid}")
    # C11 billing (hotel side)
    for path in BILLING:
        g(f"/api/v1/saas/{path}")
    # C12 control
    for path in CONTROL:
        g(f"/api/v1/control/{path}")
    # Phase P: groups and allotments (P3), companies and receivables (P4), the importer (P5), retention (P6)
    groups = g("/api/v1/bookings/groups/?when=all") or {}
    group_id = first_id(groups)
    if group_id:
        g(f"/api/v1/bookings/groups/{group_id}/", "bookings group detail")
        get(client, f"/api/v1/frontdesk/groups/{group_id}/rooming-list/?lang=es", prop=pid,
            label=f"{tag} frontdesk rooming list (CSV)")  # fmt: skip
    offers_from, offers_to = today + timedelta(days=21), today + timedelta(days=23)
    g(f"/api/v1/bookings/room-offers/?checkin={offers_from}&checkout={offers_to}", "bookings room-offers")
    companies = g("/api/v1/corporate/companies/") or {}
    company_id = first_id(companies)
    if company_id:
        g(f"/api/v1/corporate/companies/{company_id}/", "corporate company")
        g(f"/api/v1/corporate/companies/{company_id}/statement/", "corporate statement")
        g(f"/api/v1/corporate/companies/{company_id}/reservations/", "corporate company reservations")
    g("/api/v1/corporate/receivables/")
    if reservation_id:
        g(f"/api/v1/corporate/reservations/{reservation_id}/billing/", "corporate reservation billing")
        g(f"/api/v1/finance/folios/?reservation={reservation_id}", "finance folios of a reservation")
    g("/api/v1/imports/catalog/")
    g("/api/v1/imports/jobs/")
    g("/api/v1/control/automations/guests.purge_identity_documents/", "control retention automation")
    print(f"    {name}: {len([r for r in results if r[0].startswith(tag)])} endpoints")
    return portal_token


def sweep_public(portal_tokens, slugs):
    client = Client()
    today = date.today()
    checkin, checkout = today + timedelta(days=22), today + timedelta(days=24)
    g = lambda path, label=None: get(client, path, label=f"[public] {label or path}")  # noqa: E731
    g("/api/v1/public/marketplace/destinations/")
    g(f"/api/v1/public/marketplace/search/?city=cartagena&checkin={checkin}&checkout={checkout}&adults=2")
    for slug in slugs:
        g(f"/api/v1/public/marketplace/properties/{slug}/")
        g(
            f"/api/v1/public/marketplace/properties/{slug}/offers/?checkin={checkin}&checkout={checkout}&adults=2"
        )
        g(f"/api/v1/public/marketplace/properties/{slug}/booking-engine/")
        g(f"/api/v1/public/ai/chat/{slug}/?language=es")
    g("/api/v1/public/saas/plans/")
    g("/api/v1/public/core/config/")
    g("/api/v1/public/core/health/")
    g("/api/v1/public/core/health/ready/")
    for token in portal_tokens:
        g(f"/api/v1/public/guestportal/{token}/", "guest portal summary")
        g(f"/api/v1/public/guestportal/{token}/checkin/", "guest portal check-in")
        g(f"/api/v1/public/guestportal/{token}/extras/", "guest portal extras")
        g(f"/api/v1/public/compliance/portal/{token}/invoices/", "guest portal invoices")


def sweep_admin():
    client, _ = login(ADMIN)
    for path in ADMIN_PATHS:
        get(client, f"/api/v1/saas/admin/{path}", label=f"[admin] {path}")
    get(client, "/api/v1/accounts/me/", label="[admin] accounts/me (P2: email_verified)")


def main():
    tokens, slugs = [], []
    for email in OWNERS:
        client, me = login(email)
        for membership in me["memberships"]:
            for prop in membership["properties"]:
                slugs.append(prop["slug"])
                token = sweep_property(client, prop)
                if token:
                    tokens.append(token)
    sweep_admin()
    sweep_public(tokens, slugs)

    failed = [r for r in results if r[1] != 200]
    slow = sorted(results, key=lambda r: -r[2])[:8]
    for label, status, ms, note in results:
        if status != 200:
            print(f"ERR {status} {ms:6.0f} ms  {label}\n      {note}")
    print("\nSlowest:")
    for label, status, ms, _ in slow:
        print(f"    {ms:6.0f} ms  {status}  {label}")
    print(f"\n{'SWEEP OK' if not failed else 'SWEEP FAILED'} · {len(results)} GET · {len(failed)} errors")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
