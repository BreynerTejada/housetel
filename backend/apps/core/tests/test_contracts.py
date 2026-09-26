"""Service contracts (spec §4.2 + plan §C) and shared types (plan Step 5).

Consumers in later phases call ONLY these functions, so names, parameter names, keyword-only markers,
defaults and return types are frozen here. Owners implement the bodies; changing a signature breaks this test
on purpose.
"""

import dataclasses
import inspect
import re
from importlib import import_module

import pytest

CONTRACTS = {
    # rates
    "apps.rates.services.quote.quote": (
        "(*, property, room_type, rate_plan, checkin, checkout, adults, children=0, children_ages=None, "
        "promo_code=None, guest_is_foreign_non_resident=False)"
    ),
    "apps.rates.services.quote.resolve_daily": "(room_type, rate_plan, start, end)",
    "apps.rates.services.quote.set_daily_rates": (
        "(*, property, room_type, rate_plan, start, end, price=None, restrictions=None, dow=None, "
        "source='manual', actor=None)"
    ),
    "apps.rates.services.provision.provision_rates": (
        "(property, *, room_type_prices, plans=None, taxes_default=True, policies_default=True, actor=None)"
    ),
    # bookings
    "apps.bookings.services.availability.availability": (
        "(*, property, checkin, checkout, room_type_ids=None)"
    ),
    "apps.bookings.services.availability.search_offers": (
        "(*, property, checkin, checkout, adults, children=0, children_ages=None, channel='direct', "
        "promo_code=None, guest_is_foreign_non_resident=False)"
    ),
    "apps.bookings.services.reservations.create_reservation": "(req, *, actor=None, source_label=None)",
    "apps.bookings.services.reservations.modify_stay": (
        "(stay, *, checkin=None, checkout=None, room_type=None, rate_plan=None, adults=None, children=None, "
        "reprice=True, actor=None)"
    ),
    "apps.bookings.services.reservations.cancel_reservation": (
        "(reservation, *, reason, waive_fee=False, actor=None, source='user')"
    ),
    "apps.bookings.services.reservations.assign_room": "(stay, room, *, bed=None, actor=None, force=False)",
    "apps.bookings.services.reservations.auto_assign_rooms": "(*, property, date_from, date_to, actor=None)",
    "apps.bookings.services.reservations.check_in": "(stay, *, actor=None, force=False)",
    "apps.bookings.services.reservations.check_out": "(stay, *, actor=None, force=False)",
    "apps.bookings.services.reservations.mark_no_show": "(reservation, *, actor=None, source='automation')",
    "apps.bookings.services.charges.post_room_charges": (
        "(stay, *, until_date, actor=None, source='automation')"
    ),
    # finance
    "apps.finance.services.get_or_create_folio": "(reservation, *, stay=None)",
    "apps.finance.services.post_charge": (
        "(folio, *, kind, amount, description, quantity=1, tax=None, tax_exempt=False, stay=None, "
        "night_date=None, extra=None, actor=None, source='user', business_date=None)"
    ),
    "apps.finance.services.void_charge": "(charge, *, reason, actor, confirm)",
    "apps.finance.services.record_payment": (
        "(folio, *, amount, method, reference='', actor=None, status='approved', provider='manual', "
        "payload=None)"
    ),
    "apps.finance.services.refund_payment": "(payment, *, amount, reason, actor, confirm)",
    "apps.finance.services.create_payment_intent": "(folio, *, amount, return_url, provider_kind='payments')",
    "apps.finance.services.sync_payment_intent": "(intent)",
    "apps.finance.services.folio_balance": "(folio)",
    "apps.finance.services.reservation_balance": "(reservation)",
    # inventory
    "apps.inventory.services.effective_attributes": "(room)",
    "apps.inventory.services.block_room": "(room, *, start, end, kind, reason, actor=None, bed=None)",
    "apps.inventory.services.release_block": "(block, *, actor=None)",
    "apps.inventory.services.set_housekeeping_status": "(room, status, *, actor=None, source='user')",
    "apps.inventory.services.provision_room_type": (
        "(property, *, data, room_numbers, floor=None, beds_per_room=None, actor=None)"
    ),
    "apps.inventory.services.validate_custom_values": "(defs, values)",
    # guests
    "apps.guests.services.upsert_guest": "(organization, data, *, actor=None)",
    "apps.guests.services.update_guest": "(guest, data, *, source='user', actor=None)",
    "apps.guests.services.add_document": "(guest, *, kind, file, uploaded_via='staff')",
    "apps.guests.services.find_duplicates": "(guest)",
    "apps.guests.services.merge_guests": "(primary, duplicate, *, actor)",
    # messaging / ai
    "apps.messaging.services.send_message": (
        "(*, property, template_code, guest=None, reservation=None, to=None, channels=('email',), "
        "context=None, language=None)"
    ),
    "apps.ai.llm.get_llm": "(property=None)",
    "apps.ai.types.LLMClient.generate": (
        "(self, messages, *, system=None, tools=None, response_schema=None, temperature=0.2)"
    ),
    "apps.ai.llm.SimulatedLLMClient.generate": (
        "(self, messages, *, system=None, tools=None, response_schema=None, temperature=0.2)"
    ),
    # core
    "apps.core.audit.record": (
        "(*, action, target=None, summary='', actor=None, source='user', changes=None, reversible=False, "
        "undo_data=None, property=None, organization=None, actor_label=None)"
    ),
    "apps.core.audit.register_undo": "(action, handler)",
    "apps.core.audit.undo": "(event, *, actor)",
    "apps.core.audit.diff": "(before, after)",
    "apps.core.alerts.raise_alert": (
        "(*, property, kind, severity, title, message, link='', dedupe_key, data=None, source='system')"
    ),
    "apps.core.alerts.resolve_alert": "(property, dedupe_key, *, actor=None)",
    "apps.core.integrations.register_provider": "(kind, mode, cls)",
    "apps.core.integrations.get_provider": "(property, kind)",
    "apps.core.integrations.get_setting": "(property, kind)",
    "apps.core.integrations.providers_for": "(kind)",
    "apps.core.integrations.default_mode": "(kind)",
    "apps.core.integrations.set_secrets": "(setting, data)",
    "apps.core.integrations.get_secrets": "(setting)",
    "apps.core.automation.register": "(item)",
    "apps.core.automation.get": "(code)",
    "apps.core.automation.all": "()",
    "apps.core.automation.is_enabled": "(code, property)",
    "apps.core.automation.params_for": "(code, property)",
    "apps.core.automation.run": "(code, property=None, *, params=None, triggered_by=None)",
    "apps.core.permissions.has_perm": "(user, prop, code)",
    "apps.core.permissions.codes_match": "(granted, code)",
    "apps.core.signals.send_on_commit": "(signal, **kwargs)",
    "apps.core.tokens.make_reservation_token": "(reservation)",
    "apps.core.tokens.read_reservation_token": "(token, *, max_age=None)",
    "apps.core.tokens.portal_url": "(reservation)",
    "apps.core.money.quantize": "(amount, currency='COP')",
    "apps.core.money.apply_percent": "(amount, percent)",
    "apps.core.dates.nights": "(checkin, checkout)",
    "apps.core.dates.daterange": "(start, end_exclusive)",
    "apps.core.dates.overlaps": "(a_start, a_end, b_start, b_end)",
    "apps.core.dates.property_now": "(property)",
    "apps.core.codes.generate_code": "(prefix='HT', length=6)",
    "apps.core.i18n.t": "(value, lang='es')",
    "apps.accounts.services.ensure_system_roles": "(organization)",
    "apps.accounts.services.add_member": (
        "(organization, user, role_code, *, all_properties=True, properties=None)"
    ),
}

