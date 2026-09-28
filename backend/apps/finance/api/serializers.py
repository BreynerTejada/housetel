"""Finance API serializers. Money is always a string with two decimals (`"350000.00"`)."""

from decimal import Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.finance.cash import money_str
from apps.finance.models import CashShift, Charge, Folio, Payment, PaymentIntent, Refund
from apps.rates.models import Extra, Tax

MONEY = {"max_digits": 14, "decimal_places": 2}
# P4: `tax` = a lodging tax or levy posted apart (seguro hotelero, tasa turística); routable on its own.
MANUAL_CHARGE_KINDS = ["extra", "fee", "adjustment", "other", "tax"]
MANUAL_PAYMENT_METHODS = ["cash", "card_terminal", "bank_transfer", "other"]
LINK_CHANNELS = ["email", "whatsapp"]


def user_ref(user) -> dict | None:
    return {"id": str(user.pk), "full_name": user.full_name, "email": user.email} if user else None


# --- Nested references -------------------------------------------------------------------------------


class UserRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    email = serializers.EmailField()


class TaxRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    rate = serializers.DecimalField(max_digits=5, decimal_places=2)


class ReservationRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    status = serializers.CharField()
    checkin_date = serializers.DateField()
    checkout_date = serializers.DateField()
    adults = serializers.IntegerField()
    children = serializers.IntegerField()


class GuestRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    email = serializers.CharField()
    phone = serializers.CharField()
    is_foreign_non_resident = serializers.BooleanField()


class FolioTotalsSerializer(serializers.Serializer):
    charges_net = serializers.DecimalField(**MONEY)
    tax_total = serializers.DecimalField(**MONEY)
    charges_total = serializers.DecimalField(**MONEY)
    payments_total = serializers.DecimalField(**MONEY)
    refunds_total = serializers.DecimalField(**MONEY)
    balance = serializers.DecimalField(**MONEY)
    expected_balance = serializers.DecimalField(
        **MONEY, required=False, help_text="P4: balance + lodging not posted yet that goes to this folio"
    )
    reservation_balance = serializers.DecimalField(**MONEY, allow_null=True, required=False)


class FolioCompanyRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    legal_name = serializers.CharField()
    trade_name = serializers.CharField()
    nit_display = serializers.CharField()
    credit_enabled = serializers.BooleanField()
    payment_terms_days = serializers.IntegerField()


def company_ref(company) -> dict | None:
    if company is None:
        return None
    from apps.corporate.nit import format_nit

    return {
        "id": str(company.pk),
        "legal_name": company.legal_name,
        "trade_name": company.trade_name,
        "nit_display": format_nit(company.nit, company.dv),
        "credit_enabled": company.credit_enabled,
        "payment_terms_days": company.payment_terms_days,
    }


# --- Lines -------------------------------------------------------------------------------------------


class ChargeSerializer(serializers.ModelSerializer):
    total = serializers.DecimalField(**MONEY, read_only=True)
    tax = TaxRefSerializer(allow_null=True, read_only=True)
    tax_exempt = serializers.SerializerMethodField()
    stay_id = serializers.UUIDField(allow_null=True, read_only=True)
    extra_id = serializers.UUIDField(allow_null=True, read_only=True)
    posted_by = serializers.SerializerMethodField()
    voided = serializers.BooleanField(source="is_voided", read_only=True)
    voided_by = serializers.SerializerMethodField()

    class Meta:
        model = Charge
        fields = [
            "id",
            "folio",
            "business_date",
            "kind",
            "description",
            "quantity",
            "unit_price",
            "amount",
            "tax_amount",
            "total",
            "tax",
            "tax_exempt",
            "stay_id",
            "night_date",
            "extra_id",
            "source",
            "posted_by",
            "voided",
            "voided_at",
            "voided_by",
            "void_reason",
            "created_at",
        ]
        read_only_fields = fields

    def get_tax_exempt(self, obj) -> bool:
        return obj.tax_id is not None and obj.tax_amount == 0 and obj.amount != 0

    @extend_schema_field(UserRefSerializer(allow_null=True))
    def get_posted_by(self, obj):
        return user_ref(obj.posted_by)

    @extend_schema_field(UserRefSerializer(allow_null=True))
    def get_voided_by(self, obj):
        return user_ref(obj.voided_by)


