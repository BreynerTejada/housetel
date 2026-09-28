"""Per-property housekeeping settings (created with the plan's defaults on first use)."""

from apps.core import audit
from apps.housekeeping.models import HousekeepingSettings

EDITABLE_FIELDS = ("stayover_frequency_days", "require_inspection", "auto_assign", "minutes_per_shift")


def get_settings(property) -> HousekeepingSettings:
    settings, _created = HousekeepingSettings.objects.get_or_create(property=property)
    return settings


def update_settings(property, data: dict, *, actor=None) -> HousekeepingSettings:
    """Update the editable fields present in `data` (already validated by the API serializer)."""
    settings = get_settings(property)
    changes = {}
    for field in EDITABLE_FIELDS:
        if field in data and getattr(settings, field) != data[field]:
            changes[field] = [getattr(settings, field), data[field]]
            setattr(settings, field, data[field])
    if changes:
        settings.save(update_fields=[*changes, "updated_at"])
        audit.record(
            action="housekeeping.settings_updated",
            target=settings,
            actor=actor,
            property=property,
            summary="Actualizó la configuración de limpieza",
            changes=changes,
        )
    return settings