# Return annotations written in spec §4.2 / plan §C (module prefixes and quotes are ignored).
RETURNS = {
    "apps.rates.services.quote.quote": "Quote",
    "apps.rates.services.quote.resolve_daily": "list[DayRate]",
    "apps.rates.services.quote.set_daily_rates": "int",
    "apps.rates.services.provision.provision_rates": "None",
    "apps.bookings.services.availability.availability": "dict[UUID, int]",
    "apps.bookings.services.availability.search_offers": "list[Offer]",
    "apps.bookings.services.reservations.create_reservation": "Reservation",
    "apps.bookings.services.reservations.modify_stay": "Stay",
    "apps.bookings.services.reservations.cancel_reservation": "Reservation",
    "apps.bookings.services.reservations.assign_room": "Stay",
    "apps.bookings.services.reservations.auto_assign_rooms": "AssignmentReport",
    "apps.bookings.services.reservations.check_in": "Stay",
    "apps.bookings.services.reservations.check_out": "Stay",
    "apps.bookings.services.reservations.mark_no_show": "Reservation",
    "apps.bookings.services.charges.post_room_charges": "list[Charge]",
    "apps.finance.services.get_or_create_folio": "Folio",
    "apps.finance.services.post_charge": "Charge",
    "apps.finance.services.void_charge": "Charge",
    "apps.finance.services.record_payment": "Payment",
    "apps.finance.services.refund_payment": "Refund",
    "apps.finance.services.create_payment_intent": "PaymentIntent",
    "apps.finance.services.sync_payment_intent": "PaymentIntent",
    "apps.finance.services.folio_balance": "Decimal",
    "apps.finance.services.reservation_balance": "Decimal",
    "apps.inventory.services.effective_attributes": "dict",
    "apps.inventory.services.block_room": "RoomBlock",
    "apps.inventory.services.release_block": "RoomBlock",
    "apps.inventory.services.set_housekeeping_status": "Room",
    "apps.inventory.services.provision_room_type": "RoomType",
    "apps.guests.services.upsert_guest": "Guest",
    "apps.guests.services.update_guest": "Guest",
    "apps.guests.services.add_document": "GuestDocument",
    "apps.guests.services.find_duplicates": "list[Guest]",
    "apps.guests.services.merge_guests": "Guest",
    "apps.messaging.services.send_message": "list[OutboundMessage]",
    "apps.ai.llm.get_llm": "LLMClient",
    "apps.ai.types.LLMClient.generate": "LLMResult",
    "apps.ai.llm.SimulatedLLMClient.generate": "LLMResult",
    "apps.core.audit.record": "AuditEvent",
    "apps.core.integrations.get_setting": "IntegrationSetting",
    "apps.core.permissions.has_perm": "bool",
    "apps.core.tokens.make_reservation_token": "str",
    "apps.core.tokens.read_reservation_token": "Reservation | None",
    "apps.core.tokens.portal_url": "str",
}

