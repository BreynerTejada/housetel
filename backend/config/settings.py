"""Housetel Django settings.

Every value comes from the environment (docker-compose injects `.env`; see `/.env.example`). `DJANGO_ENV`
picks the profile:

- `development` (default): debug pages, permissive hosts, public API docs, simulations on.
- `production`: refuses to start with DJANGO_DEBUG on or without DJANGO_SECRET_KEY / FERNET_KEY /
  FRONTEND_URL; HTTPS-only cookies, HSTS, JSON logs, `/django-admin/` and the API docs locked down,
  simulations off unless HOUSETEL_ALLOW_SIMULATIONS=1. Deployment guide: `docs/deploy.md`.
"""

import base64
import hashlib
import os
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path
from urllib.parse import urlsplit

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


def env_list(name: str, default: list[str]) -> list[str]:
    items = [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]
    return items or default


def installed(module: str) -> bool:
    """Optional production dependencies (sidecar, storages, sentry) may be missing from an old dev image."""
    return find_spec(module) is not None


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""


def unique(items) -> list:
    return list(dict.fromkeys(item for item in items if item))


# pytest is always imported before Django settings when the suite runs; used below to switch to fast,
# isolated backends (MD5 hasher, local-memory cache, temporary media root).
TESTING = "pytest" in sys.modules

# --- Environment ------------------------------------------------------------------------------------
DJANGO_ENV = env("DJANGO_ENV", "development").strip().lower() or "development"
if DJANGO_ENV not in {"development", "production"}:
    raise ImproperlyConfigured(f"DJANGO_ENV must be 'development' or 'production', not {DJANGO_ENV!r}")
IS_PRODUCTION = DJANGO_ENV == "production"

# --- Core -------------------------------------------------------------------------------------------
DEV_SECRET_KEY = "housetel-dev-insecure-secret-key-change-me"
DEBUG = env_bool("DJANGO_DEBUG", not IS_PRODUCTION)
SECRET_KEY = env("DJANGO_SECRET_KEY") or ("" if IS_PRODUCTION else DEV_SECRET_KEY)
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:5173").rstrip("/")
# Where the outside world reaches this installation (payment/WhatsApp webhooks, links sent to guests). Set it
# to a tunnel (`cloudflared tunnel --url http://localhost:5173`) to receive real webhooks in development.
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL").rstrip("/")
ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    unique(urlsplit(url).hostname for url in (FRONTEND_URL, PUBLIC_BASE_URL)) if IS_PRODUCTION else ["*"],
)

# Fernet key for integration secrets (apps.core.integrations). Without FERNET_KEY a key derived from
# SECRET_KEY is used, which is only acceptable for local development (production refuses to start).
FERNET_KEY = env("FERNET_KEY") or (
    "" if IS_PRODUCTION else base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest()).decode()
)

# Simulations (simulated payment gateway, OTA/WhatsApp simulators, simulated providers): unset → on in
# development, off in production; "1" / "0" force them on or off (apps.core.runtime.simulations_enabled).
HOUSETEL_ALLOW_SIMULATIONS = (
    env_bool("HOUSETEL_ALLOW_SIMULATIONS") if env("HOUSETEL_ALLOW_SIMULATIONS").strip() else None
)

# Support channels shown in the app ("Help and support", error pages). Empty = not offered.
SUPPORT_WHATSAPP = env("SUPPORT_WHATSAPP")
SUPPORT_EMAIL = env("SUPPORT_EMAIL", "soporte@housetel.co")
SUPPORT_DOCS_URL = env("SUPPORT_DOCS_URL")

if IS_PRODUCTION:
    _problems = []
    if DEBUG:
        _problems.append("DJANGO_DEBUG must be 0")
    if not SECRET_KEY or SECRET_KEY == DEV_SECRET_KEY:
        _problems.append("DJANGO_SECRET_KEY is missing")
    if not FERNET_KEY:
        _problems.append("FERNET_KEY is missing")
    else:
        from cryptography.fernet import Fernet

        try:
            Fernet(FERNET_KEY)
        except (TypeError, ValueError):
            _problems.append("FERNET_KEY is not a valid Fernet key")
    if not env("FRONTEND_URL"):
        _problems.append("FRONTEND_URL is missing (public URL of the app, e.g. https://app.example.com)")
    if not ALLOWED_HOSTS:
        _problems.append("DJANGO_ALLOWED_HOSTS is missing")
    if _problems:
        raise ImproperlyConfigured(
            "Production settings are incomplete: " + "; ".join(_problems) + ". See docs/deploy.md."
        )

