"""Staff API of `revenue` (`/api/v1/revenue/`, header `X-Property-Id`): `revenue.view` reads, `revenue.manage`
configures, decides, runs and simulates. Rules and bounds are small catalogs listed without pagination;
recommendations and runs are paginated."""

from datetime import timedelta
from decimal import Decimal

import django_filters
from django.core.cache import cache
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Min, Q, Sum, Value
from django.db.models.functions import Coalesce
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core import audit, automation
from apps.core.errors import ConflictError, DomainError
from apps.core.tenancy import PropertyScopedAPIView, PropertyScopedMixin, PropertyScopedViewSet
from apps.rates.services.calendar import holiday_list
from apps.revenue.api import serializers as s
from apps.revenue.models import PriceBounds, PricingRule, RateRecommendation, RevenueRun
from apps.revenue.services import decisions
from apps.revenue.services.config import get_settings
from apps.revenue.services.engine import RuleSpec, active_rules, priced_pairs, propose
from apps.revenue.services.summary import ai_explanation, impact_figures

VIEW, MANAGE = "revenue.view", "revenue.manage"
CATALOG_PERMISSIONS = {"list": VIEW, "retrieve": VIEW, "*": MANAGE}
Status = RateRecommendation.Status
CENTS = Decimal("0.01")
EXPLANATION_CACHE_SECONDS = 60 * 60 * 24


class RunFailed(DomainError):
    code = "run_failed"
    status_code = 500


def user_language(request, asked=None) -> str:
    if asked:
        return asked
    return "en" if getattr(request.user, "language", "es") == "en" else "es"


def money(value) -> str:
    return format(Decimal(value or 0).quantize(CENTS), "f")


class RevenueSettingsView(PropertyScopedAPIView):
    """`GET/PATCH settings/`: revenue settings of the property (created with defaults on first read)."""

    required_permissions = {"get": VIEW, "patch": MANAGE}

    @extend_schema(responses=s.RevenueSettingsSerializer)
    def get(self, request):
        return Response(s.RevenueSettingsSerializer(get_settings(request.property)).data)

    @extend_schema(request=s.RevenueSettingsSerializer, responses=s.RevenueSettingsSerializer)
    def patch(self, request):
        settings = get_settings(request.property)
        before = s.RevenueSettingsSerializer(settings).data
        serializer = s.RevenueSettingsSerializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        after = serializer.data
        changes = audit.diff(
            {k: v for k, v in before.items() if k != "updated_at"},
            {k: v for k, v in after.items() if k != "updated_at"},
        )
        if changes:
            audit.record(
                action="revenue.settings_updated",
                target=settings,
                property=request.property,
                actor=request.user,
                summary="Ajustes de revenue actualizados",
                changes=changes,
            )
        return Response(after)


class PricingRuleViewSet(PropertyScopedViewSet):
    queryset = PricingRule.objects.prefetch_related("room_types")
    serializer_class = s.PricingRuleSerializer
    required_permissions = CATALOG_PERMISSIONS
    pagination_class = None
    filterset_fields = ["kind", "is_active"]

    def perform_create(self, serializer):
        rule = serializer.save(property=self.request.property)
        self._audit("revenue.rule_created", rule, f"Regla de precio creada: {rule.name}", serializer.data)

    def perform_update(self, serializer):
        before = s.PricingRuleSerializer(serializer.instance).data
        rule = serializer.save()
        after = s.PricingRuleSerializer(rule).data
        changes = audit.diff(
            {k: v for k, v in before.items() if k != "updated_at"},
            {k: v for k, v in after.items() if k != "updated_at"},
        )
        self._audit("revenue.rule_updated", rule, f"Regla de precio actualizada: {rule.name}", changes)

    def perform_destroy(self, instance):
        self._audit("revenue.rule_deleted", instance, f"Regla de precio eliminada: {instance.name}", {})
        instance.delete()

    def _audit(self, action, rule, summary, changes):
        audit.record(
            action=action,
            target=rule,
            property=self.request.property,
            actor=self.request.user,
            summary=summary,
            changes=dict(changes),
        )


