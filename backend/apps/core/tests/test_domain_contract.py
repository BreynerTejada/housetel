"""Contract test for the core domain model (spec §4 + plan §C/Step 4).

Later phases depend on these names: every field listed in the spec must exist with the right relation
target, nullability, choice values and money precision. Owners may ADD fields to their own models; they may
not remove or rename these.
"""

import pytest
from django.apps import apps
from django.db import models

SPEC_FIELDS = {
    "core.Organization": "name slug legal_name nit country status trial_ends_at settings",
    "core.Property": (
        "organization name slug property_type description address city department country latitude "
        "longitude timezone currency default_language check_in_time check_out_time phone email website "
        "rnt_number nit legal_name star_rating house_rules business_date marketplace_listed commission_rate "
        "branding status settings"
    ),
    "core.AuditEvent": (
        "organization property actor actor_label source action target_type target_id summary changes "
        "reversible undo_data undone_at undone_by request_id"
    ),
    "core.Alert": "property kind severity title message link dedupe_key source data resolved_at resolved_by",
    "core.IntegrationSetting": (
        "property kind mode enabled config secrets_encrypted status status_message last_checked_at"
    ),
    "core.AutomationSetting": "property code enabled params",
    "core.AutomationRun": "property code status started_at finished_at summary details",
    "accounts.User": "email full_name language phone is_platform_admin",
    "accounts.Role": "organization code name description is_system permissions",
    "accounts.Membership": "user organization role all_properties properties is_active",
    "accounts.Invitation": "organization email role properties token expires_at accepted_at invited_by",
    "inventory.Amenity": "organization code name icon category",
    "inventory.RoomType": (
        "property code name description kind base_occupancy max_adults max_children max_occupancy beds "
        "size_m2 view smoking_allowed accessible amenities color housekeeping_minutes sort_order is_active "
        "custom_values"
    ),
    "inventory.Room": (
        "property room_type number name floor building overrides extra_amenities removed_amenities "
        "custom_values housekeeping_status is_active sort_order notes connecting_rooms"
    ),
    "inventory.Bed": "room label bed_type is_active",
    "inventory.CustomFieldDefinition": (
        "organization property applies_to key label field_type options required default_value "
        "show_in_marketplace sort_order"
    ),
    "inventory.Photo": "property room_type room image caption sort_order",
    "inventory.RoomBlock": "room bed start_date end_date kind reason created_by released_at",
    "rates.Tax": (
        "property code name rate applies_to included_in_price exempt_foreign_non_residents is_active"
    ),
    "rates.CancellationPolicy": (
        "property name non_refundable free_until_hours_before penalty_type penalty_value description"
    ),
    "rates.RatePlan": (
        "property code name kind parent derivation_type derivation_value room_types meal_plan "
        "cancellation_policy deposit_percent is_public channels min_los_default is_active sort_order"
    ),
    "rates.RoomTypeRateDefaults": (
        "room_type rate_plan price dow_adjustments extra_adult_price extra_child_price child_age_limit "
        "single_occupancy_price"
    ),
    "rates.Season": "property name start_date end_date priority color",
    "rates.SeasonRate": "season room_type rate_plan price dow_adjustments",
    "rates.DailyRate": (
        "room_type rate_plan date price extra_adult_price extra_child_price min_los max_los "
        "closed_to_arrival closed_to_departure stop_sell source updated_by"
    ),
    "rates.Extra": "property code name price charge_type tax sellable_online is_active",
    "rates.PromoCode": (
        "property code discount_type value valid_from valid_to stay_from stay_to rate_plans max_uses "
        "uses is_active"
    ),
    "bookings.ReservationGroup": "property name contact_guest notes",
    "bookings.Reservation": (
        "property code status source channel_code external_id external_payload booker group checkin_date "
        "checkout_date adults children currency total_amount language eta special_requests notes promo_code "
        "guarantee cancellation_policy_snapshot cancelled_at cancellation_reason cancellation_fee created_by "
        "custom_values tags hold_expires_at"
    ),
    "bookings.Stay": (
        "reservation room_type rate_plan room bed checkin_date checkout_date adults children children_ages "
        "occupants nightly_rates total_amount status locked_room checked_in_at checked_out_at"
    ),
    "bookings.InventoryDay": "property room_type date total_units sold_units blocked_units",
    "guests.Guest": (
        "organization first_name last_name email phone document_type document_number nationality "
        "country_of_residence city_of_residence birth_date gender address language is_vip tags notes "
        "preferences marketing_consent data_processing_consent_at custom_values blacklisted merged_into"
    ),
    "guests.GuestDocument": "guest kind file uploaded_via",
    "finance.Folio": "property reservation stay guest folio_type status currency closed_at",
    "finance.Charge": (
        "folio business_date kind description quantity unit_price amount tax tax_amount stay night_date "
        "extra posted_by source voided_at voided_by void_reason"
    ),
    "finance.Payment": (
        "folio amount method status provider provider_reference provider_payload business_date "
        "received_by notes"
    ),
    "finance.Refund": "payment amount status provider_reference reason approved_by",
    "finance.PaymentIntent": (
        "property folio amount currency provider mode reference checkout_url status expires_at "
        "return_url payload"
    ),
    "finance.CashShift": (
        "property user opened_at closed_at opening_float expected_cash counted_cash difference notes"
    ),
}

