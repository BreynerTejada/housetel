"""PostgreSQL `unaccent` (contrib, trusted extension): the CRM search matches "Perez" with "Pérez"."""

from django.contrib.postgres.operations import UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("guests", "0002_private_documents_anonymized"),
    ]

    operations = [UnaccentExtension()]
