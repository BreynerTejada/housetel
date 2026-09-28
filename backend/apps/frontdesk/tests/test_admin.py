import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.frontdesk.models import NightAuditReport

pytestmark = pytest.mark.django_db


def test_the_closing_reports_are_browsable_in_the_admin(client, prop):
    report = NightAuditReport.objects.create(
        property=prop, business_date=prop.business_date, status="completed", summary={"errors": []}
    )
    client.force_login(User.objects.create_superuser("root@example.com", "pass1234"))

    listing = client.get(reverse("admin:frontdesk_nightauditreport_changelist"))
    detail = client.get(reverse("admin:frontdesk_nightauditreport_change", args=[report.pk]))

    assert (listing.status_code, detail.status_code) == (200, 200)
    assert prop.name in listing.content.decode()
