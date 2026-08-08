import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

IS_PRODUCTION = "DYNO" in os.environ or os.getenv("DJANGO_ENV", "").lower() == "production"

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if IS_PRODUCTION and not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is required in production")
if not SECRET_KEY:
    SECRET_KEY = "dev-secret-key"

DEBUG = False if IS_PRODUCTION else os.getenv("DJANGO_DEBUG", "1") == "1"

ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0,.ngrok-free.dev,.ngrok-free.app").split(",")
if "DYNO" in os.environ:
    ALLOWED_HOSTS.append("roomink-0315e6e58623.herokuapp.com")

# Heroku / reverse proxy 配下の公開URLを正しく復元する。
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = IS_PRODUCTION
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "3600" if IS_PRODUCTION else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", "0") == "1"
SECURE_HSTS_PRELOAD = os.getenv("DJANGO_SECURE_HSTS_PRELOAD", "0") == "1"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO")},
    "loggers": {
        "django.server": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "core": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"), "propagate": False},
    },
}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # third-party
    "rest_framework",
    "corsheaders",
    "django_filters",
    "drf_spectacular",

    # local
    "core",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# --- CORS (Vue dev server etc.) ---
_cors_env = os.getenv("DJANGO_CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://roomink-0315e6e58623.herokuapp.com",
    "https://roomink.netlify.app",
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "origin",
    "x-csrftoken",
    "x-requested-with",
]

# --- CSRF ---
_csrf_env = os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_env.split(",") if o.strip()] if _csrf_env else [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
if "DYNO" in os.environ:
    CSRF_TRUSTED_ORIGINS.append("https://roomink-0315e6e58623.herokuapp.com")
    CSRF_TRUSTED_ORIGINS.append("https://roomink.netlify.app")

# --- Cross-origin cookie settings (for Amplify ↔ App Runner) ---
if _cors_env or IS_PRODUCTION:
    SESSION_COOKIE_SAMESITE = "None"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = "None"
    CSRF_COOKIE_SECURE = True

# --- DRF minimal ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 200,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Roomink API",
    "VERSION": "0.1.0",
    "ENUM_NAME_OVERRIDES": {
        "EndDayOffsetEnum": "core.models.DAY_OFFSET_CHOICES",
        "ShiftRequestStatusEnum": "core.models.ShiftRequest.Status",
        "OrderStatusEnum": "core.models.Order.Status",
        "CallLogStatusEnum": "core.models.CallLog.Status",
        "SmsLogStatusEnum": "core.models.SmsLog.Status",
        "LineNotificationStatusEnum": "core.models.LineNotificationLog.Status",
        "DailySettlementStatusEnum": "core.models.DailySettlement.Status",
        "CastDailyCheckoutStatusEnum": "core.models.CastDailyCheckout.Status",
        "CastAdjustmentStatusEnum": "core.models.CastAdjustment.Status",
        "CastNoteStatusEnum": "core.models.CastNote.Status",
        "ShiftConfirmNotificationStatusEnum": "core.models.ShiftConfirmNotificationLog.Status",
    },
}

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database ---
# DATABASE_URL があれば Postgres（Heroku等）、なければ個別環境変数 or sqlite3
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    import urllib.parse
    url = urllib.parse.urlparse(DATABASE_URL)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": url.path.lstrip("/"),
            "USER": url.username or "",
            "PASSWORD": url.password or "",
            "HOST": url.hostname or "localhost",
            "PORT": url.port or 5432,
        }
    }
elif os.getenv("USE_POSTGRES", "0") == "1":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "roomink"),
            "USER": os.getenv("POSTGRES_USER", "roomink"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "roomink"),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ja"
TIME_ZONE = "Asia/Tokyo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Twilio Webhook signature validation ---
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WEBHOOK_PUBLIC_BASE_URL = os.getenv("TWILIO_WEBHOOK_PUBLIC_BASE_URL", "").rstrip("/")
TWILIO_WEBHOOK_ALLOW_UNSIGNED = os.getenv("TWILIO_WEBHOOK_ALLOW_UNSIGNED", "0") == "1"

# --- Customer account invitation / SMS delivery ---
FRONTEND_URL = os.getenv("FRONTEND_URL", "").rstrip("/")
SMS_DUMMY_MODE = os.getenv("SMS_DUMMY_MODE", "0") == "1"

# --- LINE Messaging API ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