RELATIONS = {  # field → target model (and whether the spec marks it nullable)
    "core.Property.organization": ("core.Organization", False),
    "core.AuditEvent.property": ("core.Property", True),
    "core.AuditEvent.actor": ("accounts.User", True),
    "core.IntegrationSetting.property": ("core.Property", True),
    "accounts.Role.organization": ("core.Organization", True),
    "accounts.Membership.properties": ("core.Property", None),
    "inventory.Amenity.organization": ("core.Organization", True),
    "inventory.RoomType.property": ("core.Property", False),
    "inventory.RoomType.amenities": ("inventory.Amenity", None),
    "inventory.Room.room_type": ("inventory.RoomType", False),
    "inventory.Room.extra_amenities": ("inventory.Amenity", None),
    "inventory.Room.removed_amenities": ("inventory.Amenity", None),
    "inventory.Room.connecting_rooms": ("inventory.Room", None),
    "inventory.Bed.room": ("inventory.Room", False),
    "inventory.CustomFieldDefinition.property": ("core.Property", True),
    "inventory.Photo.room_type": ("inventory.RoomType", True),
    "inventory.Photo.room": ("inventory.Room", True),
    "inventory.RoomBlock.room": ("inventory.Room", False),
    "inventory.RoomBlock.bed": ("inventory.Bed", True),
    "inventory.RoomBlock.created_by": ("accounts.User", True),
    "rates.RatePlan.parent": ("rates.RatePlan", True),
    "rates.RatePlan.room_types": ("inventory.RoomType", None),
    "rates.RatePlan.cancellation_policy": ("rates.CancellationPolicy", True),
    "rates.RoomTypeRateDefaults.room_type": ("inventory.RoomType", False),
    "rates.RoomTypeRateDefaults.rate_plan": ("rates.RatePlan", False),
    "rates.SeasonRate.season": ("rates.Season", False),
    "rates.DailyRate.room_type": ("inventory.RoomType", False),
    "rates.DailyRate.rate_plan": ("rates.RatePlan", False),
    "rates.DailyRate.updated_by": ("accounts.User", True),
    "rates.Extra.tax": ("rates.Tax", True),
    "rates.PromoCode.rate_plans": ("rates.RatePlan", None),
    "bookings.ReservationGroup.contact_guest": ("guests.Guest", True),
    "bookings.Reservation.property": ("core.Property", False),
    "bookings.Reservation.booker": ("guests.Guest", False),
    "bookings.Reservation.group": ("bookings.ReservationGroup", True),
    "bookings.Reservation.created_by": ("accounts.User", True),
    "bookings.Stay.reservation": ("bookings.Reservation", False),
    "bookings.Stay.room_type": ("inventory.RoomType", False),
    "bookings.Stay.rate_plan": ("rates.RatePlan", False),
    "bookings.Stay.room": ("inventory.Room", True),
    "bookings.Stay.bed": ("inventory.Bed", True),
    "bookings.Stay.occupants": ("guests.Guest", None),
    "bookings.InventoryDay.room_type": ("inventory.RoomType", False),
    "guests.Guest.organization": ("core.Organization", False),
    "guests.Guest.merged_into": ("guests.Guest", True),
    "guests.GuestDocument.guest": ("guests.Guest", False),
    "finance.Folio.property": ("core.Property", False),
    "finance.Folio.reservation": ("bookings.Reservation", True),
    "finance.Folio.stay": ("bookings.Stay", True),
    "finance.Folio.guest": ("guests.Guest", True),
    "finance.Charge.folio": ("finance.Folio", False),
    "finance.Charge.tax": ("rates.Tax", True),
    "finance.Charge.stay": ("bookings.Stay", True),
    "finance.Charge.extra": ("rates.Extra", True),
    "finance.Charge.posted_by": ("accounts.User", True),
    "finance.Payment.folio": ("finance.Folio", False),
    "finance.Payment.received_by": ("accounts.User", True),
    "finance.Refund.payment": ("finance.Payment", False),
    "finance.PaymentIntent.folio": ("finance.Folio", False),
    "finance.CashShift.user": ("accounts.User", False),
}

