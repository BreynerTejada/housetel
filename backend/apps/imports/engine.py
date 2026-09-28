"""Execution of an import job: dry-run, real run and rollback (Celery task `imports.process_job`).

- **Dry-run**: every reservation (or row) goes through the same contract services as the real run inside a
  transaction that is rolled back right away (no locks are kept, nothing is saved, no signal is sent). A
  ledger of the units and rooms taken by the earlier rows of the file catches the conflicts between rows
  of the same file that the rolled-back transactions cannot see.
- **Run**: one transaction per reservation (all its rooms at once) or per row; rows already processed are
  skipped, so a run interrupted halfway can be launched again. Reservations: `guests.upsert_guest` +
  `bookings.create_reservation(source="import", enforce_restrictions=False)`, `check_in(force=True)` for the
  guests in house and `finance.record_payment(method="other", reference="Saldo importado")` for what was
  already paid. Availability conflicts are row errors: nothing is overbooked.
- **Rollback**: cancels (without penalty) the reservations the job created that have no later activity, after
  voiding their imported payment, and marks them.

Guests and reservations run inside `core.signals.seeding()`: the receivers that send emails to guests,
register TRA, issue invoices or push ARI treat the import like the demo seed and do nothing per row (an
import must not email hundreds of "confirmed" or "cancelled" messages nor register guests twice). At the
end one `inventory_changed` covers the affected categories and dates, so channels get the new availability.
"""

import logging
import time as time_module
import uuid
from collections import Counter, defaultdict
from contextlib import nullcontext
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core import audit, signals
from apps.core.errors import DomainError
from apps.core.money import quantize
from apps.imports.messages import from_domain_error, message
from apps.imports.models import ImportedRecord, ImportJob, ImportRow

logger = logging.getLogger("housetel.imports")

FLUSH_SECONDS = 1.5
PAYMENT_REFERENCE = "Saldo importado"
DONE_OUTCOMES = (ImportRow.Outcome.CREATED, ImportRow.Outcome.UPDATED, ImportRow.Outcome.SKIPPED)
QUEUED_STALE = timedelta(minutes=2)
RUNNING_STALE = timedelta(minutes=5)
TARGET_TYPES = {
    ImportJob.Kind.GUESTS: "guests.guest",
    ImportJob.Kind.RESERVATIONS: "bookings.reservation",
    ImportJob.Kind.ROOM_TYPES: "inventory.roomtype",
    ImportJob.Kind.ROOMS: "inventory.room",
}


class _Rollback(Exception):  # noqa: N818 - control flow of the dry-run
    """Raised at the end of a dry-run transaction to roll it back."""


def _user(actor):
    return actor if getattr(actor, "is_authenticated", False) else None


def is_stale(job: ImportJob) -> bool:
    """A queued job no worker picked up, or a running job whose worker stopped reporting."""
    now = timezone.now()
    if job.status == ImportJob.Status.QUEUED:
        return job.queued_at is None or job.queued_at < now - QUEUED_STALE
    if job.status == ImportJob.Status.RUNNING:
        last = job.heartbeat_at or job.started_at or job.queued_at
        return last is None or last < now - RUNNING_STALE
    return False


# ---- Entry point --------------------------------------------------------------------------------------


def process(job_id, mode: str) -> None:
    """Run the queued `mode` of the job (called by the Celery task, the inline fallback or the management
    command). Never raises: a crash marks the job and is logged."""
    job = _claim(job_id, mode)
    if job is None:
        return
    runner = Runner(job, mode)
    try:
        runner.execute()
    except Exception as exc:  # noqa: BLE001 - the job must end in a visible state
        logger.exception("Import job %s (%s) failed", job_id, mode)
        _fail(job, mode, exc)


def _claim(job_id, mode: str) -> ImportJob | None:
    with transaction.atomic():
        job = (
            ImportJob.objects.select_for_update(of=("self",))
            .select_related("property", "property__organization", "run_by", "created_by")
            .filter(pk=job_id)
            .first()
        )
        if job is None:
            return None
        stale_running = job.status == ImportJob.Status.RUNNING and is_stale(job)
        if job.phase != mode or not (job.status == ImportJob.Status.QUEUED or stale_running):
            return None
        now = timezone.now()
        job.status = ImportJob.Status.RUNNING
        job.started_at = now
        job.heartbeat_at = now
        job.progress_done = 0
        job.error = ""
        job.save(
            update_fields=["status", "started_at", "heartbeat_at", "progress_done", "error", "updated_at"]
        )
    return job


def _fail(job: ImportJob, mode: str, exc: Exception) -> None:
    text = f"{type(exc).__name__}: {exc}"[:2000]
    if mode == ImportJob.Phase.RUN:
        status = ImportJob.Status.FAILED
    elif mode == ImportJob.Phase.REVERT:
        status = ImportJob.Status.COMPLETED
    else:
        status = ImportJob.Status.VALIDATED
    ImportJob.objects.filter(pk=job.pk).update(
        status=status, phase="", error=text, finished_at=timezone.now(), updated_at=timezone.now()
    )


# ---- Runner -------------------------------------------------------------------------------------------