# `/django-admin/`: off in production unless ADMIN_ENABLED=1, and then only for signed-in staff users (anyone
# else gets a 404; staff sign in through the app's /login). The OpenAPI schema and Swagger UI (`/api/schema/`,
# `/api/docs/`) are public in development and staff-only in production (API_DOCS_PUBLIC overrides).
ADMIN_ENABLED = env_bool("ADMIN_ENABLED", not IS_PRODUCTION)
ADMIN_STAFF_ONLY = env_bool("ADMIN_STAFF_ONLY", IS_PRODUCTION)
API_DOCS_PUBLIC = env_bool("API_DOCS_PUBLIC", not IS_PRODUCTION)

# --- External providers (platform level) ------------------------------------------------------------
GEMINI_API_KEY = env("GEMINI_API_KEY")
GEMINI_MODEL = env("GEMINI_MODEL", "gemini-3.5-flash")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
CLAUDE_MODEL = env("CLAUDE_MODEL", "claude-sonnet-5")
WOMPI_PLATFORM_PUBLIC_KEY = env("WOMPI_PLATFORM_PUBLIC_KEY")
WOMPI_PLATFORM_PRIVATE_KEY = env("WOMPI_PLATFORM_PRIVATE_KEY")
WOMPI_PLATFORM_INTEGRITY_SECRET = env("WOMPI_PLATFORM_INTEGRITY_SECRET")
WOMPI_PLATFORM_EVENTS_SECRET = env("WOMPI_PLATFORM_EVENTS_SECRET")
WOMPI_PLATFORM_ENV = env("WOMPI_PLATFORM_ENV", "sandbox")

# --- Applications -----------------------------------------------------------------------------------
LOCAL_APPS = [
    "core",
    "accounts",
    "inventory",
    "rates",
    "bookings",
    "guests",
    "finance",
    "frontdesk",
    "housekeeping",
    "distribution",
    "marketplace",
    "guestportal",
    "messaging",
    "compliance",
    "revenue",
    "ai",
    "reports",
    "saas",
    "control",
    "corporate",
    "imports",
]

# Swagger UI / Redoc assets served by Django itself (offline) instead of a CDN.
SWAGGER_OFFLINE = installed("drf_spectacular_sidecar")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    *(["drf_spectacular_sidecar"] if SWAGGER_OFFLINE else []),
    *[f"apps.{app}" for app in LOCAL_APPS],
]

MIDDLEWARE = [
    "apps.core.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # API errors in the user's language: Accept-Language here, the signed-in user's profile language below.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.UserLanguageMiddleware",
    "apps.core.middleware.AdminGateMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database ---------------------------------------------------------------------------------------
DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", "postgres://housetel:housetel@localhost:5432/housetel"),
        # Persistent connections under gunicorn/celery in production (health-checked before reuse).
        conn_max_age=env_int("DB_CONN_MAX_AGE", 60 if IS_PRODUCTION else 0),
        conn_health_checks=True,
    )
}
# Parallel agents use different test databases: `docker compose run --rm -e TEST_DB_NAME=test_x backend
# pytest`.
DATABASES["default"]["TEST"] = {"NAME": env("TEST_DB_NAME", "test_housetel")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Auth -------------------------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    # Our User has `email` and `full_name` (no username/first_name/last_name): compare with those (P2, P-INT).
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ("email", "full_name")},
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# The SPA is served from the same origin (Vite proxy in development, nginx in production): session cookie +
# CSRF. The public URL (tunnel) is always trusted too, so the app also works through it.
CSRF_TRUSTED_ORIGINS = unique(
    [
        *env_list(
            "CSRF_TRUSTED_ORIGINS",
            [origin_of(FRONTEND_URL)]
            if IS_PRODUCTION
            else ["http://localhost:5173", "http://127.0.0.1:5173"],
        ),
        origin_of(PUBLIC_BASE_URL),
    ]
)
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the SPA reads `csrftoken` and sends it back as X-CSRFToken
SESSION_COOKIE_HTTPONLY = True

# --- Security headers (both profiles) and HTTPS (production) ----------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"  # the API is never framed (the embeddable widget is an SPA page served by nginx)
if IS_PRODUCTION:
    # nginx (and any load balancer in front of it) terminates TLS and sends X-Forwarded-Proto.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^api/v1/public/core/health/"]  # container healthchecks speak plain HTTP
    SECURE_HSTS_SECONDS = env_int("DJANGO_HSTS_SECONDS", 31_536_000)  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    # Only for trying the production stack over plain HTTP on a host other than localhost.
    SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
    CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE

# --- Cache / Celery ---------------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "housetel",
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_TIMEZONE = "America/Bogota"
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_IGNORE_RESULT = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# --- Email (Mailpit locally) ------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = int(env("EMAIL_PORT", "1025"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 20)
# The sender domain must be the one authorized by SPF/DKIM (docs/integraciones-reales.md → SMTP).
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "Housetel <no-reply@housetel.co>")
SERVER_EMAIL = env("SERVER_EMAIL", DEFAULT_FROM_EMAIL)

