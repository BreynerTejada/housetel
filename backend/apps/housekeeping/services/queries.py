"""Read helpers shared by services, API and automations."""

from django.db.models import Q

from apps.housekeeping.models import HousekeepingTask
from apps.housekeeping.services.common import OPEN_STATUSES


def day_filter(property, date) -> Q:
    """Tasks of a business date. For the current business date it also includes the tasks still open from
    earlier days (a room left dirty yesterday is still today's work), so nothing gets stranded when the
    daily generation does not run."""
    condition = Q(business_date=date)
    if date == property.business_date:
        condition |= Q(business_date__lt=date, status__in=OPEN_STATUSES)
    return condition


def day_tasks(property, date):
    return HousekeepingTask.objects.filter(property=property).filter(day_filter(property, date))