M = dataclasses.MISSING
DATACLASSES = {  # path: (frozen, [(field, default)])
    "apps.rates.types.NightPrice": (True, [
        ("date", M), ("base", M), ("extra_adults", M), ("extra_children", M), ("discount", M), ("total", M)]),
    "apps.rates.types.TaxLine": (True, [
        ("code", M), ("name", M), ("rate", M), ("amount", M), ("included", M), ("exempt", False)]),
    "apps.rates.types.DayRate": (True, [
        ("date", M), ("price", M), ("extra_adult_price", M), ("extra_child_price", M), ("min_los", M),
        ("max_los", M), ("closed_to_arrival", M), ("closed_to_departure", M), ("stop_sell", M),
        ("source", M)]),
    "apps.rates.types.Quote": (True, [
        ("room_type_id", M), ("rate_plan_id", M), ("checkin", M), ("checkout", M), ("adults", M),
        ("children", M), ("nights", M), ("subtotal", M), ("discount_total", M), ("taxes", M),
        ("tax_total", M), ("total", M), ("currency", M), ("restrictions_ok", M), ("violations", []),
        ("promo_applied", None)]),
    "apps.bookings.types.StayRequest": (False, [
        ("room_type_id", M), ("rate_plan_id", M), ("checkin", M), ("checkout", M), ("adults", M),
        ("children", 0), ("children_ages", []), ("room_id", None), ("bed_id", None), ("locked_room", False),
        ("occupants", []), ("nightly_rates", None)]),
    "apps.bookings.types.ReservationRequest": (False, [
        ("property", M), ("booker", M), ("stays", M), ("source", "front_desk"), ("channel_code", ""),
        ("external_id", ""), ("external_payload", {}), ("notes", ""), ("special_requests", ""),
        ("promo_code", ""), ("language", "es"), ("eta", None), ("status", "confirmed"),
        ("allow_overbooking", False), ("enforce_restrictions", True), ("hold_minutes", 20),
        ("guarantee", "none"), ("group_id", None), ("custom_values", {})]),
    "apps.bookings.types.Offer": (True, [
        ("room_type_id", M), ("rate_plan_id", M), ("available_units", M), ("units_needed", M), ("quote", M),
        ("total", M)]),
    "apps.bookings.types.AssignmentReport": (False, [("assigned", []), ("unassigned", []), ("messages", [])]),
    "apps.guests.types.GuestInput": (False, [
        ("first_name", M), ("last_name", M), ("email", ""), ("phone", ""), ("document_type", ""),
        ("document_number", ""), ("nationality", ""), ("country_of_residence", ""), ("city_of_residence", ""),
        ("birth_date", None), ("language", "es"), ("marketing_consent", False),
        ("data_processing_consent", False)]),
    "apps.ai.types.ToolCall": (False, [("name", M), ("arguments", M), ("id", "")]),
    "apps.ai.types.LLMResult": (False, [
        ("text", ""), ("tool_calls", []), ("data", None), ("provider", "simulated"), ("model", ""),
        ("simulated", True), ("usage", {})]),
    "apps.messaging.types.OutboundMessage": (False, [
        ("channel", M), ("to", M), ("status", M), ("subject", ""), ("body", ""), ("template_code", ""),
        ("provider_message_id", ""), ("error", ""), ("message_id", None)]),
    "apps.core.automation.RunResult": (True, [("status", "success"), ("summary", ""), ("details", {})]),
    "apps.core.automation.Automation": (True, [
        ("code", M), ("app", M), ("name_es", M), ("name_en", M), ("description_es", M), ("schedule", M),
        ("handler", M), ("default_enabled", True), ("scope", "property"), ("default_params", {}),
        ("description_en", "")]),
}  # fmt: skip