# --- I18N / time ------------------------------------------------------------------------------------
LANGUAGE_CODE = "es"
LANGUAGES = [("es", "Español"), ("en", "English")]
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

# --- Static / media ---------------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = Path(env("STATIC_ROOT")) if env("STATIC_ROOT") else BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT")) if env("MEDIA_ROOT") else BASE_DIR / "media"
# Private files (identity documents, signatures, damage photos, invoices, SIRE files) never live under
# MEDIA_ROOT. Unset → `<MEDIA_ROOT>-private` (backend/media-private/ in development); in production point it
# to a folder no web server publishes (the production compose file mounts its own volume there).
PRIVATE_MEDIA_ROOT = Path(env("PRIVATE_MEDIA_ROOT")) if env("PRIVATE_MEDIA_ROOT") else None

# Two separate storages: `default` = public media (room photos, logos: served at /media/photos|branding|
# booking-engine/), `private` = private files (only through authenticated API views; apps.core.storage).
# With AWS_STORAGE_BUCKET_NAME both move to S3-compatible object storage (AWS S3, DigitalOcean Spaces,
# Cloudflare R2, MinIO…): public media in that bucket, private files in AWS_PRIVATE_STORAGE_BUCKET_NAME (or a
# private prefix of the same bucket), always with a private ACL and signed, short-lived URLs.
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
USE_S3_STORAGE = bool(AWS_STORAGE_BUCKET_NAME) and not TESTING
STATICFILES_STORAGE_BACKEND = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
if USE_S3_STORAGE:
    if not installed("storages"):
        raise ImproperlyConfigured(
            "AWS_STORAGE_BUCKET_NAME needs django-storages and boto3 "
            "(rebuild the image: backend/requirements.txt)"
        )
    _s3_common = {
        "access_key": env("AWS_ACCESS_KEY_ID") or None,
        "secret_key": env("AWS_SECRET_ACCESS_KEY") or None,
        "region_name": env("AWS_S3_REGION_NAME") or None,
        "endpoint_url": env("AWS_S3_ENDPOINT_URL") or None,
        "addressing_style": env("AWS_S3_ADDRESSING_STYLE") or None,
        "signature_version": "s3v4",
        "file_overwrite": False,
    }
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                **_s3_common,
                "bucket_name": AWS_STORAGE_BUCKET_NAME,
                "location": env("AWS_PUBLIC_MEDIA_LOCATION", "media"),
                "custom_domain": env("AWS_S3_CUSTOM_DOMAIN") or None,
                "default_acl": env("AWS_DEFAULT_ACL") or None,  # e.g. public-read if the bucket has no policy
                "querystring_auth": env_bool("AWS_QUERYSTRING_AUTH", False),
            },
        },
        "private": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                **_s3_common,
                "bucket_name": env("AWS_PRIVATE_STORAGE_BUCKET_NAME") or AWS_STORAGE_BUCKET_NAME,
                "location": env("AWS_PRIVATE_MEDIA_LOCATION", "private"),
                "default_acl": "private",
                "querystring_auth": True,
                "querystring_expire": 300,
                "custom_domain": None,
            },
        },
        "staticfiles": STATICFILES_STORAGE_BACKEND,
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},  # MEDIA_ROOT, MEDIA_URL
        "private": {"BACKEND": "apps.core.storage.LocalPrivateStorage"},  # PRIVATE_MEDIA_ROOT, no URL
        "staticfiles": STATICFILES_STORAGE_BACKEND,
    }

# --- Django REST framework --------------------------------------------------------------------------
REST_FRAMEWORK = {
    # Session auth that answers 401 to anonymous requests (the SPA redirects to /login on 401).
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.core.api.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.api.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "EXCEPTION_HANDLER": "apps.core.api.exceptions.exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        *(["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    ],
    # In development every browser reaches Django through the Vite proxy with the same IP, so the demo users
    # share one login budget: a looser default there (override with LOGIN_THROTTLE_RATE).
    "DEFAULT_THROTTLE_RATES": {
        "login": env("LOGIN_THROTTLE_RATE", "30/min" if DEBUG and not TESTING else "10/min"),
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}
# Per-IP throttles behind proxies: how many proxies append to X-Forwarded-For in front of gunicorn (nginx = 1;
# add one per load balancer / CDN in front of nginx). Unset in development (Vite does not add the header).
if env("NUM_PROXIES").strip() or IS_PRODUCTION:
    REST_FRAMEWORK["NUM_PROXIES"] = env_int("NUM_PROXIES", 1)

