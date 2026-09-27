"""Staff finance API (`/api/v1/finance/`, header `X-Property-Id`). Permissions (plan §D):
finance.view (read), finance.collect (charges, payments, links), finance.void, finance.refund and
finance.cashier (cash shifts).
"""

import logging
from datetime import date

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.bookings.models import Reservation
from apps.core.tenancy import PropertyScopedAPIView, PropertyScopedMixin
from apps.core.tokens import portal_url
from apps.finance import cash, reporting, services
from apps.finance.api import serializers as s
from apps.finance.cash import money_str
from apps.finance.models import CashShift, Charge, Folio, Payment, PaymentIntent, Refund
from apps.rates.models import Extra, Tax

logger = logging.getLogger("housetel.finance")

UUID_REGEX = "[0-9a-fA-F-]{36}"


def _uuid_param(request, name):
    value = request.query_params.get(name)
    if not value:
        return None
    try:
        from uuid import UUID

        return UUID(value)
    except ValueError:
        raise ValidationError({name: ["UUID inválido"]}) from None


def _date_param(request, name, default=None):
    value = request.query_params.get(name)
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError({name: ["Fecha inválida (AAAA-MM-DD)"]}) from None


def _payments_prefetch():
    return Prefetch(
        "payments",
        queryset=Payment.objects.select_related("received_by", "intent").prefetch_related(
            Prefetch("refunds", queryset=Refund.objects.select_related("requested_by", "approved_by"))
        ),
    )