class PriceBoundsViewSet(PropertyScopedViewSet):
    """Bounds per category and base plan; `POST` creates or updates the pair (201 / 200)."""

    queryset = PriceBounds.objects.select_related("room_type", "rate_plan")
    serializer_class = s.PriceBoundsSerializer
    required_permissions = CATALOG_PERMISSIONS
    pagination_class = None
    property_field = "room_type__property"
    filterset_fields = ["room_type", "rate_plan"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        bounds = PriceBounds.objects.filter(room_type=data["room_type"], rate_plan=data["rate_plan"]).first()
        code = status.HTTP_200_OK
        if bounds is None:
            bounds, code = (
                PriceBounds(room_type=data["room_type"], rate_plan=data["rate_plan"]),
                status.HTTP_201_CREATED,
            )
        for field in ("min_price", "max_price"):
            if field in data:
                setattr(bounds, field, data[field])
        bounds.save()
        self._audit("revenue.bounds_saved", bounds)
        return Response(self.get_serializer(bounds).data, status=code)

    def perform_update(self, serializer):
        self._audit("revenue.bounds_saved", serializer.save())

    def perform_destroy(self, instance):
        self._audit("revenue.bounds_deleted", instance)
        instance.delete()

    def _audit(self, action, bounds):
        audit.record(
            action=action,
            target=bounds,
            property=self.request.property,
            actor=self.request.user,
            summary=f"Límites de precio {bounds.room_type.code} · {bounds.rate_plan.code}",
            changes={
                "min_price": None if bounds.min_price is None else money(bounds.min_price),
                "max_price": None if bounds.max_price is None else money(bounds.max_price),
            },
        )


class RecommendationFilter(django_filters.FilterSet):
    start = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    end = django_filters.DateFilter(field_name="date", lookup_expr="lt", help_text="Exclusivo")
    status = django_filters.MultipleChoiceFilter(choices=Status.choices)
    room_type = django_filters.UUIDFilter(field_name="room_type_id")
    rate_plan = django_filters.UUIDFilter(field_name="rate_plan_id")

    class Meta:
        model = RateRecommendation
        fields = ["start", "end", "status", "room_type", "rate_plan"]


class RecommendationViewSet(PropertyScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = RateRecommendation.objects.select_related("room_type", "rate_plan", "decided_by")
    serializer_class = s.RecommendationSerializer
    filterset_class = RecommendationFilter
    ordering_fields = ["date", "change_percent", "recommended_price", "created_at"]
    ordering = ["date", "room_type__sort_order", "room_type__code", "created_at"]
    required_permissions = {
        "list": VIEW,
        "retrieve": VIEW,
        "calendar": VIEW,
        "summary": VIEW,
        "explain": VIEW,
        "*": MANAGE,
    }

    @extend_schema(
        parameters=[
            OpenApiParameter("start", OpenApiTypes.DATE, required=True),
            OpenApiParameter("end", OpenApiTypes.DATE, required=True, description="Exclusivo (≤ 186 noches)"),
            OpenApiParameter("lang", OpenApiTypes.STR, enum=["es", "en"]),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=["get"])
    def calendar(self, request):
        """Heatmap: one row per category × base plan, one cell per night with its recommendation (the pending
        one, else the latest decided one; expired ones are left out)."""
        query = s.CalendarQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        start, end = query.validated_data["start"], query.validated_data["end"]
        prop = request.property
        best: dict = {}
        rows = RateRecommendation.objects.filter(property=prop, date__gte=start, date__lt=end).exclude(
            status=Status.EXPIRED
        )
        for rec in rows.order_by("created_at"):
            key = (rec.room_type_id, rec.rate_plan_id, rec.date.isoformat())
            if best.get(key) is None or best[key].status != Status.PENDING:
                best[key] = rec
        days = [start + timedelta(days=offset) for offset in range((end - start).days)]
        body_rows = []
        for room_type, plan in priced_pairs(prop):
            cells = {}
            for day in days:
                rec = best.get((room_type.pk, plan.pk, day.isoformat()))
                if rec is not None:
                    cells[day.isoformat()] = {
                        "id": str(rec.pk),
                        "status": rec.status,
                        "change_percent": money(rec.change_percent),
                        "current_price": money(rec.current_price),
                        "recommended_price": money(rec.recommended_price),
                        "occupancy": None if rec.occupancy is None else money(rec.occupancy),
                    }
            body_rows.append(
                {"room_type": s.room_type_ref(room_type), "rate_plan": s.rate_plan_ref(plan), "cells": cells}
            )
        return Response(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "business_date": prop.business_date.isoformat(),
                "currency": prop.currency or "COP",
                "dates": [day.isoformat() for day in days],
                "holidays": holiday_list(
                    start, end, user_language(request, query.validated_data.get("lang"))
                ),
                "rows": body_rows,
            }
        )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """KPIs of the pending recommendations (nights from the business date) and the last run."""
        prop = request.property
        pending = RateRecommendation.objects.filter(
            property=prop, status=Status.PENDING, date__gte=prop.business_date
        )
        impact = ExpressionWrapper(
            (F("recommended_price") - F("current_price")) * Coalesce(F("available_units"), Value(0)),
            output_field=DecimalField(max_digits=20, decimal_places=2),
        )
        figures = pending.aggregate(
            count=Count("id"),
            up=Count("id", filter=Q(change_percent__gt=0)),
            down=Count("id", filter=Q(change_percent__lt=0)),
            total_change=Sum("change_percent"),
            impact=Sum(impact),
            impact_up=Sum(impact, filter=Q(change_percent__gt=0)),
            impact_down=Sum(impact, filter=Q(change_percent__lt=0)),
            first_date=Min("date"),
        )
        settings = get_settings(prop)
        last_run = RevenueRun.objects.filter(property=prop).select_related("triggered_by").first()
        count = figures["count"]
        return Response(
            {
                "pending": count,
                "up": figures["up"],
                "down": figures["down"],
                "avg_change_percent": money(figures["total_change"] / count) if count else "0.00",
                "estimated_impact": money(figures["impact"]),
                "impact_up": money(figures["impact_up"]),
                "impact_down": money(figures["impact_down"]),
                "first_date": figures["first_date"].isoformat() if figures["first_date"] else None,
                "currency": prop.currency or "COP",
                "enabled": settings.enabled,
                "auto_apply": settings.auto_apply,
                "last_run": s.RunSerializer(last_run).data if last_run else None,
            }
        )

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def explain(self, request, pk=None):
        """Plain-language explanation of one recommendation written by the LLM (`get_llm(property)`), cached
        for a day. When the LLM is not available it answers the deterministic explanation with
        `simulated: true`."""
        rec = self.get_object()
        key = f"revenue:explain:{rec.pk}:{rec.updated_at.timestamp()}"
        cached = cache.get(key)
        if cached is None:
            text, provider = ai_explanation(rec)
            cached = {"text": text or rec.explanation, "provider": provider, "simulated": not provider}
            if provider:
                cache.set(key, cached, EXPLANATION_CACHE_SECONDS)
        return Response({"id": str(rec.pk), **cached})

    def _decide(self, request, decide):
        body = s.DecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        result = decide(request.property, body.validated_data["ids"], actor=request.user)
        return Response(
            {
                "updated": len(result.recommendations),
                "skipped": result.skipped,
                "errors": result.errors,
                "recommendations": s.RecommendationSerializer(result.recommendations, many=True).data,
            }
        )

    @extend_schema(request=s.DecisionSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def approve(self, request):
        """Approve and apply pending recommendations (`set_daily_rates(source="revenue")`)."""
        return self._decide(request, decisions.approve)

    @extend_schema(request=s.DecisionSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def reject(self, request):
        return self._decide(request, decisions.reject)

    @extend_schema(request=s.DecisionSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def apply(self, request):
        """Apply pending or approved (not yet written) recommendations."""
        return self._decide(request, decisions.apply)


class RunViewSet(
    PropertyScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = RevenueRun.objects.select_related("triggered_by")
    serializer_class = s.RunSerializer
    required_permissions = {"*": VIEW}


class RunNowView(PropertyScopedAPIView):
    """`POST run-now/`: runs the rules now through the automation `revenue.run_rules` (recorded like any
    run)."""

    required_permissions = {"post": MANAGE}

    @extend_schema(request=None, responses={201: s.RunSerializer})
    def post(self, request):
        prop = request.property
        if not get_settings(prop).enabled:
            raise ConflictError(
                "Revenue management está desactivado para esta propiedad", code="revenue_disabled"
            )
        result = automation.run(
            "revenue.run_rules",
            prop,
            params={"trigger": RevenueRun.Trigger.MANUAL, "triggered_by": str(request.user.pk)},
            triggered_by=request.user,
        )
        run_id = (result.details or {}).get("run_id")
        if result.status == "failed" or not run_id:
            raise RunFailed(result.summary or "La corrida de revenue falló")
        run = RevenueRun.objects.select_related("triggered_by").get(pk=run_id, property=prop)
        return Response(s.RunSerializer(run).data, status=status.HTTP_201_CREATED)


class SimulateView(PropertyScopedAPIView):
    """`POST simulate/`: what a run would recommend now (nothing is saved), optionally with a draft rule."""

    required_permissions = {"post": MANAGE}

    @extend_schema(request=s.SimulateSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        prop = request.property
        body = s.SimulateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        start = data.get("start") or prop.business_date
        end = data.get("end") or start + timedelta(days=get_settings(prop).horizon_days)
        if end <= start or (end - start).days > s.MAX_RANGE_DAYS:
            raise DomainError(
                "Rango de fechas inválido", code="validation_error", fields={"end": ["Rango inválido"]}
            )
        rules = active_rules(prop)
        if "rule" in data:
            rules = self._with_draft(request, rules, data["rule"])
        recs = propose(prop, start=start, end=end, rules=rules)
        changes = [rec.change_percent for rec in recs]
        return Response(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "summary": {
                    "count": len(recs),
                    "up": sum(1 for change in changes if change > 0),
                    "down": sum(1 for change in changes if change < 0),
                    "avg_change_percent": money(sum(changes, Decimal(0)) / len(changes))
                    if changes
                    else "0.00",
                    **impact_figures(recs),
                },
                "recommendations": s.RecommendationSerializer(recs, many=True).data,
            }
        )

    def _with_draft(self, request, rules, draft):
        rule_id = draft.get("id")
        if rule_id and not PricingRule.objects.filter(property=request.property, pk=rule_id).exists():
            raise DomainError(
                "La regla no existe", code="validation_error", fields={"rule": ["La regla no existe"]}
            )
        serializer = s.PricingRuleSerializer(data=draft, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        spec = RuleSpec(
            id=str(rule_id) if rule_id else None,
            name=data["name"],
            kind=data["kind"],
            params=data["params"],
            combine=data.get("combine", PricingRule.Combine.STACK),
            priority=data.get("priority", 10),
            room_type_ids=frozenset(room_type.pk for room_type in data.get("room_types", [])),
        )
        others = [rule for rule in rules if not rule_id or rule.id != str(rule_id)]
        return [*others, spec] if data.get("is_active", True) else others


class OptionsView(PropertyScopedAPIView):
    """`GET options/`: categories and active base plans (with each category's default price, the reference
    for the bounds) for the rule editor and the bounds table."""

    required_permissions = {"get": VIEW}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        from apps.inventory.models import RoomType
        from apps.rates.models import RatePlan, RoomTypeRateDefaults

        prop = request.property
        room_types = RoomType.objects.filter(property=prop, is_active=True).order_by("sort_order", "code")
        plans = (
            RatePlan.objects.filter(property=prop, kind=RatePlan.Kind.BASE, is_active=True)
            .prefetch_related("room_types")
            .order_by("sort_order", "code")
        )
        active_ids = {room_type.pk for room_type in room_types}
        defaults = {
            (row.rate_plan_id, row.room_type_id): row.price
            for row in RoomTypeRateDefaults.objects.filter(rate_plan__in=plans).only(
                "rate_plan_id", "room_type_id", "price"
            )
        }

        def plan_payload(plan):
            types = [
                rt
                for rt in sorted(plan.room_types.all(), key=lambda rt: (rt.sort_order, rt.code))
                if rt.pk in active_ids
            ]
            prices = {str(rt.pk): defaults.get((plan.pk, rt.pk)) for rt in types}
            return {
                **s.rate_plan_ref(plan),
                "room_types": [str(rt.pk) for rt in types],
                "default_prices": {
                    key: None if price is None else money(price) for key, price in prices.items()
                },
            }

        return Response(
            {
                "currency": prop.currency or "COP",
                "business_date": prop.business_date.isoformat(),
                "room_types": [{**s.room_type_ref(rt), "kind": rt.kind} for rt in room_types],
                "rate_plans": [plan_payload(plan) for plan in plans],
            }
        )