SPECTACULAR_SETTINGS = {
    "TITLE": "Housetel API",
    "DESCRIPTION": (
        "PMS + OTA para hoteles en Colombia. Staff: /api/v1/<app>/ · Público: /api/v1/public/<app>/"
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # `/api/schema/` and `/api/docs/`: anyone in development, staff users (is_staff) in production.
    "SERVE_PERMISSIONS": [
        "rest_framework.permissions.AllowAny" if API_DOCS_PUBLIC else "rest_framework.permissions.IsAdminUser"
    ],
    # Choice fields that share a name across apps (`kind`, `status`, `source`) but not their options get a
    # stable enum name here instead of a hashed one (`KindD0cEnum`) plus a warning. Add an entry when a new
    # app introduces a colliding choice set (`manage.py spectacular --validate --fail-on-warn` must pass;
    # test: apps/core/tests/test_schema.py).
    "ENUM_NAME_OVERRIDES": {
        "BookingStatusEnum": "apps.bookings.models.BookingStatus",
        "ReservationSourceEnum": "apps.bookings.models.Reservation.Source",
        "RoomTypeKindEnum": "apps.inventory.models.RoomType.Kind",
        "RoomBlockKindEnum": "apps.inventory.models.RoomBlock.Kind",
        "GuestDocumentKindEnum": "apps.guests.models.GuestDocument.Kind",
        # Phase C (C-INT). Invoice.Kind has the same options as InvoiceResolution.DocumentKind, so both
        # fields share InvoiceKindEnum; every real/simulated field with the "Real/Simulado" labels
        # (IntegrationSetting, PaymentIntent, compliance documents) shares IntegrationModeEnum.
        "InvoiceStatusEnum": "apps.compliance.models.Invoice.Status",
        "InvoiceKindEnum": "apps.compliance.models.Invoice.Kind",
        "SireReportStatusEnum": "apps.compliance.models.SireReport.Status",
        "TraRegistrationStatusEnum": "apps.compliance.models.TraRegistration.Status",
        "IntegrationModeEnum": "apps.core.models.IntegrationSetting.Mode",
        "PricingRuleKindEnum": "apps.revenue.models.PricingRule.Kind",
        "RateRecommendationStatusEnum": "apps.revenue.models.RateRecommendation.Status",
        "RevenueRunStatusEnum": "apps.revenue.models.RevenueRun.Status",
        # es/en with human labels (User, Guest, FAQ, chatbot) vs the bare codes of request serializers.
        "LanguageEnum": "apps.accounts.models.User.Language",
        "LanguageCodeEnum": ["es", "en"],
        # Bare real/simulated codes of the AI settings/status serializers.
        "ModeCodeEnum": ["real", "simulated"],
    },
}
if SWAGGER_OFFLINE:
    SPECTACULAR_SETTINGS.update(
        {"SWAGGER_UI_DIST": "SIDECAR", "SWAGGER_UI_FAVICON_HREF": "SIDECAR", "REDOC_DIST": "SIDECAR"}
    )

# --- Logging ----------------------------------------------------------------------------------------
# `json` (one JSON object per line, with the request id: production default) or `console` (development).
LOG_LEVEL = env("LOG_LEVEL", "INFO")
LOG_FORMAT = env("LOG_FORMAT", "json" if IS_PRODUCTION else "console").strip().lower()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"},
        "json": {"()": "apps.core.logs.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if LOG_FORMAT == "json" else "console",
        }
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        # Replaces Django's default `django` handlers (a second, DEBUG-only console) so each record — e.g.
        # a 4xx warning or a 500 traceback from django.request — is printed once, in our format.
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.db.backends": {"level": "WARNING"},
        "django.utils.autoreload": {"level": "WARNING"},
    },
}
# With JSON logs Celery keeps our root handler instead of installing its own plain-text one.
CELERY_WORKER_HIJACK_ROOT_LOGGER = LOG_FORMAT != "json"

# --- Monitoring (optional) --------------------------------------------------------------------------
SENTRY_DSN = env("SENTRY_DSN")
if SENTRY_DSN and not TESTING:
    if not installed("sentry_sdk"):
        raise ImproperlyConfigured(
            "SENTRY_DSN needs sentry-sdk (rebuild the image: backend/requirements.txt)"
        )
    import sentry_sdk

    # Django, Celery and Redis integrations are enabled automatically when those libraries are present.
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("SENTRY_ENVIRONMENT", DJANGO_ENV),
        release=env("SENTRY_RELEASE") or None,
        traces_sample_rate=float(env("SENTRY_TRACES_SAMPLE_RATE", "0")),
        send_default_pii=False,
    )

# --- Test overrides ---------------------------------------------------------------------------------
if TESTING:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "housetel-tests"}
    }
    MEDIA_ROOT = Path(tempfile.gettempdir()) / "housetel-test-media"
    PRIVATE_MEDIA_ROOT = None  # → housetel-test-media-private, next to the temporary MEDIA_ROOT
