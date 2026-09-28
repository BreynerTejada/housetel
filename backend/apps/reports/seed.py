"""Reports demo check (plan C10 › Seed; runs after every data seeder, see ``SEED_ORDER``).

Reports have no tables of their own: every figure is computed live from bookings, finance and inventory by the
KPI engine, so there is nothing to derive or store. This seeder only *verifies* the demo: it builds every
report of the catalog for each demo property with its default filters (read-only, a few seconds in total) and
logs the headline figures of the month. A report that fails is logged with its error and the seed goes on (a
report bug must never block the demo data of the other apps). Idempotent by construction: it writes nothing.
"""

from __future__ import annotations

import time

from apps.reports.params import make_params
from apps.reports.registry import REPORTS
from apps.reports.service import run_report


def check_property(prop) -> tuple[int, list[str], dict]:
    """Builds every report for ``prop``: ``(reports built, failures, headline KPIs of the performance
    report)``."""
    built, failures, headline = 0, [], {}
    for report in REPORTS.values():
        try:
            params = make_params(report, prop, None, {"lang": "es"})
            result = run_report(report, params)
        except Exception as error:  # noqa: BLE001 - logged and reported, the demo seed must go on
            failures.append(f"{report.id}: {type(error).__name__}: {error}")
            continue
        built += 1
        if report.id == "performance":
            headline = {kpi.key: kpi.value for kpi in result.summary}
    return built, failures, headline


def seed(ctx) -> None:
    for key, prop in ctx.properties.items():
        prop.refresh_from_db(fields=["business_date"])
        started = time.perf_counter()
        built, failures, headline = check_property(prop)
        elapsed = time.perf_counter() - started
        occupancy = headline.get("occupancy")
        summary = (
            f"ocupación del mes {occupancy} % · ADR {headline.get('adr')} · RevPAR {headline.get('revpar')}"
            if occupancy is not None
            else "sin cifras de rendimiento"
        )
        ctx.log(f"  {key}: {built}/{len(REPORTS)} reportes en {elapsed:.1f} s · {summary}")
        for failure in failures:
            ctx.log(f"  ⚠ {key}: {failure}")