class RefundSerializer(serializers.ModelSerializer):
    payment_id = serializers.UUIDField(read_only=True)
    error = serializers.SerializerMethodField()
    requested_by = serializers.SerializerMethodField()
    approved_by = serializers.SerializerMethodField()

    class Meta:
        model = Refund
        fields = [
            "id",
            "payment_id",
            "amount",
            "status",
            "provider_reference",
            "reason",
            "instructions",
            "error",
            "requested_by",
            "approved_by",
            "business_date",
            "created_at",
            "completed_at",
        ]
        read_only_fields = fields

    def get_error(self, obj) -> str:
        return (obj.provider_payload or {}).get("error", "")

    @extend_schema_field(UserRefSerializer(allow_null=True))
    def get_requested_by(self, obj):
        return user_ref(obj.requested_by)

    @extend_schema_field(UserRefSerializer(allow_null=True))
    def get_approved_by(self, obj):
        return user_ref(obj.approved_by)


class PaymentSerializer(serializers.ModelSerializer):
    received_by = serializers.SerializerMethodField()
    refunded_amount = serializers.SerializerMethodField()
    refundable_amount = serializers.SerializerMethodField()
    intent_id = serializers.UUIDField(allow_null=True, read_only=True)
    intent_reference = serializers.SerializerMethodField()
    cash_shift_id = serializers.UUIDField(allow_null=True, read_only=True)
    can_void = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id",
            "folio",
            "business_date",
            "amount",
            "method",
            "status",
            "provider",
            "provider_reference",
            "notes",
            "received_by",
            "refunded_amount",
            "refundable_amount",
            "intent_id",
            "intent_reference",
            "cash_shift_id",
            "can_void",
            "voided_at",
            "void_reason",
            "created_at",
        ]
        read_only_fields = fields

    def _refunds(self, obj) -> list:
        return list(obj.refunds.all())  # prefetched by the views

    @extend_schema_field(UserRefSerializer(allow_null=True))
    def get_received_by(self, obj):
        return user_ref(obj.received_by)

    @extend_schema_field(serializers.DecimalField(**MONEY))
    def get_refunded_amount(self, obj):
        return money_str(sum((r.amount for r in self._refunds(obj) if r.status == "approved"), Decimal("0")))

    @extend_schema_field(serializers.DecimalField(**MONEY))
    def get_refundable_amount(self, obj):
        if obj.status != Payment.Status.APPROVED:
            return money_str(0)
        taken = sum((r.amount for r in self._refunds(obj) if r.status != "failed"), Decimal("0"))
        return money_str(obj.amount - taken)

    def get_intent_reference(self, obj) -> str | None:
        return obj.intent.reference if obj.intent_id else None

    def get_can_void(self, obj) -> bool:
        return (
            obj.provider == "manual"
            and obj.intent_id is None
            and obj.status == Payment.Status.APPROVED
            and not any(r.status != "failed" for r in self._refunds(obj))
        )


class PaymentIntentSerializer(serializers.ModelSerializer):
    folio_id = serializers.UUIDField(read_only=True)
    reservation_id = serializers.SerializerMethodField()
    reservation_code = serializers.SerializerMethodField()
    payment_id = serializers.SerializerMethodField()

    class Meta:
        model = PaymentIntent
        fields = [
            "id",
            "reference",
            "folio_id",
            "reservation_id",
            "reservation_code",
            "amount",
            "currency",
            "status",
            "mode",
            "provider",
            "checkout_url",
            "return_url",
            "expires_at",
            "created_at",
            "method",
            "status_message",
            "last_checked_at",
            "payment_id",
        ]
        read_only_fields = fields

    def get_reservation_id(self, obj) -> str | None:
        return str(obj.folio.reservation_id) if obj.folio.reservation_id else None

    def get_reservation_code(self, obj) -> str | None:
        return obj.folio.reservation.code if obj.folio.reservation_id else None

    def get_payment_id(self, obj) -> str | None:
        payment = getattr(obj, "payment", None)
        return str(payment.pk) if payment else None


# --- Folios ------------------------------------------------------------------------------------------


