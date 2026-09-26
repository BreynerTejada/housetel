"""Housetel Django settings.

Every value comes from the environment (docker-compose injects `.env`; see `/.env.example`).
"""

import base64
import hashlib
import os
import sys
import tempfile
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def env_list(name: str, default: list[str]) -> list[str]:
    items = [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]
    return items or default


# pytest is always imported before Django settings when the suite runs; used below to switch to fast,
# isolated backends (MD5 hasher, local-memory cache, temporary media root).
TESTING = "pytest" in sys.modules

# --- Core -------------------------------------------------------------------------------------------
DEBUG = env_bool("DJANGO_DEBUG", True)
SECRET_KEY = env("DJANGO_SECRET_KEY") or "housetel-dev-insecure-secret-key-change-me"
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["*"])
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:5173").rstrip("/")

# Fernet key for integration secrets (apps.core.integrations). Without FERNET_KEY a key derived from
# SECRET_KEY is used, which is only acceptable for local development.
FERNET_KEY = (
    env("FERNET_KEY") or base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest()).decode()
)

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
]

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
    *[f"apps.{app}" for app in LOCAL_APPS],
]

MIDDLEWARE = [
    "apps.core.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
        env("DATABASE_URL", "postgres://housetel:housetel@localhost:5432/housetel")
    )
}
# Parallel agents use different test databases: `docker compose run --rm -e TEST_DB_NAME=test_x backend
# pytest`.
DATABASES["default"]["TEST"] = {"NAME": env("TEST_DB_NAME", "test_housetel")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Auth -------------------------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# The SPA is served from the same origin through the Vite proxy: session cookie + CSRF.
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", ["http://localhost:5173", "http://127.0.0.1:5173"])
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False

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
DEFAULT_FROM_EMAIL = "Housetel <no-reply@housetel.co>"
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# --- I18N / time ------------------------------------------------------------------------------------
LANGUAGE_CODE = "es"
LANGUAGES = [("es", "Español"), ("en", "English")]
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

# --- Static / media ---------------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

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
    "DEFAULT_THROTTLE_RATES": {"login": "10/min"},
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Housetel API",
    "DESCRIPTION": (
        "PMS + OTA para hoteles en Colombia. Staff: /api/v1/<app>/ · Público: /api/v1/public/<app>/"
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# --- Logging ----------------------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"console": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "console"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        # Replaces Django's default `django` handlers (a second, DEBUG-only console) so each record — e.g.
        # a 4xx warning or a 500 traceback from django.request — is printed once, in our format.
        "django": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO"), "propagate": False},
        "django.db.backends": {"level": "WARNING"},
        "django.utils.autoreload": {"level": "WARNING"},
    },
}

# --- Test overrides ---------------------------------------------------------------------------------
if TESTING:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "housetel-tests"}
    }
    MEDIA_ROOT = Path(tempfile.gettempdir()) / "housetel-test-media"
