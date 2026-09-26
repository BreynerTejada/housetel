from django.apps import AppConfig


class SaasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.saas"
    label = "saas"
    verbose_name = "SaaS"