class FolioViewSet(
    PropertyScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Folios of the active property. `GET folios/?reservation=<id>&status=open|closed`."""

    queryset = Folio.objects.select_related("reservation__booker", "guest", "property")
    serializer_class = s.FolioSummarySerializer
    lookup_value_regex = UUID_REGEX
    required_permissions = {
        "list": "finance.view",
        "retrieve": "finance.view",
        "charge_options": "finance.view",
        "create": "finance.collect",
        "charges": "finance.collect",
        "payments": "finance.collect",
        "payment_link": "finance.collect",
    }

    def get_queryset(self):
        queryset = reporting.annotate_folio_totals(super().get_queryset())
        if reservation_id := _uuid_param(self.request, "reservation"):
            queryset = queryset.filter(reservation_id=reservation_id)
        if folio_status := self.request.query_params.get("status"):
            queryset = queryset.filter(status=folio_status)
        return queryset.order_by("created_at")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "totals": reporting.folio_totals}

    def _detail(self, folio_id):
        folio = (
            self.get_queryset()
            .prefetch_related(
                Prefetch("charges", queryset=Charge.objects.select_related("tax", "posted_by", "voided_by")),
                _payments_prefetch(),
                Prefetch(
                    "payment_intents",
                    queryset=PaymentIntent.objects.select_related("folio__reservation", "payment"),
                ),
            )
            .get(pk=folio_id)
        )
        context = {
            **self.get_serializer_context(),
            "totals": lambda obj: reporting.folio_totals(obj, with_reservation=True),
        }
        return s.FolioDetailSerializer(folio, context=context).data

    @extend_schema(
        parameters=[
            OpenApiParameter("reservation", OpenApiTypes.UUID, description="Folios de una reserva"),
            OpenApiParameter("status", OpenApiTypes.STR, enum=["open", "closed"]),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(responses=s.FolioDetailSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(self._detail(self.get_object().pk))

    @extend_schema(
        request=s.EnsureFolioSerializer,
        responses={200: s.FolioDetailSerializer, 201: s.FolioDetailSerializer},
    )
    def create(self, request, *args, **kwargs):
        """Get or create the guest folio of a reservation of this property."""
        data = s.EnsureFolioSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        reservation = get_object_or_404(
            Reservation, pk=data.validated_data["reservation_id"], property=request.property
        )
        existed = Folio.objects.filter(
            reservation=reservation, stay=None, folio_type=Folio.FolioType.GUEST
        ).exists()
        folio = services.get_or_create_folio(reservation)
        return Response(
            self._detail(folio.pk), status=status.HTTP_200_OK if existed else status.HTTP_201_CREATED
        )

    @extend_schema(responses=s.ChargeOptionsSerializer)
    @action(detail=True, methods=["get"], url_path="charge-options")
    def charge_options(self, request, pk=None):
        """Extras (with the default quantity for this reservation) and taxes for the "add charge" dialog."""
        folio = self.get_object()
        guest = services.guest_of(folio)

        def tax_payload(tax):
            if tax is None:
                return None
            return {
                "id": str(tax.pk),
                "code": tax.code,
                "name": tax.name,
                "rate": money_str(tax.rate),
                "applies_to": tax.applies_to,
                "included_in_price": tax.included_in_price,
                "exempt": services.is_tax_exempt(folio, tax),
            }

        extras = []
        for extra in Extra.objects.filter(property=request.property, is_active=True).select_related("tax"):
            tax = extra.tax if extra.tax_id and extra.tax.is_active else None
            extras.append(
                {
                    "id": str(extra.pk),
                    "code": extra.code,
                    "name": extra.name or {},
                    "price": money_str(extra.price),
                    "unit_price": money_str(services.extra_unit_net(extra, tax)),
                    "charge_type": extra.charge_type,
                    "default_quantity": services.extra_default_quantity(extra, folio),
                    "tax": tax_payload(tax),
                }
            )
        taxes = [tax_payload(tax) for tax in Tax.objects.filter(property=request.property, is_active=True)]
        return Response(
            {
                "extras": extras,
                "taxes": taxes,
                "manual_kinds": s.MANUAL_CHARGE_KINDS,
                "guest_is_foreign_non_resident": bool(guest and guest.is_foreign_non_resident),
            }
        )

    @extend_schema(request=s.ChargeCreateSerializer, responses={201: s.ChargeSerializer})
    @action(detail=True, methods=["post"])
    def charges(self, request, pk=None):
        """Post an extra (`{extra_id, quantity?}`) or a manual line (`{kind, description, amount, quantity?,
        tax_id?}`; `amount` is the NET unit price; only adjustments may be negative)."""
        folio = self.get_object()
        data = s.ChargeCreateSerializer(data=request.data, context={"property": request.property})
        data.is_valid(raise_exception=True)
        values = data.validated_data
        if "extra" in values:
            charge = services.post_extra_charge(
                folio, values["extra"], quantity=values["quantity"], actor=request.user
            )
        else:
            charge = services.post_charge(
                folio,
                kind=values["kind"],
                amount=values["amount"],
                description=values["description"],
                quantity=values["quantity"],
                tax=values["tax"],
                tax_exempt=services.is_tax_exempt(folio, values["tax"]),
                actor=request.user,
            )
        return Response(s.ChargeSerializer(charge).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=s.ManualPaymentSerializer, responses={201: s.PaymentSerializer})
    @action(detail=True, methods=["post"])
    def payments(self, request, pk=None):
        """Record a manual payment (cash needs the user's open cash shift → 409 `cash_shift_required`)."""
        folio = self.get_object()
        data = s.ManualPaymentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        payment = services.record_payment(
            folio,
            amount=values["amount"],
            method=values["method"],
            reference=values["reference"],
            actor=request.user,
        )
        if values["notes"]:
            payment.notes = values["notes"]
            payment.save(update_fields=["notes", "updated_at"])
        return Response(s.PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=s.PaymentLinkRequestSerializer, responses={201: s.PaymentLinkSerializer})
    @action(detail=True, methods=["post"], url_path="payment-link")
    def payment_link(self, request, pk=None):
        """Create an online payment link (simulated or Wompi) that returns to the guest portal; optionally
        send it with the `payment_link` template by email / WhatsApp."""
        folio = self.get_object()
        data = s.PaymentLinkRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        reservation = folio.reservation if folio.reservation_id else None
        return_url = f"{portal_url(reservation)}?paid=1" if reservation else ""
        intent = services.create_payment_intent(folio, amount=values["amount"], return_url=return_url)
        intent.created_by = request.user
        intent.save(update_fields=["created_by", "updated_at"])
        payload = {
            "intent": s.PaymentIntentSerializer(intent).data,
            "checkout_url": intent.checkout_url,
            "messages": [],
        }
        if values["send_via"]:
            payload.update(self._send_link(folio, intent, tuple(values["send_via"])))
        return Response(payload, status=status.HTTP_201_CREATED)

    def _send_link(self, folio, intent, channels) -> dict:
        from apps.messaging import services as messaging

        context = {
            "payment_url": intent.checkout_url,
            "amount": services._money(intent.amount, intent.currency),
            "reference": intent.reference,
            "expires_at": intent.expires_at.isoformat() if intent.expires_at else "",
        }
        try:
            sent = messaging.send_message(
                property=folio.property,
                template_code="payment_link",
                guest=services.guest_of(folio),
                reservation=folio.reservation if folio.reservation_id else None,
                channels=channels,
                context=context,
            )
        except Exception as exc:  # delivery problems never undo the link: it is shown to copy by hand
            logger.exception("Could not send payment link %s", intent.reference)
            return {"messages": [], "send_error": str(exc)[:300]}
        return {
            "messages": [
                {"channel": m.channel, "to": m.to, "status": m.status, "error": m.error or ""} for m in sent
            ]
        }


class ChargeViewSet(PropertyScopedMixin, viewsets.GenericViewSet):
    queryset = Charge.objects.select_related("folio__property", "tax", "posted_by", "voided_by")
    serializer_class = s.ChargeSerializer
    property_field = "folio__property"
    lookup_value_regex = UUID_REGEX
    required_permissions = {"void": "finance.void"}

    @extend_schema(request=s.ReasonConfirmSerializer, responses=s.ChargeSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        """`{reason, confirm: true}` — risky action: the UI asks to type the amount first."""
        data = s.ReasonConfirmSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        charge = services.void_charge(
            self.get_object(),
            reason=data.validated_data["reason"],
            actor=request.user,
            confirm=data.validated_data["confirm"],
        )
        return Response(s.ChargeSerializer(charge).data)


class PaymentViewSet(PropertyScopedMixin, viewsets.GenericViewSet):
    queryset = Payment.objects.select_related("folio__property", "received_by", "intent").prefetch_related(
        "refunds"
    )
    serializer_class = s.PaymentSerializer
    property_field = "folio__property"
    lookup_value_regex = UUID_REGEX
    required_permissions = {"void": "finance.void", "refund": "finance.refund"}

    @extend_schema(request=s.ReasonConfirmSerializer, responses=s.PaymentSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        """Void a MANUAL payment recorded by mistake (`{reason, confirm: true}`)."""
        data = s.ReasonConfirmSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        payment = services.void_payment(
            self.get_object(),
            reason=data.validated_data["reason"],
            actor=request.user,
            confirm=data.validated_data["confirm"],
        )
        return Response(s.PaymentSerializer(self.get_queryset().get(pk=payment.pk)).data)

    @extend_schema(request=s.RefundRequestSerializer, responses={201: s.RefundSerializer})
    @action(detail=True, methods=["post"])
    def refund(self, request, pk=None):
        """`{amount, reason, confirm: true}` → Refund `approved` | `pending` (manual step) | `failed`."""
        data = s.RefundRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        refund = services.refund_payment(
            self.get_object(),
            amount=values["amount"],
            reason=values["reason"],
            actor=request.user,
            confirm=values["confirm"],
        )
        return Response(s.RefundSerializer(refund).data, status=status.HTTP_201_CREATED)


class RefundViewSet(PropertyScopedMixin, viewsets.GenericViewSet):
    queryset = Refund.objects.select_related("payment__folio__property", "requested_by", "approved_by")
    serializer_class = s.RefundSerializer
    property_field = "payment__folio__property"
    lookup_value_regex = UUID_REGEX
    required_permissions = {"complete": "finance.refund"}

    @extend_schema(request=s.CompleteRefundSerializer, responses=s.RefundSerializer)
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        """Mark a `pending` refund as done (`{confirm: true, outcome: approved|failed, reference?}`)."""
        data = s.CompleteRefundSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        refund = services.complete_refund(
            self.get_object(),
            actor=request.user,
            confirm=values["confirm"],
            outcome=values["outcome"],
            reference=values["reference"],
        )
        return Response(s.RefundSerializer(refund).data)


class PaymentIntentViewSet(
    PropertyScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Online payment links. `GET intents/?status=&folio=&reservation=`."""

    queryset = PaymentIntent.objects.select_related("folio__reservation", "payment")
    serializer_class = s.PaymentIntentSerializer
    lookup_value_regex = UUID_REGEX
    required_permissions = {"list": "finance.view", "retrieve": "finance.view", "sync": "finance.collect"}

    def get_queryset(self):
        queryset = super().get_queryset()
        if intent_status := self.request.query_params.get("status"):
            queryset = queryset.filter(status=intent_status)
        if folio_id := _uuid_param(self.request, "folio"):
            queryset = queryset.filter(folio_id=folio_id)
        if reservation_id := _uuid_param(self.request, "reservation"):
            queryset = queryset.filter(folio__reservation_id=reservation_id)
        return queryset.order_by("-created_at")

    @extend_schema(
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR),
            OpenApiParameter("folio", OpenApiTypes.UUID),
            OpenApiParameter("reservation", OpenApiTypes.UUID),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=None, responses=s.PaymentIntentSerializer)
    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        """Verify the link with the payment provider now."""
        intent = services.sync_payment_intent(self.get_object())
        return Response(s.PaymentIntentSerializer(self.get_queryset().get(pk=intent.pk)).data)


class CashShiftViewSet(
    PropertyScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Cash shifts (caja). `GET cash-shifts/?user=&status=open|closed&start=&end=` (opening date)."""

    queryset = CashShift.objects.select_related("user", "closed_by", "property")
    serializer_class = s.CashShiftSerializer
    lookup_value_regex = UUID_REGEX
    required_permissions = {
        "list": "finance.cashier",
        "retrieve": "finance.cashier",
        "export": "finance.cashier",
        "export_history": "finance.cashier",
        "open": "finance.cashier",
        "close": "finance.cashier",
        "current": "finance.view",
    }

    def get_queryset(self):
        queryset = reporting.open_or_closed(super().get_queryset(), self.request.query_params.get("status"))
        if user_id := _uuid_param(self.request, "user"):
            queryset = queryset.filter(user_id=user_id)
        if start := _date_param(self.request, "start"):
            queryset = queryset.filter(opened_at__date__gte=start)
        if end := _date_param(self.request, "end"):
            queryset = queryset.filter(opened_at__date__lte=end)
        return queryset.order_by("-opened_at")

    @extend_schema(
        parameters=[
            OpenApiParameter("user", OpenApiTypes.UUID),
            OpenApiParameter("status", OpenApiTypes.STR, enum=["open", "closed"]),
            OpenApiParameter("start", OpenApiTypes.DATE),
            OpenApiParameter("end", OpenApiTypes.DATE),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(responses=s.CashShiftDetailSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(s.CashShiftDetailSerializer(self.get_object()).data)

    @extend_schema(responses=s.CurrentShiftSerializer)
    @action(detail=False, methods=["get"])
    def current(self, request):
        """The signed-in user's open shift at this property (with live totals and movements), or null."""
        shift = cash.current_cash_shift(request.property, request.user)
        return Response({"shift": s.CashShiftDetailSerializer(shift).data if shift else None})

    @extend_schema(request=s.OpenShiftSerializer, responses={201: s.CashShiftDetailSerializer})
    @action(detail=False, methods=["post"])
    def open(self, request):
        data = s.OpenShiftSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        shift = cash.open_cash_shift(
            request.property,
            request.user,
            opening_float=data.validated_data["opening_float"],
            notes=data.validated_data["notes"],
        )
        return Response(s.CashShiftDetailSerializer(shift).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=s.CloseShiftSerializer, responses=s.CashShiftDetailSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        """`{counted_cash}` or `{denominations: {"50000": 3, …}}` (+ `notes`) → expected and difference."""
        data = s.CloseShiftSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        shift = cash.close_cash_shift(
            self.get_object(),
            actor=request.user,
            counted_cash=values["counted_cash"],
            denominations=values["denominations"] or None,
            notes=values["notes"],
        )
        return Response(s.CashShiftDetailSerializer(shift).data)

    @extend_schema(operation_id="finance_cash_shift_export", responses={(200, "text/csv"): OpenApiTypes.STR})
    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        """CSV of the shift's movements and totals (`;`, UTF-8 with BOM)."""
        return reporting.shift_csv(self.get_object())

    @extend_schema(
        parameters=[OpenApiParameter("start", OpenApiTypes.DATE), OpenApiParameter("end", OpenApiTypes.DATE)],
        responses={(200, "text/csv"): OpenApiTypes.STR},
        operation_id="finance_cash_shifts_export",
    )
    @action(detail=False, methods=["get"], url_path="export")
    def export_history(self, request):
        """CSV of the shifts opened between `start` and `end` (inclusive, property dates)."""
        return reporting.shifts_csv(
            self.get_queryset(), request.query_params.get("start"), request.query_params.get("end")
        )


class SummaryView(PropertyScopedAPIView):
    """`GET summary/?date=` (default: business date) → payments by method, refunds and charges of the day."""

    required_permissions = {"get": "finance.view"}

    @extend_schema(parameters=[OpenApiParameter("date", OpenApiTypes.DATE)], responses=s.SummarySerializer)
    def get(self, request):
        day = _date_param(request, "date", request.property.business_date)
        return Response(reporting.payments_summary(request.property, day))
