"""Data migration (P2): every user that existed before email verification counts as verified.

They signed up or were invited before the feature existed; asking all of them to verify now would only add
noise. New users verify through the link emailed on creation (apps/accounts/receivers.py).
"""

from django.db import migrations
from django.utils import timezone


def mark_existing_users_verified(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(email_verified_at__isnull=True).update(email_verified_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_user_email_verified_at")]

    operations = [migrations.RunPython(mark_existing_users_verified, migrations.RunPython.noop)]