class Runner:
    def __init__(self, job: ImportJob, mode: str):
        from apps.imports.catalog import DEFAULT_OPTIONS

        self.job = job
        self.mode = mode
        self.dry = mode == ImportJob.Phase.DRY_RUN
        self.prop = job.property
        self.org = job.property.organization
        self.actor = _user(job.run_by) or _user(job.created_by)
        self.options = {**DEFAULT_OPTIONS, **(job.options or {})}
        self.on_existing = self.options.get("on_existing", "update")
        self.today = self.prop.business_date
        self.currency = self.prop.currency or "COP"
        self.done = 0
        self.flushed_at = time_module.monotonic()
        self.counts: Counter = Counter()
        self.room_type_ids: set[str] = set()
        self.start: date | None = None
        self.end: date | None = None
        self.pending_rows: list[ImportRow] = []
        # dry-run ledgers (what the earlier rows of the file took)
        self.units_taken: Counter = Counter()  # (room_type_id, date) → units
        self.units_by: dict = {}  # (room_type_id, date) → row number
        self.rooms_taken: dict = {}  # (room_id, date) → row number
        self.available: dict = {}  # (room_type_id, date) → units free in the database
        self.records: dict[str, ImportedRecord] = {}

    # -- plumbing

    def tick(self, count: int = 1) -> None:
        self.done += count
        if time_module.monotonic() - self.flushed_at >= FLUSH_SECONDS:
            self.flush()

    def flush(self) -> None:
        self.flushed_at = time_module.monotonic()
        if self.pending_rows:
            self._write_rows(self.pending_rows)
            self.pending_rows = []
        ImportJob.objects.filter(pk=self.job.pk).update(progress_done=self.done, heartbeat_at=timezone.now())

    def _write_rows(self, rows: list[ImportRow]) -> None:
        fields = (
            ["dry_outcome", "dry_message"]
            if self.dry
            else [
                "outcome",
                "outcome_message",
                "target_type",
                "target_id",
                "target_label",
                "processed_at",
                "extra",
            ]
        )
        ImportRow.objects.bulk_update(rows, fields, batch_size=500)

    def set_result(
        self, rows: list[ImportRow], outcome: str, msg: dict, *, target=None, label="", extra=None
    ):
        """Store the outcome of a unit on its rows (dry-run: the would-be outcome)."""
        now = timezone.now()
        for row in rows:
            if self.dry:
                row.dry_outcome = {
                    "created": ImportRow.DryOutcome.CREATE,
                    "updated": ImportRow.DryOutcome.UPDATE,
                    "skipped": ImportRow.DryOutcome.SKIP,
                    "failed": ImportRow.DryOutcome.FAIL,
                }[outcome]
                row.dry_message = msg
            else:
                row.outcome = outcome
                row.outcome_message = msg
                if target is not None:
                    row.target_type = TARGET_TYPES[self.job.kind]
                    row.target_id = target.pk
                    row.target_label = label[:160]
                row.processed_at = now
                if extra:
                    row.extra = {**(row.extra or {}), **extra}
            self.counts[outcome] += 1
        if self.dry:
            self.pending_rows.extend(rows)
        else:  # the unit is committed: its rows say so right away (a resumed run skips them)
            self._write_rows(rows)

    def track(self, room_type_id, start: date | None, end: date | None) -> None:
        if room_type_id:
            self.room_type_ids.add(str(room_type_id))
        if start is not None:
            self.start = start if self.start is None else min(self.start, start)
        if end is not None:
            self.end = end if self.end is None else max(self.end, end)

    def unit(self):
        """Transaction of one unit of work: rolled back at the end in a dry-run."""
        return transaction.atomic()

    def record(self, key: str) -> ImportedRecord | None:
        if key not in self.records:
            self.records[key] = ImportedRecord.objects.filter(
                property=self.prop, kind=self.job.kind, source_system=self.job.source_system, external_id=key
            ).first()
        return self.records[key]

    def save_record(self, key: str, target) -> None:
        if self.dry or not key:
            return
        record, created = ImportedRecord.objects.update_or_create(
            property=self.prop,
            kind=self.job.kind,
            source_system=self.job.source_system,
            external_id=key[:200],
            defaults={
                "target_type": TARGET_TYPES[self.job.kind],
                "target_id": target.pk,
                "job": self.job,
            },
        )
        if created:
            record.created_by_job = self.job
            record.save(update_fields=["created_by_job", "updated_at"])
        self.records[key] = record

    # -- main

    def execute(self) -> None:
        kind = self.job.kind
        quiet = kind in (ImportJob.Kind.GUESTS, ImportJob.Kind.RESERVATIONS)
        with signals.seeding() if quiet else nullcontext():
            if self.mode == ImportJob.Phase.REVERT:
                self.revert()
            else:
                self.prepare_rows()
                handler = {
                    ImportJob.Kind.GUESTS: self.run_guests,
                    ImportJob.Kind.RESERVATIONS: self.run_reservations,
                    ImportJob.Kind.ROOM_TYPES: self.run_room_types,
                    ImportJob.Kind.ROOMS: self.run_rooms,
                }[kind]
                handler()
        self.flush()
        self.finish()

    def rows(self, statuses=(ImportRow.Status.VALID, ImportRow.Status.WARNING)) -> list[ImportRow]:
        rows = self.job.rows.filter(status__in=statuses).order_by("number")
        if not self.dry:
            rows = rows.exclude(outcome__in=DONE_OUTCOMES)
        return list(rows)

    def prepare_rows(self) -> None:
        """Rows that will not run get their outcome now (first error or skip reason)."""
        pending = []
        for row in self.job.rows.filter(status__in=(ImportRow.Status.ERROR, ImportRow.Status.SKIP)):
            if not self.dry and row.outcome in DONE_OUTCOMES:
                continue
            level = "error" if row.status == ImportRow.Status.ERROR else "skip"
            first = next((item for item in row.issues if item.get("level") == level), None) or {}
            msg = {"code": first.get("code", level), "es": first.get("es", ""), "en": first.get("en", "")}
            outcome = ImportRow.Outcome.FAILED if level == "error" else ImportRow.Outcome.SKIPPED
            if self.dry:
                row.dry_outcome = ImportRow.DryOutcome.FAIL if level == "error" else ImportRow.DryOutcome.SKIP
                row.dry_message = msg
            else:
                row.outcome, row.outcome_message, row.processed_at = outcome, msg, timezone.now()
            self.counts[outcome] += 1
            pending.append(row)
        if pending:
            self._write_rows(pending)

    def finish(self) -> None:
        job = ImportJob.objects.get(pk=self.job.pk)
        now = timezone.now()
        if self.mode == ImportJob.Phase.DRY_RUN:
            job.dry_run_summary = self.summary_counts()
            job.dry_run_at = now
            job.status = ImportJob.Status.VALIDATED
        elif self.mode == ImportJob.Phase.RUN:
            totals = Counter(job.rows.values_list("outcome", flat=True))
            job.summary = {
                "created": totals.get(ImportRow.Outcome.CREATED, 0),
                "updated": totals.get(ImportRow.Outcome.UPDATED, 0),
                "skipped": totals.get(ImportRow.Outcome.SKIPPED, 0),
                "failed": totals.get(ImportRow.Outcome.FAILED, 0),
                "total": job.total_rows,
                "start": self.start.isoformat() if self.start else None,
                "end": self.end.isoformat() if self.end else None,
                "room_type_ids": sorted(self.room_type_ids),
            }
            job.status = ImportJob.Status.COMPLETED
            self._audit_run(job)
        job.phase = ""
        job.finished_at = now
        job.progress_done = job.progress_total
        job.heartbeat_at = now
        job.save()
        self.job = job
        if not self.dry:
            self._emit_inventory()

    def summary_counts(self) -> dict:
        return {
            "create": self.counts.get(ImportRow.Outcome.CREATED, 0),
            "update": self.counts.get(ImportRow.Outcome.UPDATED, 0),
            "skip": self.counts.get(ImportRow.Outcome.SKIPPED, 0),
            "fail": self.counts.get(ImportRow.Outcome.FAILED, 0),
        }

    def _audit_run(self, job: ImportJob) -> None:
        summary = job.summary
        noun = {
            ImportJob.Kind.GUESTS: "huéspedes",
            ImportJob.Kind.RESERVATIONS: "reservas",
            ImportJob.Kind.ROOM_TYPES: "categorías",
            ImportJob.Kind.ROOMS: "habitaciones",
        }[job.kind]
        audit.record(
            action="imports.job_completed",
            target=job,
            actor=self.actor,
            property=self.prop,
            summary=(
                f"Importó {noun} desde {job.source_label} ({job.filename}): {summary['created']} creados, "
                f"{summary['updated']} actualizados, {summary['skipped']} omitidos, "
                f"{summary['failed']} con error"
            ),
            changes={"counts": {key: summary[key] for key in ("created", "updated", "skipped", "failed")}},
        )

    def _emit_inventory(self) -> None:
        if self.job.kind == ImportJob.Kind.RESERVATIONS and self.room_type_ids and self.start and self.end:
            from apps.bookings.services.inventory import ORIGIN

            # The reservations already moved the inventory rows (their own transactions); the channels have
            # not
            # heard about it because the import ran quietly: one event for the whole import.
            signals.send_on_commit(
                signals.inventory_changed,
                property=self.prop,
                room_type_ids=[uuid.UUID(value) for value in sorted(self.room_type_ids)],
                start=max(self.start, self.today),
                end=self.end,
                origin=ORIGIN,
            )

    # ---- Guests -------------------------------------------------------------------------------------

    def run_guests(self) -> None:
        rows = self.rows()
        self.set_total(len(rows))
        for row in rows:
            self.guest_row(row)
            self.tick()

    def set_total(self, total: int) -> None:
        ImportJob.objects.filter(pk=self.job.pk).update(progress_total=total)
        self.job.progress_total = total

    def guest_row(self, row: ImportRow) -> None:
        try:
            with self.unit():
                outcome, msg, guest = self._guest(row)
                if self.dry:
                    raise _Rollback
        except _Rollback:
            self.set_result([row], outcome, msg)
            return
        except DomainError as exc:
            self.set_result([row], ImportRow.Outcome.FAILED, from_domain_error(exc))
            return
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the import
            self.set_result([row], ImportRow.Outcome.FAILED, _unexpected(exc, row))
            return
        self.set_result([row], outcome, msg, target=guest, label=guest.full_name if guest else "")

    def _guest_input(self, values: dict):
        from apps.guests.types import GuestInput

        birth = values.get("birth_date")
        return GuestInput(
            first_name=values.get("first_name") or "",
            last_name=values.get("last_name") or "",
            email=values.get("email") or "",
            phone=values.get("phone") or "",
            document_type=values.get("document_type") or "",
            document_number=values.get("document_number") or "",
            nationality=values.get("nationality") or "",
            country_of_residence=values.get("country_of_residence") or "",
            city_of_residence=values.get("city_of_residence") or "",
            birth_date=date.fromisoformat(birth) if birth else None,
            language=values.get("language") or "es",
        )

    def _existing_guest(self, values: dict):
        """The guest `upsert_guest` would match (document, then email), to say "created" or "completed"."""
        from apps.guests.models import Guest
        from apps.guests.services import document_owner

        if values.get("document_number"):
            owner = document_owner(self.org, values.get("document_type", ""), values["document_number"])
            if owner is not None:
                return owner
            if not values.get("email"):
                return None
            return (
                Guest.objects.filter(
                    organization=self.org,
                    merged_into__isnull=True,
                    email__iexact=values["email"],
                    document_number="",
                )
                .order_by("created_at")
                .first()
            )
        if values.get("email"):
            return (
                Guest.objects.filter(
                    organization=self.org, merged_into__isnull=True, email__iexact=values["email"]
                )
                .order_by("created_at")
                .first()
            )
        return None

    def _guest(self, row: ImportRow):
        """(outcome, message, guest) of one guest row."""
        from apps.guests.models import Guest
        from apps.guests.services import surviving_guest, update_guest, upsert_guest

        values = row.data.get("guest") or {}
        key = row.external_id
        record = self.record(key) if key else None
        guest = None
        if record is not None:
            guest = Guest.objects.filter(pk=record.target_id, organization=self.org).first()
            guest = surviving_guest(guest) if guest else None
        if guest is not None:
            if self.on_existing == "skip":
                return ImportRow.Outcome.SKIPPED, message("skipped_existing"), guest
            changes = self._guest_changes(guest, values)
            if not changes:
                return ImportRow.Outcome.SKIPPED, message("unchanged"), guest
            update_guest(guest, changes, source="user", actor=self.actor)
            self.save_record(key, guest)
            return ImportRow.Outcome.UPDATED, message("updated_fields", value=_labels(changes)), guest
        existed = self._existing_guest(values)
        guest = upsert_guest(self.org, self._guest_input(values), actor=self.actor)
        extra = {
            field: values[field]
            for field in ("gender", "address")
            if values.get(field) and not getattr(guest, field)
        }
        if extra:
            update_guest(guest, extra, source="user", actor=self.actor)
        self.save_record(key, guest)
        if existed is not None:
            return ImportRow.Outcome.UPDATED, message("matched_guest"), guest
        return ImportRow.Outcome.CREATED, message("created_guest"), guest

    def _guest_changes(self, guest, values: dict) -> dict:
        """Non-empty file values that differ from the guest (an existing document is never replaced)."""
        from apps.guests.services import document_owner

        changes = {}
        for field in (
            "first_name", "last_name", "email", "phone", "nationality", "country_of_residence",
            "city_of_residence", "language", "gender", "address",
        ):  # fmt: skip
            value = values.get(field)
            if value and str(getattr(guest, field) or "") != str(value):
                changes[field] = value
        birth = values.get("birth_date")
        if birth and (guest.birth_date is None or guest.birth_date.isoformat() != birth):
            changes["birth_date"] = date.fromisoformat(birth)
        if values.get("document_number") and not guest.document_number:
            owner = document_owner(
                self.org, values.get("document_type", ""), values["document_number"], exclude=guest
            )
            if owner is None:
                changes["document_type"] = values.get("document_type", "")
                changes["document_number"] = values["document_number"]
        if changes.get("phone") and guest.phone:
            from apps.guests.normalization import normalize_phone

            if normalize_phone(changes["phone"]) == guest.phone:
                changes.pop("phone")
        return changes

    # ---- Reservations -------------------------------------------------------------------------------

    def run_reservations(self) -> None:
        rows = self.rows()
        groups: dict[str, list[ImportRow]] = defaultdict(list)
        for row in rows:
            groups[row.group_key or f"row-{row.number}"].append(row)
        self.set_total(len(groups))
        for key, members in groups.items():
            self.reservation_group(key, members)
            self.tick()

    def reservation_group(self, key: str, rows: list[ImportRow]) -> None:
        record = self.record(key)
        try:
            with self.unit():
                if record is not None:
                    outcome, msg, reservation, extra = self._update_reservation(record, rows)
                else:
                    outcome, msg, reservation, extra = self._create_reservation(key, rows)
                if self.dry:
                    raise _Rollback
        except _Rollback:
            self.set_result(rows, outcome, msg)
            return
        except DomainError as exc:
            self.set_result(rows, ImportRow.Outcome.FAILED, from_domain_error(exc))
            return
        except Exception as exc:  # noqa: BLE001 - one bad reservation must not stop the import
            self.set_result(rows, ImportRow.Outcome.FAILED, _unexpected(exc, rows[0]))
            return
        label = reservation.code if reservation is not None else ""
        self.set_result(rows, outcome, msg, target=reservation, label=label, extra=extra)

    def _group_values(self, rows: list[ImportRow]) -> dict:
        first = rows[0].data
        stays = []
        for row in rows:
            for stay in row.data.get("stays") or []:
                stays.append({**stay, "stage": row.data.get("stage"), "row": row.number})
        paid = sum((Decimal(row.data.get("paid") or "0") for row in rows), Decimal("0"))
        totals = [row.data.get("total") for row in rows]
        total = sum((Decimal(value) for value in totals if value is not None), Decimal("0"))
        extra = first.get("extra") or {}
        notes = [value for row in rows if (value := (row.data.get("extra") or {}).get("notes"))]
        requests = [value for row in rows if (value := (row.data.get("extra") or {}).get("special_requests"))]
        return {
            "guest": first.get("guest") or {},
            "stays": stays,
            "paid": paid,
            "total": total if any(value is not None for value in totals) else None,
            "tentative": all(row.data.get("tentative") for row in rows),
            "cancel": any(row.data.get("status") in ("cancelled", "no_show") for row in rows),
            "extra": extra,
            "notes": "\n".join(dict.fromkeys(notes)),
            "special_requests": "\n".join(dict.fromkeys(requests)),
        }

    def _nightly_rates(self, stay: dict, checkin: date, checkout: date, foreign: bool) -> list[dict] | None:
        """Per-night prices that reproduce the file's total for the stay (as a channel price: before any tax
        that is not included in the price)."""
        from apps.bookings.services.pricing import lodging_tax, split_amount, tax_exempt
        from apps.core.dates import nights as stay_nights

        if stay.get("total") is None:
            return None
        nights = stay_nights(checkin, checkout)
        total = Decimal(stay["total"])
        shares = split_amount(total, len(nights), self.currency)
        tax = lodging_tax(self.prop)
        include = bool(self.options.get("amounts_include_tax", True))
        prices = []
        for day, share in zip(nights, shares, strict=True):
            price = share
            if tax is not None and not tax_exempt(tax, foreign):
                rate = Decimal(tax.rate) / 100
                if include and not tax.included_in_price:
                    price = quantize(share / (1 + rate), self.currency)
                elif not include and tax.included_in_price:
                    price = quantize(share * (1 + rate), self.currency)
            prices.append({"date": day.isoformat(), "amount": str(price)})
        return prices

    def _check_ledger(self, stays: list[dict]) -> None:
        """Dry-run only: the earlier rows of the file already took these units or rooms?"""
        from apps.bookings.services.availability import availability
        from apps.core.dates import nights as stay_nights

        for stay in stays:
            checkin, checkout = date.fromisoformat(stay["checkin"]), date.fromisoformat(stay["checkout"])
            units = stay["adults"] + stay["children"] if stay["kind"] == "dorm" else 1
            for night in stay_nights(checkin, checkout):
                key = (stay["room_type_id"], night)
                if self.units_taken.get(key):
                    if key not in self.available:
                        free = availability(
                            property=self.prop,
                            checkin=night,
                            checkout=night + timedelta(days=1),
                            room_type_ids=[uuid.UUID(stay["room_type_id"])],
                        )
                        self.available[key] = int(free.get(uuid.UUID(stay["room_type_id"]), 0))
                    if self.available[key] - self.units_taken[key] < units:
                        raise DomainError(
                            "conflict", code="conflict_in_file", room_type=stay["room_type_code"], date=night
                        )
                if stay.get("room_id") and (stay["room_id"], night) in self.rooms_taken:
                    raise DomainError(
                        "conflict",
                        code="room_conflict_in_file",
                        room=stay.get("room_label"),
                        row=self.rooms_taken[(stay["room_id"], night)],
                    )

    def _take_ledger(self, stays: list[dict], row_number: int) -> None:
        from apps.core.dates import nights as stay_nights

        for stay in stays:
            checkin, checkout = date.fromisoformat(stay["checkin"]), date.fromisoformat(stay["checkout"])
            units = stay["adults"] + stay["children"] if stay["kind"] == "dorm" else 1
            for night in stay_nights(checkin, checkout):
                self.units_taken[(stay["room_type_id"], night)] += units
                self.units_by[(stay["room_type_id"], night)] = row_number
                if stay.get("room_id"):
                    self.rooms_taken[(stay["room_id"], night)] = row_number

    def _create_reservation(self, key: str, rows: list[ImportRow]):
        from apps.bookings.models import Reservation
        from apps.bookings.services.reservations import check_in, create_reservation
        from apps.bookings.types import ReservationRequest, StayRequest
        from apps.finance.services import get_or_create_folio, record_payment
        from apps.guests.services import upsert_guest

        values = self._group_values(rows)
        guest = values["guest"]
        stays_data = []
        for row in rows:
            for stay in row.data.get("stays") or []:
                stays_data.append(
                    {**stay, "checkin": row.data["checkin"], "checkout": row.data["checkout"],
                     "row": row.number,
                     "stage": row.data.get("stage")}
                )  # fmt: skip
        if self.dry:
            try:
                self._check_ledger(stays_data)
            except DomainError as exc:
                return ImportRow.Outcome.FAILED, message(exc.code, **exc.extra), None, {}
        # The booker first: the IVA exemption of the prices depends on the guest Housetel ends up with (an
        # existing guest may already have the nationality the file lacks).
        booker = upsert_guest(self.org, self._guest_input(guest), actor=self.actor)
        foreign = booker.is_foreign_non_resident
        requests = []
        for stay in stays_data:
            checkin, checkout = date.fromisoformat(stay["checkin"]), date.fromisoformat(stay["checkout"])
            requests.append(
                StayRequest(
                    room_type_id=uuid.UUID(stay["room_type_id"]),
                    rate_plan_id=uuid.UUID(stay["rate_plan_id"]),
                    checkin=checkin,
                    checkout=checkout,
                    adults=stay["adults"],
                    children=stay["children"],
                    room_id=uuid.UUID(stay["room_id"]) if stay.get("room_id") else None,
                    bed_id=uuid.UUID(stay["bed_id"]) if stay.get("bed_id") else None,
                    nightly_rates=self._nightly_rates(stay, checkin, checkout, foreign),
                )
            )
        extra = values["extra"]
        notes = [values["notes"]] if values["notes"] else []
        origin = []
        if extra.get("source"):
            origin.append(f"origen: {extra['source']}")
        if extra.get("third_party_id"):
            origin.append(f"n.º del canal: {extra['third_party_id']}")
        external = key if not key.startswith("fp-") else ""
        notes.append(
            f"Importada desde {self.job.source_label}"
            + (f" (reserva {external})" if external else "")
            + (f" · {', '.join(origin)}" if origin else "")
        )
        eta = extra.get("eta")
        source = "import" if "import" in Reservation.Source.values else "front_desk"
        request = ReservationRequest(
            property=self.prop,
            booker=booker,
            stays=requests,
            source=source,
            external_id=external[:120],
            external_payload={
                "import": {
                    "job_id": str(self.job.pk),
                    "source_system": self.job.source_system,
                    "external_id": key,
                    "rows": [row.number for row in rows],
                    "source": extra.get("source") or "",
                    "third_party_id": extra.get("third_party_id") or "",
                    "booked_at": extra.get("booked_at"),
                }
            },
            notes="\n".join(notes),
            special_requests=values["special_requests"],
            language=guest.get("language") or "es",
            eta=_time(eta),
            status="tentative" if values["tentative"] else "confirmed",
            allow_overbooking=False,
            enforce_restrictions=False,
            hold_minutes=0,
        )
        reservation = create_reservation(request, actor=self.actor)
        room_labels = []
        created = list(reservation.stays.order_by("created_at"))
        index = 0
        for stay, stay_request in zip(stays_data, requests, strict=True):
            units = stay_request.adults + stay_request.children if stay.get("kind") == "dorm" else 1
            for created_stay in created[index : index + units]:
                if stay.get("stage") == "in_house":
                    checked = check_in(created_stay, actor=self.actor, force=True)
                    if checked.room_id:
                        room_labels.append(checked.room.number)
            index += units
            self.track(stay["room_type_id"], stay_request.checkin, stay_request.checkout)
        payment_ids = []
        if values["paid"] > 0:
            payment = record_payment(
                get_or_create_folio(reservation),
                amount=values["paid"],
                method="other",
                reference=PAYMENT_REFERENCE,
                actor=None,
            )
            payment_ids.append(str(payment.pk))
        reservation.refresh_from_db()
        self.save_record(key, reservation)
        if self.dry:
            self._take_ledger(stays_data, rows[0].number)
        if room_labels:
            msg = message("created_in_house", code=reservation.code, room=", ".join(room_labels))
        else:
            msg = message("created_reservation", code=reservation.code)
        warning = self._total_warning(reservation, values)
        if warning:
            msg = {**msg, "es": f"{msg['es']} · {warning['es']}", "en": f"{msg['en']} · {warning['en']}"}
        return (
            ImportRow.Outcome.CREATED,
            msg,
            reservation,
            {"payment_ids": payment_ids, "guest_id": str(reservation.booker_id)},
        )

    def _total_warning(self, reservation, values: dict) -> dict | None:
        if values["total"] is None or not self.options.get("amounts_include_tax", True):
            return None
        nights = max((reservation.checkout_date - reservation.checkin_date).days, 1)
        difference = abs(Decimal(reservation.total_amount) - values["total"])
        if difference <= Decimal(nights * len(values["stays"] or [1])):
            return None
        return message(
            "total_differs", value=_money(reservation.total_amount), expected=_money(values["total"])
        )

    def _update_reservation(self, record: ImportedRecord, rows: list[ImportRow]):
        from apps.bookings.models import Reservation, Stay
        from apps.bookings.services.reservations import (
            cancel_reservation,
            check_in,
            modify_stay,
            update_reservation,
        )
        from apps.finance.services import get_or_create_folio, record_payment
        from apps.inventory.models import RoomType
        from apps.rates.models import RatePlan

        reservation = Reservation.objects.filter(pk=record.target_id, property=self.prop).first()
        if reservation is None:  # deleted in Housetel: import it again
            if not self.dry:
                ImportedRecord.objects.filter(pk=record.pk).delete()
            self.records.pop(record.external_id, None)
            return self._create_reservation(record.external_id, rows)
        if self.on_existing == "skip":
            return ImportRow.Outcome.SKIPPED, message("skipped_existing"), reservation, {}
        values = self._group_values(rows)
        if reservation.status in ("cancelled", "no_show", "checked_out"):
            return (
                ImportRow.Outcome.SKIPPED,
                message("skipped_inactive", status=reservation.get_status_display()),
                reservation,
                {},
            )
        if values["cancel"]:
            if reservation.status == "checked_in":
                return ImportRow.Outcome.FAILED, message("cancel_in_house"), reservation, {}
            status = next(
                row.data.get("status") for row in rows if row.data.get("status") in ("cancelled", "no_show")
            )
            # The imported payments mirrored money handled in the previous system (refunded or kept there):
            # voided with the cancellation, so the folio does not show a credit that does not exist.
            _void_imported_payments(reservation, self.actor, "Cancelada en el sistema anterior")
            cancel_reservation(
                reservation,
                reason=f"Cancelada en {self.job.source_label} (importación)",
                waive_fee=True,
                actor=self.actor,
                source="user",
            )
            label = "cancelada" if status == "cancelled" else "no-show"
            for stay in reservation.stays.all():
                self.track(stay.room_type_id, stay.checkin_date, stay.checkout_date)
            return ImportRow.Outcome.UPDATED, message("cancelled_from_source", value=label), reservation, {}

        changed: list[str] = []
        notes: list[dict] = []
        stays = list(reservation.stays.filter(status__in=["tentative", "confirmed", "checked_in"]))
        file_stays = []
        for row in rows:
            for stay in row.data.get("stays") or []:
                file_stays.append({**stay, "checkin": row.data["checkin"], "checkout": row.data["checkout"],
                                   "stage": row.data.get("stage")})  # fmt: skip
        if len(stays) == 1 and len(file_stays) == 1:
            stay, wanted = stays[0], file_stays[0]
            checkin, checkout = date.fromisoformat(wanted["checkin"]), date.fromisoformat(wanted["checkout"])
            kwargs = {}
            if stay.status != Stay.Status.CHECKED_IN and stay.checkin_date != checkin:
                kwargs["checkin"] = checkin
            if stay.checkout_date != checkout:
                kwargs["checkout"] = checkout
            if stay.status != Stay.Status.CHECKED_IN and str(stay.room_type_id) != wanted["room_type_id"]:
                kwargs["room_type"] = RoomType.objects.get(pk=wanted["room_type_id"])
            if str(stay.rate_plan_id) != wanted["rate_plan_id"]:
                kwargs["rate_plan"] = RatePlan.objects.get(pk=wanted["rate_plan_id"])
            if stay.adults != wanted["adults"]:
                kwargs["adults"] = wanted["adults"]
            if stay.children != wanted["children"]:
                kwargs["children"] = wanted["children"]
            if kwargs:
                modify_stay(stay, reprice=False, actor=self.actor, **kwargs)
                changed.append("estadía")
                self.track(
                    wanted["room_type_id"], min(checkin, stay.checkin_date), max(checkout, stay.checkout_date)
                )
            stay.refresh_from_db()
            if wanted.get("stage") == "in_house" and stay.status in (
                Stay.Status.CONFIRMED,
                Stay.Status.TENTATIVE,
            ):
                if wanted.get("room_id") and not stay.room_id:
                    from apps.bookings.services.reservations import assign_room
                    from apps.inventory.models import Room

                    assign_room(stay, Room.objects.get(pk=wanted["room_id"]), actor=self.actor)
                checked = check_in(stay, actor=self.actor, force=True)
                changed.append("check-in")
                notes.append(
                    message("checked_in_from_source", room=checked.room.number if checked.room_id else "—")
                )
        elif file_stays and (len(stays) != len(file_stays)):
            notes.append(message("multi_stay_not_updated"))

        free = {}
        extra = values["extra"]
        if values["special_requests"] and values["special_requests"] != reservation.special_requests:
            free["special_requests"] = values["special_requests"]
        eta = _time(extra.get("eta"))
        if eta and reservation.eta != eta:
            free["eta"] = eta.strftime("%H:%M")
        if values["notes"] and values["notes"] not in (reservation.notes or ""):
            free["notes"] = f"{reservation.notes}\n{values['notes']}".strip()
        if free:
            update_reservation(reservation, free, actor=self.actor, source="user")
            changed.append("datos")

        imported = _imported_paid(reservation)
        payment_ids = []
        if values["paid"] > imported:
            difference = values["paid"] - imported
            payment = record_payment(
                get_or_create_folio(reservation),
                amount=difference,
                method="other",
                reference=PAYMENT_REFERENCE,
                actor=None,
            )
            payment_ids.append(str(payment.pk))
            changed.append("pago")
            notes.append(message("payment_added", value=_money(difference)))
        elif values["paid"] < imported:
            notes.append(message("payment_lower", value=_money(values["paid"])))

        self.save_record(record.external_id, reservation)
        if "estadía" in changed:
            reservation.refresh_from_db()
            warning = self._total_warning(reservation, values)
            if warning:
                notes.append(warning)
        if not changed:
            base = message("unchanged")
            return ImportRow.Outcome.SKIPPED, _join(base, notes), reservation, {}
        base = message("updated_fields", value=", ".join(changed))
        return ImportRow.Outcome.UPDATED, _join(base, notes), reservation, {"payment_ids": payment_ids}

    # ---- Room types ---------------------------------------------------------------------------------

    def run_room_types(self) -> None:
        rows = self.rows()
        self.set_total(len(rows))
        for row in rows:
            self.simple_row(row, self._room_type)
            self.tick()

    def simple_row(self, row: ImportRow, handler) -> None:
        try:
            with self.unit():
                outcome, msg, target, label = handler(row)
                if self.dry:
                    raise _Rollback
        except _Rollback:
            self.set_result([row], outcome, msg)
            return
        except DomainError as exc:
            self.set_result([row], ImportRow.Outcome.FAILED, from_domain_error(exc))
            return
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the import
            self.set_result([row], ImportRow.Outcome.FAILED, _unexpected(exc, row))
            return
        self.set_result([row], outcome, msg, target=target, label=label)

    def _room_type(self, row: ImportRow):
        from apps.inventory.models import RoomType
        from apps.inventory.serializers import RoomTypeSerializer, validated
        from apps.inventory.services import bulk_create_rooms, provision_room_type, save_room_type
        from apps.rates.models import CancellationPolicy, RatePlan, Tax
        from apps.rates.services.provision import provision_rates

        data = row.data
        existing = (
            RoomType.objects.filter(property=self.prop, code=data["code"]).first() if data["code"] else None
        )
        record = self.record(row.external_id) if row.external_id else None
        if existing is None and record is not None:
            existing = RoomType.objects.filter(pk=record.target_id, property=self.prop).first()
        name = {"es": data["name"], "en": data.get("name_en") or data["name"]}
        fields = {
            key: data[key]
            for key in ("base_occupancy", "max_adults", "max_children", "max_occupancy")
            if data.get(key) is not None
        }
        if existing is not None:
            if self.on_existing == "skip":
                return ImportRow.Outcome.SKIPPED, message("skipped_existing"), existing, existing.code
            payload = {"name": name, **fields}
            if data.get("description"):
                payload["description"] = {**(existing.description or {}), "es": data["description"]}
            serializer = validated(
                RoomTypeSerializer, data=payload, instance=existing, partial=True,
                context={"property": self.prop},
                message="Hay datos inválidos en la categoría",
            )  # fmt: skip
            save_room_type(self.prop, data=serializer.validated_data, room_type=existing, actor=self.actor)
            if data.get("room_numbers"):
                bulk_create_rooms(
                    self.prop,
                    room_type=existing,
                    numbers=data["room_numbers"],
                    beds_per_room=data.get("beds_per_room"),
                    actor=self.actor,
                )
            self.save_record(row.external_id, existing)
            return ImportRow.Outcome.UPDATED, message("updated"), existing, existing.code
        payload = {"code": data["code"], "name": name, "kind": data["kind"], **fields}
        if data.get("description"):
            payload["description"] = {"es": data["description"]}
        room_type = provision_room_type(
            self.prop,
            data=payload,
            room_numbers=data.get("room_numbers") or [],
            beds_per_room=data.get("beds_per_room") if data["kind"] == "dorm" else None,
            actor=self.actor,
        )
        if data.get("base_price"):
            plans = list(RatePlan.objects.filter(property=self.prop, is_active=True).order_by("sort_order"))
            provision_rates(
                self.prop,
                room_type_prices={room_type.code: {"price": data["base_price"]}},
                plans=[{"code": plan.code, "kind": plan.kind} for plan in plans] or None,
                taxes_default=not Tax.objects.filter(property=self.prop).exists(),
                policies_default=not plans
                or not CancellationPolicy.objects.filter(property=self.prop).exists(),
                actor=self.actor,
            )
        self.save_record(row.external_id or room_type.code, room_type)
        return ImportRow.Outcome.CREATED, message("created"), room_type, room_type.code

    # ---- Rooms --------------------------------------------------------------------------------------

    def run_rooms(self) -> None:
        rows = self.rows()
        self.set_total(len(rows))
        for row in rows:
            self.simple_row(row, self._room)
            self.tick()

    def _room(self, row: ImportRow):
        from apps.inventory.models import Room
        from apps.inventory.numbering import infer_floor
        from apps.inventory.serializers import RoomSerializer, validated
        from apps.inventory.services import create_beds, save_room

        data = row.data
        existing = Room.objects.filter(property=self.prop, number=data["number"]).first()
        if existing is not None:
            if self.on_existing == "skip":
                return ImportRow.Outcome.SKIPPED, message("skipped_existing"), existing, existing.number
            payload = {key: data[key] for key in ("floor", "name", "building", "notes") if data.get(key)}
            if data.get("room_type_id") and str(existing.room_type_id) != data["room_type_id"]:
                payload["room_type"] = data["room_type_id"]
            if not payload:
                return ImportRow.Outcome.SKIPPED, message("unchanged"), existing, existing.number
            serializer = validated(
                RoomSerializer, data=payload, instance=existing, partial=True,
                context={"property": self.prop},
                message="Hay datos inválidos en la habitación",
            )  # fmt: skip
            room = save_room(self.prop, data=serializer.validated_data, room=existing, actor=self.actor)
            self.save_record(row.external_id, room)
            return (
                ImportRow.Outcome.UPDATED,
                message("updated_fields", value=_labels(payload)),
                room,
                room.number,
            )
        payload = {
            "number": data["number"],
            "room_type": data["room_type_id"],
            "floor": data.get("floor") or infer_floor(data["number"]),
            "name": data.get("name") or "",
            "building": data.get("building") or "",
            "notes": data.get("notes") or "",
        }
        serializer = validated(
            RoomSerializer,
            data=payload,
            context={"property": self.prop},
            message="Hay datos inválidos en la habitación",
        )
        room = save_room(self.prop, data=serializer.validated_data, actor=self.actor)
        if data.get("kind") == "dorm" and data.get("beds"):
            create_beds(room, count=int(data["beds"]), actor=self.actor)
        self.save_record(row.external_id, room)
        return ImportRow.Outcome.CREATED, message("created"), room, room.number

    # ---- Rollback -----------------------------------------------------------------------------------

    def revert(self) -> None:
        rows = list(
            self.job.rows.filter(
                outcome=ImportRow.Outcome.CREATED, target_type="bookings.reservation"
            ).order_by("number")
        )
        groups: dict[str, list[ImportRow]] = defaultdict(list)
        for row in rows:
            groups[str(row.target_id)].append(row)
        self.set_total(len(groups))
        reasons: Counter = Counter()
        reverted = 0
        for target_id, members in groups.items():
            code = self._revert_group(target_id, members)
            if code == "reverted":
                reverted += 1
            else:
                reasons[code] += 1
            self.tick()
        self.flush()
        job = ImportJob.objects.get(pk=self.job.pk)
        job.revert_summary = {
            "reverted": reverted,
            "not_reverted": sum(reasons.values()),
            "reasons": dict(reasons),
        }
        job.status = ImportJob.Status.REVERTED
        job.reverted_at = timezone.now()
        job.reverted_by = self.actor
        job.save(update_fields=["revert_summary", "status", "reverted_at", "reverted_by", "updated_at"])
        audit.record(
            action="imports.job_reverted",
            target=job,
            actor=self.actor,
            property=self.prop,
            summary=(
                f"Revirtió la importación {job.filename}: {reverted} reservas canceladas, "
                f"{sum(reasons.values())} no se revirtieron"
            ),
            changes={"reverted": reverted, "not_reverted": dict(reasons)},
        )
        self.job = job

    def _revert_group(self, target_id: str, rows: list[ImportRow]) -> str:
        from apps.bookings.models import Reservation
        from apps.bookings.services.reservations import cancel_reservation

        reservation = Reservation.objects.filter(pk=target_id, property=self.prop).first()
        if reservation is None:
            self._revert_note(rows, message("revert_missing"))
            return "revert_missing"
        if reservation.status == "checked_in":
            self._revert_note(rows, message("revert_in_house"))
            return "revert_in_house"
        if reservation.status not in ("tentative", "confirmed"):
            self._revert_note(rows, message("revert_not_active", status=reservation.get_status_display()))
            return "revert_not_active"
        imported_at = min((row.processed_at for row in rows if row.processed_at), default=None)
        payment_ids = {pid for row in rows for pid in (row.extra or {}).get("payment_ids", [])}
        activity = _activity(reservation, imported_at, payment_ids)
        if activity:
            self._revert_note(rows, message("revert_activity", value=activity))
            return "revert_activity"
        try:
            with transaction.atomic():
                _void_imported_payments(reservation, self.actor, "Reversión de importación", ids=payment_ids)
                cancel_reservation(
                    reservation,
                    reason=f"Importación revertida ({self.job.filename})",
                    waive_fee=True,
                    actor=self.actor,
                    source="user",
                )
                ImportedRecord.objects.filter(
                    property=self.prop, kind=self.job.kind, target_id=reservation.pk, created_by_job=self.job
                ).delete()
        except DomainError as exc:
            self._revert_note(rows, from_domain_error(exc))
            return exc.code or "error"
        for stay in reservation.stays.all():
            self.track(stay.room_type_id, stay.checkin_date, stay.checkout_date)
        now = timezone.now()
        for row in rows:
            row.outcome = ImportRow.Outcome.REVERTED
            row.outcome_message = message("reverted")
            row.processed_at = now
        ImportRow.objects.bulk_update(rows, ["outcome", "outcome_message", "processed_at"])
        return "reverted"

    def _revert_note(self, rows: list[ImportRow], msg: dict) -> None:
        for row in rows:
            row.extra = {**(row.extra or {}), "revert": msg}
        ImportRow.objects.bulk_update(rows, ["extra"])


