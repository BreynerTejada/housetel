from datetime import timedelta
from decimal import Decimal

import factory
from django.utils.timezone import localdate

from apps.core.tests.factories import PropertyFactory
from apps.inventory.tests.factories import RoomTypeFactory
from apps.rates.models import CancellationPolicy, DailyRate, Extra, RatePlan, RoomTypeRateDefaults, Tax


class TaxFactory(factory.django.DjangoModelFactory):
    """Default: IVA 19 % on lodging, not included in the price, exempt for foreign non-residents."""

    class Meta:
        model = Tax

    property = factory.SubFactory(PropertyFactory)
    code = factory.Sequence(lambda n: f"IVA{n}")
    name = "IVA 19%"
    rate = Decimal("19.00")
    applies_to = Tax.AppliesTo.ROOM
    included_in_price = False
    exempt_foreign_non_residents = True
    is_active = True


class CancellationPolicyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CancellationPolicy

    property = factory.SubFactory(PropertyFactory)
    name = factory.LazyFunction(lambda: {"es": "Flexible 48h", "en": "Flexible 48h"})
    non_refundable = False
    free_until_hours_before = 48
    penalty_type = CancellationPolicy.PenaltyType.FIRST_NIGHT
    penalty_value = Decimal("0")


class RatePlanFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RatePlan
        skip_postgeneration_save = True

    property = factory.SubFactory(PropertyFactory)
    code = factory.Sequence(lambda n: f"PLAN{n}")
    name = factory.LazyAttribute(lambda o: {"es": f"Tarifa {o.code}", "en": f"Rate {o.code}"})
    kind = RatePlan.Kind.BASE
    meal_plan = RatePlan.MealPlan.ROOM_ONLY
    is_public = True

    @factory.post_generation
    def room_types(self, create, extracted, **kwargs):
        if create and extracted:
            self.room_types.set(extracted)


class DerivedRatePlanFactory(RatePlanFactory):
    kind = RatePlan.Kind.DERIVED
    parent = factory.SubFactory(RatePlanFactory, property=factory.SelfAttribute("..property"))
    derivation_type = RatePlan.DerivationType.PERCENT
    derivation_value = Decimal("-12")


class RoomTypeRateDefaultsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RoomTypeRateDefaults

    room_type = factory.SubFactory(RoomTypeFactory)
    rate_plan = factory.SubFactory(RatePlanFactory, property=factory.SelfAttribute("..room_type.property"))
    price = Decimal("320000")
    dow_adjustments = factory.LazyFunction(dict)
    extra_adult_price = Decimal("60000")
    extra_child_price = Decimal("30000")
    child_age_limit = 12


class DailyRateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DailyRate

    room_type = factory.SubFactory(RoomTypeFactory)
    rate_plan = factory.SubFactory(RatePlanFactory, property=factory.SelfAttribute("..room_type.property"))
    date = factory.LazyFunction(lambda: localdate() + timedelta(days=7))
    price = Decimal("350000")
    source = DailyRate.Source.MANUAL


class ExtraFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Extra

    property = factory.SubFactory(PropertyFactory)
    code = factory.Sequence(lambda n: f"EXTRA{n}")
    name = factory.LazyFunction(lambda: {"es": "Desayuno", "en": "Breakfast"})
    price = Decimal("35000")
    charge_type = Extra.ChargeType.PER_PERSON_NIGHT
