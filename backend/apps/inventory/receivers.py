"""Inventory receivers (auto-discovered by apps.core). Photo files are removed from storage after the
deleting transaction commits, whether the photo was deleted directly or through a cascade."""

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.inventory.models import Photo


@receiver(post_delete, sender=Photo, dispatch_uid="inventory.delete_photo_file")
def delete_photo_file(sender, instance, **kwargs):
    name = instance.image.name
    if name:
        storage = instance.image.storage
        transaction.on_commit(lambda: storage.delete(name))
