"""Row validation (synchronous, read-only on Housetel data): parses every row with the job's mapping and
options, stores the normalized values in `ImportRow.data`, the issues in `ImportRow.issues` and the row
status (valid / warning / error / skip), and the counts on the job.

It checks everything that can be known without writing: formats, required values, the category and plan
mapping, capacity, rooms, dates against the business date, repeated rows and records imported before.
What depends on the live inventory (availability, a room already taken) is checked by the dry-run and the
real run, which go through the booking services.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction

from apps.core.errors import DomainError
from apps.core.money import quantize
from apps.imports import mapping as mapping_svc
from apps.imports import normalize
from apps.imports.catalog import DATE_FORMATS, DEFAULT_OPTIONS, fold, spec
from apps.imports.messages import issue
from apps.imports.models import ImportedRecord, ImportJob, ImportRow

DATE_FIELDS = ("checkin", "checkout", "birth_date", "booked_at")
STATUS_BY_LEVEL = ("error", "skip", "warning")


# ---- Context ------------------------------------------------------------------------------------------


@dataclass
class Context:
    job: ImportJob
    prop: object
    today: date
    currency: str
    options: dict
    date_format: str
    room_types: list[dict] = field(default_factory=list)
    rate_plans: list[dict] = field(default_factory=list)
    rooms: dict[str, dict] = field(default_factory=dict)  # number → {id, room_type_id, is_active, beds}
    records: dict[str, str] = field(default_factory=dict)  # external id → target id (this source system)
    default_plan: dict | None = None

    def room_type(self, room_type_id: str) -> dict | None:
        return next((item for item in self.room_types if item["id"] == room_type_id), None)

    def rate_plan(self, plan_id: str) -> dict | None:
        return next((item for item in self.rate_plans if item["id"] == plan_id), None)


def build_context(job: ImportJob, raw_rows: list[dict]) -> Context:
    prop = job.property
    options = {**DEFAULT_OPTIONS, **(job.options or {})}
    date_format = options.get("date_format") if options.get("date_format") in DATE_FORMATS else "auto"
    if date_format == "auto":
        values = [
            (raw.get(job.mapping[code]) or "")
            for code in DATE_FIELDS
            if code in job.mapping
            for raw in raw_rows
        ]
        detected, ambiguous = normalize.detect_date_format(values)
        options["date_format_detected"] = detected
        options["date_format_ambiguous"] = ambiguous and any(normalize.numeric_date_parts(v) for v in values)
        date_format = detected
    ctx = Context(
        job=job,
        prop=prop,
        today=prop.business_date,
        currency=prop.currency or "COP",
        options=options,
        date_format=date_format,
    )
    if job.kind in (ImportJob.Kind.RESERVATIONS, ImportJob.Kind.ROOMS, ImportJob.Kind.ROOM_TYPES):
        ctx.room_types = mapping_svc.room_type_options(prop)
    if job.kind == ImportJob.Kind.RESERVATIONS:
        ctx.rate_plans = mapping_svc.rate_plan_options(prop)
        ctx.default_plan = default_plan(ctx.rate_plans, options.get("default_rate_plan") or "")
    if job.kind in (ImportJob.Kind.RESERVATIONS, ImportJob.Kind.ROOMS, ImportJob.Kind.ROOM_TYPES):
        from apps.inventory.models import Bed, Room

        beds = defaultdict(dict)
        for bed in Bed.objects.filter(room__property=prop, is_active=True).values("id", "room_id", "label"):
            beds[str(bed["room_id"])][fold(bed["label"])] = str(bed["id"])
        for room in Room.objects.filter(property=prop).values("id", "number", "room_type_id", "is_active"):
            ctx.rooms[fold(room["number"])] = {
                "id": str(room["id"]),
                "number": room["number"],
                "room_type_id": str(room["room_type_id"]),
                "is_active": room["is_active"],
                "beds": beds.get(str(room["id"]), {}),
            }
    ctx.records = {
        external_id: str(target_id)
        for external_id, target_id in ImportedRecord.objects.filter(
            property=prop, kind=job.kind, source_system=job.source_system
        ).values_list("external_id", "target_id")
    }
    return ctx


def default_plan(plans: list[dict], chosen: str) -> dict | None:
    if chosen:
        plan = next((item for item in plans if item["id"] == chosen), None)
        if plan is not None:
            return plan
    return next((item for item in plans if item["kind"] == "base"), None) or (plans[0] if plans else None)


# ---- Helpers ------------------------------------------------------------------------------------------


class Row:
    """Accessor over one row: mapped values, issues and normalized data."""

    def __init__(self, row: ImportRow, job: ImportJob):
        self.row = row
        self.mapping = job.mapping or {}
        self.issues: list[dict] = []
        self.data: dict = {}

    def get(self, code: str) -> str:
        header = self.mapping.get(code)
        if not header:
            return ""
        return " ".join(str(self.row.raw.get(header) or "").split())

    def mapped(self, code: str) -> bool:
        return code in self.mapping

    def add(self, level: str, msg_code: str, field: str = "", /, **params) -> None:
        self.issues.append(issue(level, msg_code, field, **params))

    def has(self, level: str) -> bool:
        return any(item["level"] == level for item in self.issues)


def _status(issues: list[dict]) -> str:
    levels = {item["level"] for item in issues}
    if "error" in levels:
        return ImportRow.Status.ERROR
    if "skip" in levels:
        return ImportRow.Status.SKIP
    if "warning" in levels:
        return ImportRow.Status.WARNING
    return ImportRow.Status.VALID


def _date(r: Row, code: str, ctx: Context, *, required=False, level="error") -> date | None:
    text = r.get(code)
    if not text:
        if required:
            r.add("error", "required", code, field=code)
        return None
    try:
        return normalize.parse_date(text, ctx.date_format)
    except (ValueError, OverflowError):
        r.add(level, "invalid_date", code, field=code, value=text)
        return None


def _int(r: Row, code: str, default: int | None = None) -> int | None:
    text = r.get(code)
    if not text:
        return default
    try:
        value = normalize.parse_int(text)
    except ValueError:
        r.add("error", "invalid_number", code, field=code, value=text)
        return default
    if value < 0:
        r.add("error", "invalid_number", code, field=code, value=text)
        return default
    return value


def _money(r: Row, code: str, ctx: Context) -> Decimal | None:
    text = r.get(code)
    if not text:
        return None
    try:
        value = normalize.parse_money(text, ctx.currency)
    except ValueError:
        r.add("error", "invalid_money", code, field=code, value=text)
        return None
    if value < 0:
        r.add("error", "negative_amount", code, field=code)
        return None
    return value


def _money_str(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def parse_guest(r: Row, ctx: Context) -> dict:
    """GuestInput values (+ gender, address) of the row; `missing_name` when there is no name at all."""
    first, last, full = r.get("first_name"), r.get("last_name"), r.get("full_name")
    if not first and not last and full:
        first, last = normalize.split_full_name(full)
    elif full and not first:
        first = normalize.split_full_name(full)[0] if not last else full
    if not first and last:
        first, last = last, ""
    guest = {"first_name": first[:100], "last_name": last[:100]}
    if not first:
        r.add("error", "missing_name", "full_name")
    email = r.get("email")
    if email:
        if normalize.is_valid_email(email):
            guest["email"] = normalize.clean_email(email)
        else:
            r.add("warning", "invalid_email", "email", value=email)
    phone = r.get("phone")
    if phone:
        guest["phone"] = phone[:32]
    for code in ("nationality", "country_of_residence"):
        text = r.get(code)
        if not text:
            continue
        try:
            guest[code] = normalize.parse_country(text)
        except ValueError:
            r.add("warning", "unknown_country", code, field=code, value=text)
    number = r.get("document_number")
    doc_type_text = r.get("document_type")
    if number:
        guest["document_number"] = "".join(number.replace(".", "").split()).upper()[:40]
        if doc_type_text:
            try:
                guest["document_type"] = normalize.parse_document_type(doc_type_text)
            except ValueError:
                guest["document_type"] = "OTHER"
                r.add("warning", "unknown_document_type", "document_type", value=doc_type_text)
        else:
            nationality = guest.get("nationality") or ""
            inferred = "CC" if nationality in ("", "CO") else "PA"
            guest["document_type"] = inferred
            r.add("warning", "document_type_inferred", "document_type", value=inferred)
    city = r.get("city_of_residence")
    if city:
        guest["city_of_residence"] = city[:100]
    birth = _date(r, "birth_date", ctx, level="warning")
    if birth is not None:
        if birth > ctx.today:
            r.add("warning", "birth_date_future", "birth_date")
        else:
            guest["birth_date"] = birth.isoformat()
    gender = r.get("gender")
    if gender:
        try:
            guest["gender"] = normalize.parse_gender(gender)
        except ValueError:
            r.add("warning", "unknown_gender", "gender", value=gender)
    language = r.get("language")
    lang = ""
    if language:
        try:
            lang = normalize.parse_language(language)
        except ValueError:
            r.add("warning", "unknown_language", "language", value=language)
    guest["language"] = lang or normalize.default_language(
        guest.get("nationality", ""), guest.get("country_of_residence", "")
    )
    address = r.get("address")
    if address:
        guest["address"] = address[:255]
    return guest


def guest_key(guest: dict) -> str:
    if guest.get("document_number"):
        return f"doc:{guest.get('document_type', '')}:{guest['document_number']}"
    if guest.get("email"):
        return f"email:{guest['email']}"
    if guest.get("phone"):
        return normalize.fingerprint("phone", guest.get("first_name"), guest.get("last_name"), guest["phone"])
    return normalize.fingerprint(
        "name", guest.get("first_name"), guest.get("last_name"), guest.get("birth_date") or ""
    )


# ---- Guests -------------------------------------------------------------------------------------------


def validate_guests(job: ImportJob, rows: list[Row], ctx: Context) -> None:
    seen: dict[str, int] = {}
    on_existing = ctx.options.get("on_existing", "update")
    for r in rows:
        guest = parse_guest(r, ctx)
        key = r.get("external_id") or guest_key(guest)
        r.data = {"guest": guest}
        r.row.external_id = key[:200]
        r.row.group_key = ""
        if key in seen:
            r.add("warning", "duplicate_row", "", row=seen[key])
        else:
            seen[key] = r.row.number
        if key in ctx.records:
            if on_existing == "skip":
                r.add("skip", "exists_skip")
            else:
                r.add("info", "exists_update")


# ---- Reservations -------------------------------------------------------------------------------------


def _split_evenly(total: int, parts: int, minimum: int = 0) -> list[int]:
    base, remainder = divmod(total, parts)
    shares = [base + (1 if index < remainder else 0) for index in range(parts)]
    return [max(minimum, share) for share in shares]


def _reservation_row(r: Row, ctx: Context, split_rooms: bool) -> None:
    job = ctx.job
    checkin = _date(r, "checkin", ctx, required=True)
    checkout = _date(r, "checkout", ctx)
    nights = _int(r, "nights")
    if checkin and not checkout and nights:
        checkout = checkin + timedelta(days=nights)
    elif checkin and checkout and nights and (checkout - checkin).days != nights:
        r.add("warning", "nights_mismatch", "nights", value=nights)
    if checkin and not checkout and not r.has("error"):
        r.add("error", "required", "checkout", field="checkout")
    if checkin and checkout and checkout <= checkin:
        r.add("error", "dates_order", "checkout")

    status_text = r.get("status")
    status = ""
    if status_text:
        try:
            status = normalize.parse_status(status_text)
        except ValueError:
            r.add("warning", "unknown_status", "status", value=status_text)

    stage = ""
    today = ctx.today
    if checkin and checkout and checkout > checkin:
        if status == "cancelled":
            r.add("skip", "skip_cancelled", "status")
        elif status == "no_show":
            r.add("skip", "skip_no_show", "status")
        elif status == "checked_out":
            r.add("skip", "skip_checked_out", "status")
        elif status == "in_house":
            if checkin > today:
                r.add("error", "in_house_future", "checkin", date=checkin.isoformat())
            elif checkout <= today:
                r.add("error", "in_house_ended", "checkout", date=checkout.isoformat())
            else:
                stage = "in_house"
        elif checkout <= today:
            r.add("skip", "skip_past", "checkout", date=checkout.isoformat())
        elif checkin < today:
            if status:
                r.add("skip", "skip_arrival_passed", "checkin", date=checkin.isoformat())
            else:
                stage = "in_house"
                r.add("warning", "assumed_in_house", "status")
        else:
            stage = "future"
            if status == "tentative":
                r.add("info", "tentative_no_expiry", "status")

    adults = _int(r, "adults")
    if adults is None:
        adults = 1
        r.add("warning", "adults_default", "adults")
    children = _int(r, "children", 0) or 0

    type_text = r.get("room_type")
    type_values = normalize.split_list(type_text) if split_rooms else ([type_text] if type_text else [])
    if not type_values:
        r.add("error", "required", "room_type", field="room_type")
    number_text = r.get("room_number")
    number_values = (
        normalize.split_list(number_text) if split_rooms else ([number_text] if number_text else [])
    )
    if split_rooms and len(type_values) == 1 and len(number_values) > 1:
        type_values = type_values * len(number_values)  # "Doble" + "101, 102": two rooms of one category
    if len(type_values) > 1:
        r.add("warning", "multi_room_split", "room_type")
    if number_values and len(number_values) != len(type_values):
        number_values = []

    plan_text = r.get("rate_plan")
    if plan_text:
        plan_id = mapping_svc.resolve_value(job, "rate_plan", plan_text, ctx.rate_plans)
        plan = ctx.rate_plan(plan_id) if plan_id else None
        if plan is None:
            r.add("error", "unmapped_rate_plan", "rate_plan", value=plan_text)
    else:
        plan = ctx.default_plan
        if plan is None:
            r.add("error", "no_default_plan", "rate_plan")

    total = _money(r, "total_amount", ctx)
    paid = _money(r, "paid_amount", ctx)
    balance = _money(r, "balance_due", ctx)
    if paid is None and total is not None and balance is not None:
        paid = max(total - balance, Decimal("0"))
    elif paid is not None and total is not None and balance is not None:
        expected = total - balance
        if abs(expected - paid) > Decimal("1"):
            r.add("warning", "balance_mismatch", "paid_amount", paid=paid, expected=expected)
    paid = paid or Decimal("0")
    if total is None:
        r.add("info", "no_total", "total_amount")
    elif paid > total:
        r.add("warning", "paid_exceeds_total", "paid_amount", paid=paid, total=total)

    count = max(len(type_values), 1)
    adult_shares = _split_evenly(adults, count, minimum=1 if count > 1 else 0)
    child_shares = _split_evenly(children, count)
    total_shares = (
        [quantize(value, ctx.currency) for value in _split_money(total, count, ctx.currency)]
        if total is not None
        else [None] * count
    )
    stays = []
    for index, value in enumerate(type_values):
        room_type_id = mapping_svc.resolve_value(job, "room_type", value, ctx.room_types)
        room_type = ctx.room_type(room_type_id) if room_type_id else None
        if room_type is None:
            r.add("error", "unmapped_room_type", "room_type", value=value)
            continue
        label = room_type["code"]
        if not room_type["is_active"]:
            r.add("error", "room_type_inactive", "room_type", room_type=label)
        stay_adults, stay_children = adult_shares[index], child_shares[index]
        if room_type["kind"] == "dorm":
            if stay_children and not room_type["max_children"]:
                r.add("error", "dorm_children", "children", room_type=label)
            if stay_adults + stay_children < 1:
                r.add("error", "capacity", "adults", room_type=label, **_capacity(room_type))
        elif (
            stay_adults < 1
            or stay_adults > room_type["max_adults"]
            or stay_children > room_type["max_children"]
            or stay_adults + stay_children > room_type["max_occupancy"]
        ):
            r.add("error", "capacity", "adults", room_type=label, **_capacity(room_type))
        if plan is not None and room_type_id not in plan["room_type_ids"]:
            r.add("error", "plan_not_for_type", "rate_plan", plan=plan["code"], room_type=label)
        stay = {
            "room_type_id": room_type_id,
            "room_type_code": label,
            "kind": room_type["kind"],
            "rate_plan_id": plan["id"] if plan else None,
            "adults": stay_adults,
            "children": stay_children,
            "room_id": None,
            "bed_id": None,
            "room_label": "",
            "total": _money_str(total_shares[index]),
        }
        number = number_values[index] if index < len(number_values) else ""
        if number:
            _assign_room(r, ctx, stay, number, stage, room_type)
        elif stage == "in_house":
            r.add("warning", "room_auto", "room_number")
        stays.append(stay)

    guest = parse_guest(r, ctx)
    external = r.get("external_id")
    if external:
        key = external
    else:
        key = normalize.fingerprint(
            guest.get("first_name"), guest.get("last_name"), checkin, checkout, type_text
        )
        r.add("warning", "external_id_missing", "external_id")
    eta = None
    eta_text = r.get("eta")
    if eta_text:
        try:
            eta = normalize.parse_time(eta_text).strftime("%H:%M")
        except ValueError:
            r.add("warning", "invalid_time", "eta", field="eta", value=eta_text)
    booked_text = r.get("booked_at")
    booked = None
    if booked_text:
        try:
            booked = normalize.parse_date(booked_text, ctx.date_format).isoformat()
        except (ValueError, OverflowError):
            booked = booked_text[:40]
    r.row.external_id = key[:200]
    r.row.group_key = key[:200]
    r.data = {
        "stage": stage,
        "status": status,
        "tentative": status == "tentative",
        "checkin": checkin.isoformat() if checkin else None,
        "checkout": checkout.isoformat() if checkout else None,
        "stays": stays,
        "total": _money_str(total),
        "paid": _money_str(paid),
        "guest": guest,
        "extra": {
            "source": r.get("source")[:100],
            "third_party_id": r.get("third_party_id")[:100],
            "booked_at": booked,
            "eta": eta,
            "special_requests": r.get("special_requests"),
            "notes": r.get("notes"),
        },
    }


def _split_money(total: Decimal, parts: int, currency: str) -> list[Decimal]:
    from apps.bookings.services.pricing import split_amount

    return split_amount(total, parts, currency)


def _capacity(room_type: dict) -> dict:
    return {
        "max_adults": room_type["max_adults"],
        "max_children": room_type["max_children"],
        "max_occupancy": room_type["max_occupancy"],
    }


def _assign_room(r: Row, ctx: Context, stay: dict, number: str, stage: str, room_type: dict) -> None:
    room = ctx.rooms.get(fold(number))
    in_house = stage == "in_house"
    if room is None or not room["is_active"]:
        if in_house:
            r.add("error", "room_not_found_in_house", "room_number", value=number)
        else:
            r.add("warning", "room_not_found", "room_number", value=number)
        return
    if room["room_type_id"] != stay["room_type_id"]:
        other = ctx.room_type(room["room_type_id"])
        other_code = other["code"] if other else "?"
        if in_house:
            r.add(
                "error", "room_other_type_in_house", "room_number",
                room=room["number"], room_type=other_code, expected=room_type["code"],
            )  # fmt: skip
        else:
            r.add("warning", "room_other_type", "room_number", room=room["number"], room_type=other_code)
        return
    stay["room_id"] = room["id"]
    stay["room_label"] = room["number"]
    bed_text = r.get("bed")
    if room_type["kind"] == "dorm" and bed_text:
        bed_id = room["beds"].get(fold(bed_text))
        if bed_id and stay["adults"] + stay["children"] == 1:
            stay["bed_id"] = bed_id
            stay["room_label"] = f"{room['number']} · {bed_text}"
        elif not bed_id:
            r.add("warning", "bed_not_found", "bed", value=bed_text, room=room["number"])


def validate_reservations(job: ImportJob, rows: list[Row], ctx: Context) -> None:
    split_rooms = job.preset == ImportJob.Preset.CLOUDBEDS
    for r in rows:
        _reservation_row(r, ctx, split_rooms)
    groups: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        groups[r.row.group_key].append(r)
    on_existing = ctx.options.get("on_existing", "update")
    for key, members in groups.items():
        active = [r for r in members if not r.has("skip")]
        if len(members) > 1:
            numbers = ", ".join(str(r.row.number) for r in members)
            for r in members:
                r.add("info", "group_rows", "external_id", count=len(members), rows=numbers)
        failing = [r for r in active if r.has("error")]
        if failing:
            for r in active:
                if not r.has("error"):
                    r.add("error", "group_has_errors", "", row=failing[0].row.number)
        if active:
            first = active[0].data.get("guest", {})
            for r in active[1:]:
                other = r.data.get("guest", {})
                if fold(other.get("first_name")) != fold(first.get("first_name")) and other.get("first_name"):
                    r.add("warning", "group_guest_differs", "full_name", row=active[0].row.number)
        if key in ctx.records:
            for r in members:
                if on_existing == "skip":
                    if not r.has("skip"):
                        r.add("skip", "exists_skip", "external_id")
                    continue
                cancel = [i for i in r.issues if i["code"] in ("skip_cancelled", "skip_no_show")]
                if cancel:  # imported before and cancelled now: the run cancels it in Housetel
                    r.issues = [i for i in r.issues if i not in cancel]
                    r.add("info", "exists_cancel", "status")
                elif not r.has("skip"):
                    r.add("info", "exists_update", "external_id")


# ---- Room types ---------------------------------------------------------------------------------------


def validate_room_types(job: ImportJob, rows: list[Row], ctx: Context) -> None:
    from apps.inventory.numbering import duplicates_in, parse_room_numbers
    from apps.inventory.serializers import sanitize_code

    on_existing = ctx.options.get("on_existing", "update")
    existing_codes = {item["code"]: item for item in ctx.room_types}
    seen: dict[str, int] = {}
    taken_numbers: dict[str, int] = {}
    for r in rows:
        name = r.get("name")
        if not name:
            r.add("error", "required", "name", field="name")
        code = sanitize_code(r.get("code") or name)
        kind_text = r.get("kind")
        kind = "private"
        if kind_text:
            try:
                kind = normalize.parse_room_kind(kind_text)
            except ValueError:
                r.add("error", "invalid_kind", "kind", value=kind_text)
        values = {
            code_: _int(r, code_)
            for code_ in ("base_occupancy", "max_adults", "max_children", "max_occupancy", "beds_per_room")
        }
        numbers: list[str] = []
        numbers_text = r.get("room_numbers")
        if numbers_text:
            try:
                numbers = parse_room_numbers(numbers_text)
            except DomainError:
                r.add("error", "invalid_room_numbers", "room_numbers", value=numbers_text)
            repeated = duplicates_in(numbers)
            if repeated:
                r.add("error", "invalid_room_numbers", "room_numbers", value=", ".join(repeated))
        price = _money(r, "base_price", ctx)
        if price is not None and price <= 0:
            r.add("error", "invalid_money", "base_price", field="base_price", value=r.get("base_price"))
            price = None
        existing = existing_codes.get(code) if code else None
        record = ctx.records.get(code) if code else None
        if record and not existing:
            existing = ctx.room_type(record)
        if code and code in seen:
            r.add("error", "code_repeated", "code", value=code, row=seen[code])
        elif code:
            seen[code] = r.row.number
        if existing is not None:
            if on_existing == "skip":
                r.add("skip", "room_type_exists_skip", "code", value=existing["code"])
            else:
                r.add("info", "room_type_exists_update", "code", value=existing["code"])
        new_numbers = [number for number in numbers if fold(number) not in ctx.rooms]
        taken = [number for number in numbers if fold(number) in ctx.rooms]
        if taken and existing is None:
            r.add("error", "room_numbers_taken", "room_numbers", value=", ".join(taken[:10]))
        for number in new_numbers:
            if number in taken_numbers:
                r.add("error", "number_repeated", "room_numbers", value=number, row=taken_numbers[number])
            else:
                taken_numbers[number] = r.row.number
        if kind == "dorm" and new_numbers and not values["beds_per_room"] and existing is None:
            r.add("error", "dorm_beds_required", "beds_per_room")
        if price is not None and existing is None:
            r.add("info", "rates_added", "base_price", value=f"$ {price:,.0f}".replace(",", "."))
        r.row.external_id = (code or fold(name))[:200]
        r.row.group_key = ""
        r.data = {
            "code": code,
            "name": name[:100],
            "name_en": r.get("name_en")[:100],
            "kind": kind,
            **{key: value for key, value in values.items() if value is not None},
            "room_numbers": new_numbers,
            "base_price": _money_str(price),
            "description": r.get("description")[:2000],
            "existing_id": existing["id"] if existing else None,
        }


# ---- Rooms --------------------------------------------------------------------------------------------


def validate_rooms(job: ImportJob, rows: list[Row], ctx: Context) -> None:
    on_existing = ctx.options.get("on_existing", "update")
    seen: dict[str, int] = {}
    for r in rows:
        number = r.get("number")[:20]
        if not number:
            r.add("error", "required", "number", field="number")
        type_text = r.get("room_type")
        room_type = None
        if not type_text:
            r.add("error", "required", "room_type", field="room_type")
        else:
            room_type_id = mapping_svc.resolve_value(job, "room_type", type_text, ctx.room_types)
            room_type = ctx.room_type(room_type_id) if room_type_id else None
            if room_type is None:
                r.add("error", "unmapped_room_type", "room_type", value=type_text)
        beds = _int(r, "beds")
        existing = ctx.rooms.get(fold(number)) if number else None
        if number and fold(number) in seen:
            r.add("error", "number_repeated", "number", value=number, row=seen[fold(number)])
        elif number:
            seen[fold(number)] = r.row.number
        if existing is not None:
            if on_existing == "skip":
                r.add("skip", "room_exists_skip", "number", value=existing["number"])
            else:
                r.add("info", "room_exists_update", "number", value=existing["number"])
        elif room_type is not None and room_type["kind"] == "dorm" and not beds:
            r.add("error", "dorm_beds_required", "beds")
        r.row.external_id = number
        r.row.group_key = ""
        r.data = {
            "number": number,
            "room_type_id": room_type["id"] if room_type else None,
            "room_type_code": room_type["code"] if room_type else "",
            "kind": room_type["kind"] if room_type else "",
            "floor": r.get("floor")[:20],
            "name": r.get("name")[:100],
            "beds": beds,
            "building": r.get("building")[:50],
            "notes": r.get("notes"),
            "existing_id": existing["id"] if existing else None,
        }


VALIDATORS = {
    ImportJob.Kind.GUESTS: validate_guests,
    ImportJob.Kind.RESERVATIONS: validate_reservations,
    ImportJob.Kind.ROOM_TYPES: validate_room_types,
    ImportJob.Kind.ROOMS: validate_rooms,
}


def missing_required(job: ImportJob) -> list[str]:
    """Required fields (and "one of" groups) the mapping does not cover."""
    kind_spec = spec(job.kind)
    missing = [item.code for item in kind_spec.fields if item.required and item.code not in job.mapping]
    for group in kind_spec.one_of:
        if not any(code in job.mapping for code in group):
            missing.append("|".join(group))
    return missing


def validate_job(job: ImportJob) -> ImportJob:
    """Validate every row (replaces previous issues and invalidates a previous dry-run)."""
    rows = list(job.rows.order_by("number"))
    ctx = build_context(job, [row.raw for row in rows])
    wrapped = [Row(row, job) for row in rows]
    VALIDATORS[job.kind](job, wrapped, ctx)
    counts: Counter = Counter()
    for r in wrapped:
        r.row.issues = r.issues
        r.row.data = r.data
        r.row.status = _status(r.issues)
        r.row.dry_outcome = ""
        r.row.dry_message = {}
        counts[r.row.status] += 1
    with transaction.atomic():
        ImportRow.objects.bulk_update(
            [r.row for r in wrapped],
            ["issues", "data", "status", "external_id", "group_key", "dry_outcome", "dry_message"],
            batch_size=500,
        )
        job.options = {**job.options, **_detected(ctx.options)}
        job.counts = {status: counts.get(status, 0) for status in ("valid", "warning", "error", "skip")}
        job.status = ImportJob.Status.VALIDATED
        job.dry_run_at = None
        job.dry_run_summary = {}
        job.error = ""
        job.save(
            update_fields=[
                "options",
                "counts",
                "status",
                "dry_run_at",
                "dry_run_summary",
                "error",
                "updated_at",
            ]
        )
    return job


def _detected(options: dict) -> dict:
    return {key: options[key] for key in ("date_format_detected", "date_format_ambiguous") if key in options}