class FolioSummarySerializer(serializers.ModelSerializer):
    # Plain strings (not enums) so the schema has no colliding "status" enum names across apps.
    status = serializers.CharField(read_only=True, help_text="open | closed")
    folio_type = serializers.CharField(read_only=True, help_text="guest | master | house | company")
    reservation = serializers.SerializerMethodField()
    guest = serializers.SerializerMethodField()
    company = serializers.SerializerMethodField()
    totals = serializers.SerializerMethodField()

    class Meta:
        model = Folio
        fields = [
            "id",
            "folio_type",
            "status",
            "currency",
            "label",
            "closed_at",
            "created_at",
            "reservation",
            "guest",
            "company",
            "totals",
        ]
        read_only_fields = fields

    @extend_schema_field(FolioCompanyRefSerializer(allow_null=True))
    def get_company(self, obj):
        return company_ref(obj.company if obj.company_id else None)

    @extend_schema_field(ReservationRefSerializer(allow_null=True))
    def get_reservation(self, obj):
        r = obj.reservation if obj.reservation_id else None
        if r is None:
            return None
        return {
            "id": str(r.pk),
            "code": r.code,
            "status": r.status,
            "checkin_date": r.checkin_date.isoformat(),
            "checkout_date": r.checkout_date.isoformat(),
            "adults": r.adults,
            "children": r.children,
        }

    @extend_schema_field(GuestRefSerializer(allow_null=True))
    def get_guest(self, obj):
        guest = obj.guest if obj.guest_id else (obj.reservation.booker if obj.reservation_id else None)
        if guest is None:
            return None
        return {
            "id": str(guest.pk),
            "full_name": guest.full_name,
            "email": guest.email,
            "phone": guest.phone,
            "is_foreign_non_resident": guest.is_foreign_non_resident,
        }

    @extend_schema_field(FolioTotalsSerializer)
    def get_totals(self, obj):
        totals = self.context["totals"](obj)
        return {key: (money_str(value) if value is not None else None) for key, value in totals.items()}


class FolioDetailSerializer(FolioSummarySerializer):
    charges = ChargeSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    refunds = serializers.SerializerMethodField()
    intents = serializers.SerializerMethodField()

    class Meta(FolioSummarySerializer.Meta):
        fields = [*FolioSummarySerializer.Meta.fields, "charges", "payments", "refunds", "intents"]
        read_only_fields = fields

    @extend_schema_field(RefundSerializer(many=True))
    def get_refunds(self, obj):
        refunds = [refund for payment in obj.payments.all() for refund in payment.refunds.all()]
        return RefundSerializer(sorted(refunds, key=lambda r: r.created_at), many=True).data

    @extend_schema_field(PaymentIntentSerializer(many=True))
    def get_intents(self, obj):
        return PaymentIntentSerializer(obj.payment_intents.all(), many=True).data


# --- Charge options ----------------------------------------------------------------------------------


class TaxOptionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    applies_to = serializers.CharField()
    included_in_price = serializers.BooleanField()
    exempt = serializers.BooleanField(help_text="Would be exempt for this folio's guest")


class ExtraOptionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.DictField(child=serializers.CharField())
    price = serializers.DecimalField(**MONEY)
    unit_price = serializers.DecimalField(**MONEY, help_text="Net unit price posted to the folio")
    charge_type = serializers.CharField()
    default_quantity = serializers.IntegerField()
    tax = TaxOptionSerializer(allow_null=True)


class ChargeOptionsSerializer(serializers.Serializer):
    extras = ExtraOptionSerializer(many=True)
    taxes = TaxOptionSerializer(many=True)
    manual_kinds = serializers.ListField(child=serializers.CharField())
    guest_is_foreign_non_resident = serializers.BooleanField()


# --- Requests ----------------------------------------------------------------------------------------


class EnsureFolioSerializer(serializers.Serializer):
    reservation_id = serializers.UUIDField()


