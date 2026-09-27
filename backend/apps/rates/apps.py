from django.apps import AppConfig


class RatesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.rates"
    label = "rates"
    verbose_name = "Tarifas"

    def ready(self) -> None:
        """Registers the undo of grid writes (`rates.bulk_update`) in core.audit."""
        from apps.rates.services.writes import register_undo_handlers

        register_undo_handlers()
