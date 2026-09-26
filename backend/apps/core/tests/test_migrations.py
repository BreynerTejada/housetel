from importlib import import_module

import pytest
from django.contrib.postgres.operations import BtreeGistExtension
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader


def test_core_initial_migration_enables_btree_gist_first():
    migration = import_module("apps.core.migrations.0001_initial").Migration
    assert isinstance(migration.operations[0], BtreeGistExtension)


def test_bookings_exclusion_constraints_run_after_the_extension():
    loader = MigrationLoader(None, ignore_no_migrations=True)
    plan = loader.graph.forwards_plan(("bookings", "0001_initial"))
    assert ("core", "0001_initial") in plan


@pytest.mark.django_db
def test_models_and_migrations_are_in_sync(capsys):
    # Raises SystemExit(1) when a model change has no migration.
    call_command("makemigrations", check=True, dry_run=True, verbosity=0)


@pytest.mark.django_db
def test_btree_gist_is_installed_in_the_database():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'btree_gist'")
        assert cursor.fetchone() == (1,)
