"""Rate provisioning (plan §C) — signature fixed in Phase A, implemented by B2a."""


def provision_rates(
    property,
    *,
    room_type_prices: dict[str, dict],
    plans: list[dict] | None = None,
    taxes_default: bool = True,
    policies_default: bool = True,
    actor=None,
) -> None:
    """Create the rate setup of a new property (used by AI onboarding and signup).

    room_type_prices: {"DBL": {"price": "320000", "weekend_adjust_percent": 15,
                               "extra_adult_price": "60000", "extra_child_price": "30000"}}
    plans=None → "Tarifa flexible" (base) + "No reembolsable" (−12 %) + "Con desayuno" (+35 000).
    taxes_default → IVA 19 % on lodging (exempt for foreign non-residents) + IVA 19 % on extras.
    policies_default → "Flexible 48h" and "No reembolsable".
    """
    raise NotImplementedError("rates.provision_rates: B2a implementa esta función")
