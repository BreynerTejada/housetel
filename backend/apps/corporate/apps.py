from django.apps import AppConfig


class CorporateConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.corporate"
    label = "corporate"
    verbose_name = "Clientes corporativos y cartera"
