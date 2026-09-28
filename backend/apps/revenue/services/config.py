"""Revenue settings of a property (created with the defaults the first time they are read)."""

from decimal import Decimal

from apps.revenue.models import RevenueSettings


def get_settings(property) -> RevenueSettings:
    settings = RevenueSettings.objects.filter(property=property).first()
    if settings is not None:
        return settings
    rounding = Decimal("1000") if (property.currency or "COP") == "COP" else Decimal("0")
    settings, _ = RevenueSettings.objects.get_or_create(
        property=property, defaults={"price_rounding": rounding}
    )
    return settings