CHOICES = {
    "core.Organization.status": "trial active past_due suspended cancelled",
    "core.Property.property_type": "hotel hostel boutique aparthotel glamping",
    "core.Property.status": "active inactive",
    "core.AuditEvent.source": "user automation ai channel guest system api",
    "core.Alert.severity": "info warning critical",
    "core.IntegrationSetting.kind": (
        "payments channel_ical channel_channex einvoice sire tra email whatsapp llm saas_billing"
    ),
    "core.IntegrationSetting.mode": "real simulated",
    "core.IntegrationSetting.status": "unknown ok error",
    "core.AutomationRun.status": "running success partial failed skipped",
    "accounts.User.language": "es en",
    "inventory.Amenity.category": "room bathroom property accessibility view",
    "inventory.RoomType.kind": "private dorm",
    "inventory.Room.housekeeping_status": "clean dirty inspected out_of_service",
    "inventory.Bed.bed_type": "single bunk_top bunk_bottom double",
    "inventory.CustomFieldDefinition.applies_to": "room_type room guest reservation",
    "inventory.CustomFieldDefinition.field_type": "text number boolean select multiselect date",
    "inventory.RoomBlock.kind": "out_of_order out_of_service maintenance owner_hold",
    "rates.Tax.applies_to": "room extras all",
    "rates.CancellationPolicy.penalty_type": "first_night percent full",
    "rates.RatePlan.kind": "base derived",
    "rates.RatePlan.derivation_type": "percent amount",
    "rates.RatePlan.meal_plan": "room_only breakfast half_board full_board all_inclusive",
    "rates.DailyRate.source": "default season manual revenue bulk channel",
    "rates.Extra.charge_type": "per_stay per_night per_person per_person_night",
    "rates.PromoCode.discount_type": "percent amount",
    "bookings.Reservation.status": "tentative confirmed checked_in checked_out cancelled no_show",
    "bookings.Reservation.source": "walk_in phone email front_desk booking_engine marketplace ota api",
    "bookings.Reservation.guarantee": "none card deposit ota",
    "bookings.Stay.status": "tentative confirmed checked_in checked_out cancelled no_show",
    "guests.Guest.document_type": "CC CE PA TI PEP PPT DNI NIT OTHER",
    "guests.GuestDocument.kind": "id_front id_back passport signature other",
    "guests.GuestDocument.uploaded_via": "staff portal",
    "finance.Folio.folio_type": "guest master house",
    "finance.Folio.status": "open closed",
    "finance.Charge.kind": "room extra tax fee cancellation_fee adjustment other",
    "finance.Payment.method": (
        "cash card_terminal bank_transfer wompi_card wompi_pse wompi_nequi wompi_other ota_collect other"
    ),
    "finance.Payment.status": "pending approved declined voided error",
    "finance.Refund.status": "pending approved failed",
    "finance.PaymentIntent.mode": "real simulated",
    "finance.PaymentIntent.status": "created pending approved declined expired error",
}

