"""Column mapping (file column → Housetel field) and value mapping (file category / plan → Housetel object).

- `suggest_mapping`: recognizes the column titles in Spanish or English (and the preset's own titles first).
- `value_candidates`: distinct values of the columns that need a value mapping (categories, rate plans) with
  the Housetel object each one matches automatically (by code, name in es/en, or a unique partial match).
"""

from collections import Counter

from apps.imports import normalize
from apps.imports.catalog import MAX_DISTINCT_VALUES, SAMPLE_VALUES, fold, spec
from apps.imports.models import ImportJob


def suggest_mapping(kind: str, preset: str, headers: list[str]) -> dict[str, str]:
    kind_spec = spec(kind)
    folded = [(header, fold(header)) for header in headers]
    mapping: dict[str, str] = {}
    used: set[str] = set()
    passes = []
    if preset == ImportJob.Preset.CLOUDBEDS:
        passes.append(lambda item: [fold(title) for title in item.cloudbeds])
    passes.append(lambda item: [fold(title) for title in item.aliases])
    for titles_of in passes:
        for item in kind_spec.fields:
            if item.code in mapping:
                continue
            titles = set(titles_of(item))
            for header, key in folded:
                if header not in used and key in titles:
                    mapping[item.code] = header
                    used.add(header)
                    break
    # "Nombre" + "Apellido" → first/last name; a lone "Nombre" is the full name.
    codes = {item.code for item in kind_spec.fields}
    if {"full_name", "first_name", "last_name"} <= codes:
        if "full_name" in mapping and "last_name" in mapping and "first_name" not in mapping:
            mapping["first_name"] = mapping.pop("full_name")
        elif "first_name" in mapping and "last_name" not in mapping and "full_name" not in mapping:
            mapping["full_name"] = mapping.pop("first_name")
    return {code: mapping[code] for code in [item.code for item in kind_spec.fields] if code in mapping}


def clean_mapping(kind: str, headers: list[str], mapping: dict) -> dict[str, str]:
    """Only known fields pointing to existing columns (a column feeds one field at most)."""
    kind_spec = spec(kind)
    valid_headers = set(headers)
    result: dict[str, str] = {}
    used: set[str] = set()
    for item in kind_spec.fields:
        header = (mapping or {}).get(item.code)
        if isinstance(header, str) and header in valid_headers and header not in used:
            result[item.code] = header
            used.add(header)
    return result


def column_samples(headers: list[str], rows: list[dict], limit: int = SAMPLE_VALUES) -> dict[str, list[str]]:
    samples: dict[str, list[str]] = {header: [] for header in headers}
    for raw in rows:
        for header in headers:
            value = (raw.get(header) or "").strip()
            bucket = samples[header]
            if value and value not in bucket and len(bucket) < limit:
                bucket.append(value)
        if all(len(bucket) >= limit for bucket in samples.values()):
            break
    return samples


def distinct_values(rows: list[dict], header: str, *, split: bool = False) -> list[tuple[str, int]]:
    counter: Counter = Counter()
    for raw in rows:
        value = (raw.get(header) or "").strip()
        if not value:
            continue
        for part in normalize.split_list(value) if split else [value]:
            counter[part] += 1
    return counter.most_common(MAX_DISTINCT_VALUES)


def _match(value: str, options: list[dict]) -> str:
    """Id of the option whose code or name (es/en) equals the value (folded); else a unique option whose name
    contains the value or is contained in it; else ""."""
    key = fold(value)
    if not key:
        return ""
    for option in options:
        if key in option["keys"]:
            return option["id"]
    partial = [
        option["id"]
        for option in options
        if any(len(k) >= 3 and (key in k or k in key) for k in option["keys"] if k)
    ]
    return partial[0] if len(set(partial)) == 1 else ""


def room_type_options(prop) -> list[dict]:
    from apps.inventory.models import RoomType

    options = []
    for room_type in RoomType.objects.filter(property=prop).order_by("sort_order", "code"):
        name = room_type.name or {}
        options.append(
            {
                "id": str(room_type.pk),
                "code": room_type.code,
                "name": {"es": name.get("es", ""), "en": name.get("en", "")},
                "kind": room_type.kind,
                "is_active": room_type.is_active,
                "max_adults": room_type.max_adults,
                "max_children": room_type.max_children,
                "max_occupancy": room_type.max_occupancy,
                "keys": {fold(room_type.code), fold(name.get("es")), fold(name.get("en"))} - {""},
            }
        )
    return options


def rate_plan_options(prop) -> list[dict]:
    from apps.rates.models import RatePlan

    options = []
    plans = (
        RatePlan.objects.filter(property=prop, is_active=True)
        .prefetch_related("room_types")
        .order_by("sort_order", "code")
    )
    for plan in plans:
        name = plan.name or {}
        options.append(
            {
                "id": str(plan.pk),
                "code": plan.code,
                "name": {"es": name.get("es", ""), "en": name.get("en", "")},
                "kind": plan.kind,
                "room_type_ids": sorted(str(rt.pk) for rt in plan.room_types.all()),
                "keys": {fold(plan.code), fold(name.get("es")), fold(name.get("en"))} - {""},
            }
        )
    return options


def public_options(options: list[dict]) -> list[dict]:
    return [{key: value for key, value in option.items() if key != "keys"} for option in options]


def value_candidates(job, rows: list[dict], *, room_types=None, rate_plans=None) -> dict:
    """{"room_type": [{"value", "count", "suggested", "selected"}], "rate_plan": [...]} for the columns mapped
    to fields with a value mapping; `selected` is the saved choice (or the suggestion)."""
    kind_spec = spec(job.kind)
    split = job.preset == ImportJob.Preset.CLOUDBEDS
    result: dict[str, list[dict]] = {}
    for item in kind_spec.fields:
        if not item.value_mapping or item.code not in job.mapping:
            continue
        options = (
            room_types if item.value_mapping == "room_type" and room_types is not None
            else rate_plans if item.value_mapping == "rate_plan" and rate_plans is not None
            else room_type_options(job.property) if item.value_mapping == "room_type"
            else rate_plan_options(job.property)
        )  # fmt: skip
        saved = (job.value_map or {}).get(item.value_mapping, {}) or {}
        entries = []
        for value, count in distinct_values(
            rows, job.mapping[item.code], split=split and item.code == "room_type"
        ):
            suggested = _match(value, options)
            selected = saved.get(value, suggested) if isinstance(saved, dict) else suggested
            entries.append(
                {"value": value, "count": count, "suggested": suggested, "selected": selected or ""}
            )
        result[item.value_mapping] = entries
    return result


def resolve_value(job, mapping_key: str, value: str, options: list[dict]) -> str:
    """Housetel id for a file value: the saved choice, else the automatic match ("" = unmapped)."""
    saved = (job.value_map or {}).get(mapping_key, {}) or {}
    if isinstance(saved, dict) and value in saved:
        return saved[value] or ""
    return _match(value, options)