# ---- helpers ------------------------------------------------------------------------------------------


def _unexpected(exc: Exception, row: ImportRow) -> dict:
    logger.exception("Import row %s of job %s failed", row.number, row.job_id)
    return message("internal_error", value=f"{type(exc).__name__}: {exc}"[:300])


def _time(value):
    if not value:
        return None
    from datetime import time

    try:
        hour, minute = (int(part) for part in str(value).split(":")[:2])
        return time(hour, minute)
    except (TypeError, ValueError):
        return None


def _money(value) -> str:
    amount = Decimal(value or 0)
    return "$ " + f"{amount:,.0f}".replace(",", ".")


def _labels(changes: dict) -> str:
    from apps.imports.messages import field_label

    return ", ".join(field_label(field) for field in changes)


def _join(base: dict, notes: list[dict]) -> dict:
    if not notes:
        return base
    return {
        "code": base["code"],
        "es": " · ".join([base["es"], *(note["es"] for note in notes)]),
        "en": " · ".join([base["en"], *(note["en"] for note in notes)]),
    }


def _void_imported_payments(reservation, actor, reason: str, ids=None) -> None:
    """Void the approved "Saldo importado" payments of the reservation (or only `ids`)."""
    from apps.finance.models import Payment
    from apps.finance.services import void_payment

    payments = Payment.objects.filter(
        folio__reservation=reservation,
        provider="manual",
        provider_reference=PAYMENT_REFERENCE,
        status=Payment.Status.APPROVED,
    )
    if ids is not None:
        payments = payments.filter(pk__in=list(ids))
    for payment in payments:
        void_payment(payment, reason=reason, actor=actor, confirm=True)


