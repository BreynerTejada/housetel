"""Rate limits of the account security endpoints (P2).

`AccountThrottle` is DRF's ScopedRateThrottle with a built-in rate per scope, so the endpoints work without
touching settings; `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"][<scope>]` overrides any of them. Anonymous
requests are counted per IP (behind a proxy set DRF's `NUM_PROXIES`), signed-in ones per user.

In development every browser reaches Django through the Vite proxy with the same IP, so the defaults there
are looser (same idea as the `login` rate in config/settings.py).
"""

from django.conf import settings
from rest_framework.throttling import ScopedRateThrottle

_LOOSE = settings.DEBUG and not getattr(settings, "TESTING", False)

DEFAULT_RATES = {
    # POST public/accounts/password/forgot/ (per IP; each address also gets at most a few emails an hour,
    # see apps.accounts.passwords.RESET_EMAILS_PER_HOUR).
    "password_forgot": "60/hour" if _LOOSE else "10/hour",
    # POST public/accounts/password/reset/ and .../reset/check/ (per IP).
    "password_reset": "120/hour" if _LOOSE else "30/hour",
    # POST public/accounts/verify-email/ (per IP).
    "email_verify": "120/hour" if _LOOSE else "30/hour",
    # POST accounts/me/password/ (per user: guessing the current password from an open session).
    "password_change": "30/hour" if _LOOSE else "10/hour",
    # POST accounts/me/verify-email/resend/ (per user).
    "email_verify_resend": "20/hour" if _LOOSE else "5/hour",
}


class AccountThrottle(ScopedRateThrottle):
    def get_rate(self):
        return self.THROTTLE_RATES.get(self.scope) or DEFAULT_RATES[self.scope]