ERRORS = {  # path: (code, status, base)
    "apps.core.errors.DomainError": ("domain_error", 400, None),
    "apps.core.errors.ConfirmationRequired": ("confirmation_required", 400, "apps.core.errors.DomainError"),
    "apps.core.errors.PaymentRequiredError": ("organization_suspended", 402, "apps.core.errors.DomainError"),
    "apps.bookings.types.BookingError": ("booking_error", 400, "apps.core.errors.DomainError"),
    "apps.bookings.types.AvailabilityError": ("no_availability", 409, "apps.bookings.types.BookingError"),
    "apps.bookings.types.RestrictionError": (
        "restriction_violation",
        400,
        "apps.bookings.types.BookingError",
    ),
    "apps.bookings.types.InvalidStateError": ("invalid_state", 409, "apps.bookings.types.BookingError"),
    "apps.bookings.types.RoomNotReadyError": ("room_not_ready", 409, "apps.bookings.types.BookingError"),
    "apps.bookings.types.BalanceDueError": ("balance_due", 409, "apps.bookings.types.BookingError"),
    "apps.core.integrations.IntegrationNotAvailable": (
        "integration_not_available",
        400,
        "apps.core.errors.DomainError",
    ),
}


def resolve(path: str):
    module_path, _, name = path.rpartition(".")
    try:
        return getattr(import_module(module_path), name)
    except ModuleNotFoundError:
        owner_path, _, owner_name = module_path.rpartition(".")  # Class.method
        return getattr(getattr(import_module(owner_path), owner_name), name)


def return_annotation(func) -> str:
    """Normalized return annotation: no module prefixes, quotes or spaces (string annotations included)."""
    annotation = inspect.signature(func).return_annotation
    if annotation is inspect.Signature.empty:
        return ""
    text = annotation if isinstance(annotation, str) else inspect.formatannotation(annotation)
    text = re.sub(r"\b(?:[a-z_]\w*\.)+([A-Za-z_]\w*)", r"\1", text).replace("'", "").replace('"', "")
    return text.replace("NoneType", "None").replace(" ", "")


def bare_signature(func) -> str:
    signature = inspect.signature(func)
    params = [p.replace(annotation=inspect.Parameter.empty) for p in signature.parameters.values()]
    return str(inspect.Signature(params))


@pytest.mark.parametrize("path", sorted(CONTRACTS))
def test_contract_signature(path):
    assert bare_signature(resolve(path)) == CONTRACTS[path]


@pytest.mark.parametrize("path", sorted(RETURNS))
def test_contract_return_type(path):
    assert return_annotation(resolve(path)) == RETURNS[path].replace(" ", "")


@pytest.mark.parametrize("path", sorted(DATACLASSES))
def test_shared_dataclasses(path):
    cls = resolve(path)
    frozen, expected = DATACLASSES[path]
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen is frozen
    actual = []
    for f in dataclasses.fields(cls):
        default = (
            f.default if f.default is not M else (f.default_factory() if f.default_factory is not M else M)
        )
        actual.append((f.name, default))
    assert actual == expected


@pytest.mark.parametrize("path", sorted(ERRORS))
def test_domain_errors(path):
    cls = resolve(path)
    code, status, base = ERRORS[path]
    assert (cls.code, cls.status_code) == (code, status)
    if base:
        assert issubclass(cls, resolve(base))