class ChargeCreateSerializer(serializers.Serializer):
    """Either an extra (`extra_id`, optional `quantity`) or a manual line (`kind`, `description`, net
    unit `amount`, `quantity`, optional `tax_id`)."""

    extra_id = serializers.UUIDField(required=False)
    kind = serializers.ChoiceField(choices=MANUAL_CHARGE_KINDS, required=False)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    amount = serializers.DecimalField(**MONEY, required=False)
    quantity = serializers.IntegerField(min_value=1, max_value=999, required=False)
    tax_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        prop = self.context["property"]
        if attrs.get("extra_id"):
            extra = (
                Extra.objects.select_related("tax")
                .filter(pk=attrs["extra_id"], property=prop, is_active=True)
                .first()
            )
            if extra is None:
                raise serializers.ValidationError({"extra_id": ["Extra no encontrado en este hotel"]})
            return {"extra": extra, "quantity": attrs.get("quantity")}
        errors = {}
        if (
            not attrs.get("kind")
            and "kind" not in attrs
            and not any(k in attrs for k in ("description", "amount"))
        ):
            raise serializers.ValidationError({"extra_id": ["Elige un extra o escribe los datos del cargo"]})
        if not attrs.get("kind"):
            errors["kind"] = ["Este campo es requerido."]
        if not (attrs.get("description") or "").strip():
            errors["description"] = ["Este campo es requerido."]
        if attrs.get("amount") is None:
            errors["amount"] = ["Este campo es requerido."]
        tax = None
        if attrs.get("tax_id"):
            tax = Tax.objects.filter(pk=attrs["tax_id"], property=prop, is_active=True).first()
            if tax is None:
                errors["tax_id"] = ["Impuesto no encontrado en este hotel"]
        if errors:
            raise serializers.ValidationError(errors)
        return {
            "kind": attrs["kind"],
            "description": attrs["description"].strip(),
            "amount": attrs["amount"],
            "quantity": attrs.get("quantity") or 1,
            "tax": tax,
        }


class ReasonConfirmSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=1000)
    confirm = serializers.BooleanField(required=False, default=False)


class TransferSerializer(serializers.Serializer):
    """P4: move a charge or a payment to another folio of the same reservation."""

    to_folio_id = serializers.UUIDField()
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)


class SplitChargeSerializer(serializers.Serializer):
    """P4: `amount` (total with tax) goes to a new charge on `to_folio_id` (default: the same folio)."""

    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    to_folio_id = serializers.UUIDField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)


class SplitResultSerializer(serializers.Serializer):
    rest = ChargeSerializer()
    part = ChargeSerializer()


class ManualPaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    method = serializers.ChoiceField(choices=MANUAL_PAYMENT_METHODS)
    reference = serializers.CharField(required=False, allow_blank=True, default="", max_length=120)
    notes = serializers.CharField(required=False, allow_blank=True, default="", max_length=1000)


class RefundRequestSerializer(ReasonConfirmSerializer):
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))


class CompleteRefundSerializer(serializers.Serializer):
    confirm = serializers.BooleanField(required=False, default=False)
    outcome = serializers.ChoiceField(choices=["approved", "failed"], required=False, default="approved")
    reference = serializers.CharField(required=False, allow_blank=True, default="", max_length=120)


class PaymentLinkRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("1"))
    send_via = serializers.ListField(
        child=serializers.ChoiceField(choices=LINK_CHANNELS), required=False, default=list, max_length=2
    )


class OutboundMessageSerializer(serializers.Serializer):
    channel = serializers.CharField()
    to = serializers.CharField()
    status = serializers.CharField()
    error = serializers.CharField()


class PaymentLinkSerializer(serializers.Serializer):
    intent = PaymentIntentSerializer()
    checkout_url = serializers.CharField()
    messages = OutboundMessageSerializer(many=True)
    send_error = serializers.CharField(required=False)


# --- Cash shifts -------------------------------------------------------------------------------------


class MethodTotalSerializer(serializers.Serializer):
    method = serializers.CharField()
    count = serializers.IntegerField()
    total = serializers.DecimalField(**MONEY)


class ShiftTotalsSerializer(serializers.Serializer):
    opening_float = serializers.DecimalField(**MONEY)
    cash_payments = serializers.DecimalField(**MONEY)
    cash_refunds = serializers.DecimalField(**MONEY)
    expected_cash = serializers.DecimalField(**MONEY)
    payments_count = serializers.IntegerField()
    refunds_count = serializers.IntegerField()
    by_method = MethodTotalSerializer(many=True)


class ShiftMovementSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=["payment", "refund"])
    created_at = serializers.DateTimeField()
    method = serializers.CharField()
    amount = serializers.DecimalField(**MONEY)
    status = serializers.CharField()
    reference = serializers.CharField()
    folio_id = serializers.UUIDField()
    reservation_id = serializers.UUIDField(allow_null=True)
    reservation_code = serializers.CharField(allow_null=True)
    guest_name = serializers.CharField()


class CashShiftSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    closed_by = serializers.SerializerMethodField()
    is_open = serializers.SerializerMethodField()

    class Meta:
        model = CashShift
        fields = [
            "id",
            "user",
            "opened_at",
            "closed_at",
            "is_open",
            "opening_float",
            "expected_cash",
            "counted_cash",
            "difference",
            "denominations",
            "notes",
            "closed_by",
        ]
        read_only_fields = fields

    @extend_schema_field(UserRefSerializer)
    def get_user(self, obj):
        return user_ref(obj.user)

    @extend_schema_field(UserRefSerializer(allow_null=True))
    def get_closed_by(self, obj):
        return user_ref(obj.closed_by)

    def get_is_open(self, obj) -> bool:
        return obj.closed_at is None


class CashShiftDetailSerializer(CashShiftSerializer):
    totals = serializers.SerializerMethodField()
    movements = serializers.SerializerMethodField()

    class Meta(CashShiftSerializer.Meta):
        fields = [*CashShiftSerializer.Meta.fields, "totals", "movements"]
        read_only_fields = fields

    @extend_schema_field(ShiftTotalsSerializer)
    def get_totals(self, obj):
        from apps.finance.reporting import shift_totals_payload

        return shift_totals_payload(obj)

    @extend_schema_field(ShiftMovementSerializer(many=True))
    def get_movements(self, obj):
        from apps.finance.reporting import shift_movements

        return ShiftMovementSerializer(shift_movements(obj), many=True).data


class CurrentShiftSerializer(serializers.Serializer):
    shift = CashShiftDetailSerializer(allow_null=True)


class OpenShiftSerializer(serializers.Serializer):
    opening_float = serializers.DecimalField(
        **MONEY, min_value=Decimal("0"), required=False, default=Decimal("0")
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="", max_length=1000)


class CloseShiftSerializer(serializers.Serializer):
    counted_cash = serializers.DecimalField(**MONEY, required=False, allow_null=True, default=None)
    denominations = serializers.DictField(
        child=serializers.IntegerField(min_value=0), required=False, default=dict
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="", max_length=1000)


# --- Summary -----------------------------------------------------------------------------------------


class CountTotalSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    total = serializers.DecimalField(**MONEY)


class ChargesDaySerializer(serializers.Serializer):
    net = serializers.DecimalField(**MONEY)
    tax = serializers.DecimalField(**MONEY)
    total = serializers.DecimalField(**MONEY)


class SummarySerializer(serializers.Serializer):
    date = serializers.DateField()
    currency = serializers.CharField()
    payments = CountTotalSerializer()
    refunds = CountTotalSerializer()
    net_total = serializers.DecimalField(**MONEY)
    by_method = MethodTotalSerializer(many=True)
    charges = ChargesDaySerializer()


# --- Public ------------------------------------------------------------------------------------------


class PublicPropertySerializer(serializers.Serializer):
    name = serializers.CharField()
    slug = serializers.CharField()
    city = serializers.CharField()
    primary_color = serializers.CharField()
    logo = serializers.CharField()


class SimIntentSerializer(serializers.Serializer):
    reference = serializers.CharField()
    amount = serializers.DecimalField(**MONEY)
    currency = serializers.CharField()
    status = serializers.CharField()
    mode = serializers.CharField()
    method = serializers.CharField()
    expires_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    return_url = serializers.CharField()
    property = PublicPropertySerializer()
    reservation_code = serializers.CharField(allow_null=True)
    payer_first_name = serializers.CharField(allow_null=True)


class SimDecisionSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=["approved", "declined", "expired"])
    method = serializers.ChoiceField(choices=["card", "pse", "nequi"])


class IntentStatusSerializer(serializers.Serializer):
    reference = serializers.CharField()
    status = serializers.CharField()
    paid = serializers.BooleanField()
    amount = serializers.DecimalField(**MONEY)
    currency = serializers.CharField()
    method = serializers.CharField()
    reservation_code = serializers.CharField(allow_null=True)
    property_slug = serializers.CharField()


class WebhookAckSerializer(serializers.Serializer):
    received = serializers.BooleanField()
    ignored = serializers.BooleanField()
    status = serializers.CharField(required=False)