def _imported_paid(reservation) -> Decimal:
    from django.db.models import Sum

    from apps.finance.models import Payment

    total = Payment.objects.filter(
        folio__reservation=reservation,
        provider="manual",
        provider_reference=PAYMENT_REFERENCE,
        status=Payment.Status.APPROVED,
    ).aggregate(total=Sum("amount"))["total"]
    return total or Decimal("0")


def _activity(reservation, imported_at, payment_ids: set[str]) -> str:
    """What happened to the reservation after the import (people, not automations): other payments,
    charges, or audited changes by a user, a guest, the AI, the API or a channel. "" when nothing."""
    from apps.core.models import AuditEvent
    from apps.finance.models import Charge, Payment

    payments = Payment.objects.filter(folio__reservation=reservation).exclude(pk__in=payment_ids)
    if payments.exists():
        return "pagos"
    if Charge.objects.filter(folio__reservation=reservation, voided_at__isnull=True).exists():
        return "cargos"
    if imported_at is None:
        return ""
    stay_ids = [str(pk) for pk in reservation.stays.values_list("pk", flat=True)]
    events = AuditEvent.objects.filter(
        created_at__gt=imported_at, source__in=["user", "guest", "ai", "api", "channel"]
    ).filter(
        target_type__in=["bookings.reservation", "bookings.stay"],
        target_id__in=[str(reservation.pk), *stay_ids],
    )
    if events.exists():
        return "cambios"
    return ""
