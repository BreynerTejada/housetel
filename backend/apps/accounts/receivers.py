"""Receivers of accounts (auto-discovered by core, P2).

- A new user (post_save, created) → the email verification link, once the transaction commits (a signup
  that fails sends nothing). Skipped while seeding, for raw fixture loads and for users born verified:
  invited users (verified when they accept), superusers and demo users.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import User
from apps.accounts.verification import send_verification_on_commit
from apps.core.signals import is_seeding


@receiver(post_save, sender=User, dispatch_uid="accounts.verification_email")
def email_verification_link(sender, instance, created, raw=False, **kwargs):
    if is_seeding():
        return
    if raw or not created or instance.email_verified_at is not None:
        return
    send_verification_on_commit(instance)
