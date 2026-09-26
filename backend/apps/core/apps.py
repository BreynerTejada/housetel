from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"
    verbose_name = "Núcleo"

    def ready(self) -> None:
        """Auto-discover every app's permissions.py, providers.py, automations.py and receivers.py."""
        from django.utils.module_loading import autodiscover_modules

        from apps.core import automation, integrations, permissions
        from apps.core.api import schema  # noqa: F401 - registers the OpenAPI auth extension

        permissions.autodiscover()
        integrations.autodiscover()
        automation.autodiscover()
        autodiscover_modules("receivers")
