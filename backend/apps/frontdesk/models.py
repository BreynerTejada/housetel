"""Front desk models (plan C1)."""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.fields import json_field
from apps.core.models import BaseModel, Property


class NightAuditReport(BaseModel):
    """Closing report of one business date: what the night audit did (no-shows, room charges, overdue
    departures, errors) and the figures of the day. One per (property, business date): the audit of a date
    runs once (see `apps.frontdesk.services.night_audit`)."""

    class Status(models.TextChoices):
        RUNNING = "running", "En curso"
        COMPLETED = "completed", "Completada"
        PARTIAL = "partial", "Completada con errores"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="night_audit_reports")
    business_date = models.DateField()  # the day that was closed
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    summary = json_field()
    run = models.ForeignKey(
        "core.AutomationRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-business_date"]
        constraints = [
            models.UniqueConstraint(fields=["property", "business_date"], name="night_audit_report_unique")
        ]

    def __str__(self) -> str:
        return f"{self.property} · {self.business_date} · {self.status}"