MONEY_FIELDS = [
    "rates.RoomTypeRateDefaults.price", "rates.RoomTypeRateDefaults.extra_adult_price",
    "rates.RoomTypeRateDefaults.extra_child_price", "rates.RoomTypeRateDefaults.single_occupancy_price",
    "rates.SeasonRate.price", "rates.DailyRate.price", "rates.DailyRate.extra_adult_price",
    "rates.DailyRate.extra_child_price", "rates.Extra.price",
    "bookings.Reservation.total_amount", "bookings.Reservation.cancellation_fee",
    "bookings.Stay.total_amount", "finance.Charge.unit_price", "finance.Charge.amount",
    "finance.Charge.tax_amount", "finance.Payment.amount",
    "finance.Refund.amount", "finance.PaymentIntent.amount", "finance.CashShift.opening_float",
    "finance.CashShift.expected_cash", "finance.CashShift.counted_cash", "finance.CashShift.difference",
]  # fmt: skip

NULLABLE_VALUES = [
    "rates.RoomTypeRateDefaults.single_occupancy_price", "bookings.Reservation.eta",
    "bookings.Reservation.hold_expires_at", "bookings.Reservation.cancelled_at", "finance.Charge.night_date",
    "finance.Charge.voided_at", "guests.Guest.birth_date", "guests.Guest.data_processing_consent_at",
]  # fmt: skip


def _model(label: str):
    app_label, model_name = label.split(".")
    return apps.get_model(app_label, model_name)


def _field(path: str):
    app_label, model_name, field_name = path.split(".")
    return apps.get_model(app_label, model_name)._meta.get_field(field_name)


@pytest.mark.parametrize("label", sorted(SPEC_FIELDS))
def test_model_has_every_spec_field(label):
    model = _model(label)
    names = {f.name for f in model._meta.get_fields() if f.concrete or f.many_to_many}
    missing = set(SPEC_FIELDS[label].split()) - names
    assert not missing, f"{label} is missing {sorted(missing)}"


@pytest.mark.parametrize("label", sorted(SPEC_FIELDS))
def test_business_models_use_uuid_pk_and_timestamps(label):
    model = _model(label)
    assert isinstance(model._meta.pk, models.UUIDField)
    names = {f.name for f in model._meta.get_fields()}
    assert {"created_at", "updated_at"} <= names


def test_stay_has_no_period_column():
    # plan Step 4: the spec's `period` is replaced by a daterange expression inside the exclusion constraints
    names = {f.name for f in _model("bookings.Stay")._meta.get_fields()}
    assert "period" not in names


@pytest.mark.parametrize("path", sorted(RELATIONS))
def test_relations_point_to_the_spec_target(path):
    field = _field(path)
    target, nullable = RELATIONS[path]
    assert field.is_relation
    assert field.related_model._meta.label == target
    if nullable is not None:
        assert field.null is nullable, f"{path}: null={field.null}, expected {nullable}"


@pytest.mark.parametrize("path", sorted(CHOICES))
def test_choice_values(path):
    field = _field(path)
    assert [value for value, _label in field.choices] == CHOICES[path].split()


@pytest.mark.parametrize("path", MONEY_FIELDS)
def test_money_fields_are_decimal_14_2(path):
    field = _field(path)
    assert isinstance(field, models.DecimalField)
    assert (field.max_digits, field.decimal_places) == (14, 2)


@pytest.mark.parametrize("path", NULLABLE_VALUES)
def test_optional_values_are_nullable(path):
    assert _field(path).null is True


def test_room_overridable_fields_are_exactly_the_spec_list():
    from apps.inventory.models import ROOM_OVERRIDABLE_FIELDS

    assert ROOM_OVERRIDABLE_FIELDS == [
        "name", "description", "base_occupancy", "max_adults", "max_children", "max_occupancy", "beds",
        "size_m2", "view", "smoking_allowed", "accessible", "housekeeping_minutes",
    ]  # fmt: skip


def test_active_stay_statuses():
    from apps.bookings.models import ACTIVE_STAY_STATUSES

    assert ACTIVE_STAY_STATUSES == ["tentative", "confirmed", "checked_in"]
