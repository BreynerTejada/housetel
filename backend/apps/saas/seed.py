"""Demo seed of the SaaS module (plan C11 › Seed). Idempotent; takes a few seconds.

- Plans Starter (≤ 15 units, 149.000/month), Pro (≤ 60, 349.000), Cadena (unlimited, 899.000); yearly −15 %.
- Casa Aurora on Pro and Grupo Andino on Cadena, both active and monthly, with a simulated card on file and
  6 months of paid subscription invoices (chronological numbering).
- Commissions of every marketplace reservation of the seeded hotels (same rules as the receivers: confirmed /
  in house / checked out → pending; cancelled or no-show with a fee → over the fee; cancelled without a fee →
  reversed), the closed months settled and invoiced (paid); the current month stays pending.
- An extra organization "Hostal Demo Trial" (owner `owner@hostaldemo.co` / housetel123) in a 14-day trial with
  an empty property, to try the getting-started checklist and the AI onboarding.

The receivers skip everything while seeding (`is_seeding()`), so nothing here is created twice.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services import add_member, ensure_system_roles
from apps.core.codes import generate_code
from apps.core.models import Organization, Property
from apps.core.money import ZERO, quantize
from apps.saas.models import Commission, CommissionSettlement, PlatformInvoice, Subscription
from apps.saas.services import billing
from apps.saas.services.commissions import (
    EARNING_STATUSES,
    ENDED_STATUSES,
    _accrual_for_fee,
    commission_amount,
    lodging_net,
)
from apps.saas.services.plans import ensure_default_plans

DEMO_PASSWORD = "housetel123"
SUBSCRIPTIONS = {
    # org key: (plan code, renewal day of month, card)
    "aurora": ("pro", 15, {"brand": "VISA", "last4": "4242", "holder": "Valentina Rojas"}),
    "andino": ("cadena", 5, {"brand": "MASTERCARD", "last4": "5100", "holder": "Santiago Restrepo"}),
}
PAID_MONTHS = 6
TRIAL_ORG = {
    "slug": "hostal-demo-trial",
    "name": "Hostal Demo Trial",
    "property": {
        "slug": "hostal-demo-trial",
        "name": "Hostal Demo Trial",
        "property_type": "hostel",
        "city": "Santa Marta",
        "department": "Magdalena",
        "address": "Calle 19 #3-45, Centro Histórico",
        "phone": "+57 605 420 8899",
    },
    "owner": ("owner@hostaldemo.co", "Mariana Cárdenas"),
    "trial_days_left": 9,
}


def seed(ctx) -> None:
    plans = ensure_default_plans()
    invoices_planned: list[dict] = []
    for key, (plan_code, day, card) in SUBSCRIPTIONS.items():
        org = ctx.orgs.get(key)
        if org is None:
            continue
        sub, created = _subscription(org, plans[plan_code], day, card)
        if created:
            invoices_planned += _subscription_history(org, sub, day)
    properties = [p for p in ctx.properties.values()]
    created_commissions = _commissions(properties)
    invoices_planned += _settlements(ctx, [ctx.orgs[k] for k in SUBSCRIPTIONS if k in ctx.orgs])
    _create_invoices(invoices_planned)
    trial = _trial_org(ctx, plans["starter"])
    ctx.log(
        f"  saas: {len(plans)} planes, {len(invoices_planned)} facturas de plataforma, "
        f"{created_commissions} comisiones, org de prueba «{trial.name}»"
    )


# ---- Subscriptions --------------------------------------------------------------------------------


def _current_period_start(today, day: int):
    start = today.replace(day=day) if today.day >= day else (today - relativedelta(months=1)).replace(day=day)
    return start


def _subscription(org: Organization, plan, day: int, card: dict) -> tuple[Subscription, bool]:
    existing = Subscription.objects.filter(organization=org).first()
    if existing is not None:
        return existing, False
    today = timezone.localdate()
    start = _current_period_start(today, day)
    sub = Subscription.objects.create(
        organization=org,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        billing_cycle=Subscription.Cycle.MONTHLY,
        current_period_start=start,
        current_period_end=billing.add_cycle(start, Subscription.Cycle.MONTHLY),
        trial_ends_at=timezone.make_aware(
            datetime.combine(start - relativedelta(months=PAID_MONTHS - 1), time(3))
        ),
        payment_source={
            "type": "card",
            "exp_month": 11,
            "exp_year": today.year + 3,
            "simulated": True,
            **card,
        },
    )
    if org.status != Organization.Status.ACTIVE:
        org.status = Organization.Status.ACTIVE
        org.save(update_fields=["status", "updated_at"])
    return sub, True


def _subscription_history(org, sub: Subscription, day: int) -> list[dict]:
    """The last PAID_MONTHS monthly invoices (the current period included), all paid by card."""
    planned = []
    for i in range(PAID_MONTHS - 1, -1, -1):
        start = sub.current_period_start - relativedelta(months=i)
        end = billing.add_cycle(start, sub.billing_cycle) - timedelta(days=1)
        issued = timezone.make_aware(datetime.combine(start, time(3, 0)))
        planned.append(
            {
                "org": org,
                "kind": PlatformInvoice.Kind.SUBSCRIPTION,
                "period_start": start,
                "period_end": end,
                "lines": [billing.plan_line(sub.plan, sub.billing_cycle, start, end)],
                "issued_at": issued,
                "method": f"{sub.payment_source.get('brand')} •••• {sub.payment_source.get('last4')}",
            }
        )
    return planned


# ---- Commissions ----------------------------------------------------------------------------------


def _commissions(properties: list[Property]) -> int:
    from apps.bookings.models import Reservation

    existing = set(
        Commission.objects.filter(property__in=properties).values_list("reservation_id", flat=True)
    )
    rows = []
    for reservation in (
        Reservation.objects.filter(property__in=properties, source="marketplace")
        .exclude(pk__in=existing)
        .select_related("property", "property__organization")
        .prefetch_related("stays")
        .iterator(chunk_size=500)
    ):
        prop = reservation.property
        currency = reservation.currency or "COP"
        rate = prop.commission_rate
        if reservation.status in EARNING_STATUSES:
            base = lodging_net(reservation)
            basis, accrual, status = (
                Commission.Basis.STAY,
                reservation.checkout_date,
                Commission.Status.PENDING,
            )
        elif reservation.status in ENDED_STATUSES and quantize(reservation.cancellation_fee or ZERO) > 0:
            base = quantize(reservation.cancellation_fee, currency)
            basis, accrual, status = (
                Commission.Basis.FEE,
                _accrual_for_fee(reservation),
                Commission.Status.PENDING,
            )
        elif reservation.status in ENDED_STATUSES:
            # Confirmed and later cancelled without a fee: the receiver would have recorded the commission
            # and then reversed it (it keeps its base and accrual date).
            base = lodging_net(reservation, all_stays=True)
            if base <= 0:
                continue
            basis, accrual, status = (
                Commission.Basis.STAY,
                reservation.checkout_date,
                Commission.Status.REVERSED,
            )
        else:
            continue  # tentative: nothing is owed yet
        rows.append(
            Commission(
                organization=prop.organization,
                property=prop,
                reservation=reservation,
                basis=basis,
                base_amount=base,
                rate=rate,
                amount=commission_amount(base, rate, currency),
                currency=currency,
                status=status,
                accrual_date=accrual,
                reversed_at=(reservation.cancelled_at or timezone.now())
                if status == Commission.Status.REVERSED
                else None,
            )
        )
    Commission.objects.bulk_create(rows, batch_size=500)
    return len(rows)


def _settlements(ctx, orgs: list[Organization]) -> list[dict]:
    """Settle every closed month (before the current one) with pending commissions: paid invoice on day 1."""
    today = timezone.localdate()
    month_start = today.replace(day=1)
    planned = []
    for org in orgs:
        pending = Commission.objects.filter(
            organization=org, status=Commission.Status.PENDING, accrual_date__lt=month_start
        ).select_related("property")
        by_month: dict = defaultdict(list)
        for commission in pending:
            by_month[commission.accrual_date.replace(day=1)].append(commission)
        for start in sorted(by_month):
            if CommissionSettlement.objects.filter(organization=org, period_start=start).exists():
                continue
            end = billing.month_bounds(start.year, start.month)[1]
            items = by_month[start]
            total = quantize(sum((c.amount for c in items), ZERO))
            settlement = CommissionSettlement.objects.create(
                organization=org,
                period_start=start,
                period_end=end,
                total=total,
                commissions_count=len(items),
                status=CommissionSettlement.Status.PAID,
            )
            Commission.objects.filter(pk__in=[c.pk for c in items]).update(
                status=Commission.Status.SETTLED, settlement=settlement
            )
            per_property: dict = defaultdict(lambda: [ZERO, 0, ""])
            for c in items:
                row = per_property[c.property_id]
                row[0] += c.amount
                row[1] += 1
                row[2] = c.property.name
            label = billing.month_label(start)
            lines = [
                {
                    "kind": "commission",
                    "description": {
                        "es": f"Comisiones marketplace · {name} · {label['es']} ({count} reservas)",
                        "en": f"Marketplace commissions · {name} · {label['en']} ({count} bookings)",
                    },
                    "quantity": count,
                    "unit_price": billing.money(amount),
                    "amount": billing.money(amount),
                    "property_id": str(prop_id),
                    "settlement_id": str(settlement.pk),
                }
                for prop_id, (amount, count, name) in sorted(per_property.items(), key=lambda i: i[1][2])
                if amount > 0
            ]
            if not lines:
                continue
            sub = Subscription.objects.filter(organization=org).first()
            source = (sub.payment_source if sub else {}) or {}
            planned.append(
                {
                    "org": org,
                    "kind": PlatformInvoice.Kind.COMMISSIONS,
                    "period_start": start,
                    "period_end": end,
                    "lines": lines,
                    "issued_at": timezone.make_aware(datetime.combine(end + timedelta(days=1), time(4, 0))),
                    "method": f"{source.get('brand', 'CARD')} •••• {source.get('last4', '')}".strip(),
                    "settlement": settlement,
                }
            )
    return planned


def _create_invoices(planned: list[dict]) -> None:
    """Create the historical invoices in chronological order (numbers follow the dates), all paid."""
    for spec in sorted(planned, key=lambda s: s["issued_at"]):
        subtotal = quantize(sum((Decimal(line["amount"]) for line in spec["lines"]), ZERO))
        tax = quantize(subtotal * billing.TAX_RATE / 100)
        issued_at = spec["issued_at"]
        invoice = PlatformInvoice.objects.create(
            organization=spec["org"],
            number=billing.next_invoice_number(timezone.localtime(issued_at).year),
            kind=spec["kind"],
            period_start=spec["period_start"],
            period_end=spec["period_end"],
            lines=spec["lines"],
            subtotal=subtotal,
            tax_rate=billing.TAX_RATE,
            tax=tax,
            total=subtotal + tax,
            status=PlatformInvoice.Status.PAID,
            issued_at=issued_at,
            due_date=timezone.localtime(issued_at).date() + timedelta(days=billing.DUE_DAYS),
            paid_at=issued_at + timedelta(minutes=2),
            payment_reference=f"SIM-SAAS-{generate_code('', 8)}",
            payment_method=spec["method"],
            attempts=1,
            payment_payload={"simulated": True, "seed": True},
        )
        settlement = spec.get("settlement")
        if settlement is not None:
            settlement.invoice = invoice
            settlement.save(update_fields=["invoice", "updated_at"])


# ---- Trial organization ---------------------------------------------------------------------------


def _trial_org(ctx, starter_plan) -> Organization:
    now = timezone.now()
    org = Organization.objects.filter(slug=TRIAL_ORG["slug"]).first()
    if org is None:
        org = Organization.objects.create(
            name=TRIAL_ORG["name"],
            slug=TRIAL_ORG["slug"],
            country="CO",
            status=Organization.Status.TRIAL,
            trial_ends_at=now + timedelta(days=TRIAL_ORG["trial_days_left"]),
        )
        ensure_system_roles(org)
    values = dict(TRIAL_ORG["property"])
    slug = values.pop("slug")
    prop, created = Property.objects.get_or_create(
        slug=slug,
        defaults={
            **values,
            "organization": org,
            "business_date": ctx.today,
            "marketplace_listed": False,
            "email": TRIAL_ORG["owner"][0],
        },
    )
    if created:
        from apps.rates.services.provision import provision_rates

        provision_rates(prop, room_type_prices={})
    email, full_name = TRIAL_ORG["owner"]
    user = User.objects.filter(email=email).first()
    if user is None:
        user = User.objects.create_user(email, DEMO_PASSWORD, full_name=full_name, language="es")
    add_member(org, user, "owner", all_properties=True)
    ctx.users.setdefault("trial_owner", user)
    if not Subscription.objects.filter(organization=org).exists():
        Subscription.objects.create(
            organization=org,
            plan=starter_plan,
            status=Subscription.Status.TRIALING,
            billing_cycle=Subscription.Cycle.MONTHLY,
            trial_ends_at=org.trial_ends_at,
        )
    return org
