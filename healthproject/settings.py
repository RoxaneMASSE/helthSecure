from pathlib import Path
from decouple import config
from csp.constants import NONCE
import datetime
import sys

BASE_DIR = Path(__file__).resolve().parent.parent

STATIC_URL = 'static/'

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='localhost,127.0.0.1',
    cast=lambda v: [s.strip() for s in v.split(',')]
)

# ── HTTPS enforcement ─────────────────────────────────────────────────────
# Auto-enabled only when the server is launched over TLS
# (python manage.py runserver_plus --cert-file cert.crt), so normal dev
# (`manage.py runserver`, plain HTTP) keeps working without breaking
# sessions/CSRF/redirects.
FORCE_HTTPS = 'runserver_plus' in sys.argv and '--cert-file' in sys.argv

SECURE_SSL_REDIRECT = FORCE_HTTPS
SESSION_COOKIE_SECURE = FORCE_HTTPS
CSRF_COOKIE_SECURE = FORCE_HTTPS
SECURE_HSTS_SECONDS = 3600 if FORCE_HTTPS else 0

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "mozilla_django_oidc",
    "accounts",
    "core",
    "django_extensions",
    "django_recaptcha",
    "csp",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "csp.middleware.CSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.KeysUnlockMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "mozilla_django_oidc.middleware.SessionRefresh",
    'accounts.middleware.NoCacheMiddleware',
]

ROOT_URLCONF = "healthproject.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "csp.context_processors.nonce",
            ],
        },
    },
]

WSGI_APPLICATION = "healthproject.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Brussels"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
KEYCLOAK_URL   = config('KEYCLOAK_URL', default='http://localhost:8080')
# Direct internal URL to Keycloak (port 8180, bypasses Nginx) for Django admin API calls
KEYCLOAK_INTERNAL_URL = config('KEYCLOAK_INTERNAL_URL', default='http://localhost:8180')
KEYCLOAK_REALM = config('KEYCLOAK_REALM', default='health')
KEYCLOAK_ADMIN_USER     = config('KEYCLOAK_ADMIN_USER', default='admin')
KEYCLOAK_ADMIN_PASSWORD = config('KEYCLOAK_ADMIN_PASSWORD', default='admin')
_BASE = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect"

OIDC_RP_CLIENT_ID     = config('OIDC_RP_CLIENT_ID', default='django-health')
OIDC_RP_CLIENT_SECRET = config('OIDC_RP_CLIENT_SECRET', default='fkXZdfIIpbBvYUofQZF5QJxKkSdr0inh')
OIDC_RP_SIGN_ALGO     = "RS256"
OIDC_RP_SCOPES        = "openid email profile"

OIDC_OP_AUTHORIZATION_ENDPOINT = f"{_BASE}/auth"
OIDC_OP_TOKEN_ENDPOINT         = f"{_BASE}/token"
OIDC_OP_USER_ENDPOINT          = f"{_BASE}/userinfo"
OIDC_OP_JWKS_ENDPOINT          = f"{_BASE}/certs"
OIDC_OP_LOGOUT_ENDPOINT        = f"{_BASE}/logout"

OIDC_STORE_ACCESS_TOKEN = True
OIDC_STORE_ID_TOKEN     = True
OIDC_OP_LOGOUT_URL_METHOD = "GET"
OIDC_LEEWAY = datetime.timedelta(seconds=60)

AUTHENTICATION_BACKENDS = [
    "accounts.backends.KeycloakOIDCBackend",
    "django.contrib.auth.backends.ModelBackend",
]

LOGIN_REDIRECT_URL  = "/"
LOGOUT_REDIRECT_URL = "/"
LOGIN_URL           = "/oidc/authenticate/"

RECAPTCHA_PUBLIC_KEY  = config('RECAPTCHA_PUBLIC_KEY')
RECAPTCHA_PRIVATE_KEY = config('RECAPTCHA_PRIVATE_KEY')
SILENCED_SYSTEM_CHECKS = ['django_recaptcha.recaptcha_test_key_error']

# ── Logging (logins, authentication failures, medical file access) ─
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# ELK: disabled by default so it doesn't break dev if Logstash isn't running
# (docker-compose.elk.yml). Enable via .env: LOGSTASH_ENABLED=True
LOGSTASH_ENABLED = config('LOGSTASH_ENABLED', default=False, cast=bool)
LOGSTASH_HOST = config('LOGSTASH_HOST', default='localhost')
LOGSTASH_PORT = config('LOGSTASH_PORT', default=5000, cast=int)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        # One JSON object per line -> easy to ship to ELK (Filebeat/Logstash)
        # without any extra parsing config on the ingestion side.
        "json": {
            "format": (
                '{"time": "%(asctime)s", "level": "%(levelname)s", '
                '"logger": "%(name)s", "message": "%(message)s"}'
            ),
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
        },
        "console": {
            "format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "console",
        },
        "security_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "security.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "json",
        },
        "django_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "django.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "json",
        },
    },
    "loggers": {
        # Authentication, authorization and medical-file access events.
        "security": {
            "handlers": ["console", "security_file"],
            "level": "INFO",
            "propagate": False,
        },
        # Django's own auth/request/security warnings (login_failed, 400/403/500, etc.)
        "django": {
            "handlers": ["console", "django_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

if LOGSTASH_ENABLED:
    LOGGING["handlers"]["logstash"] = {
        "class": "logstash.TCPLogstashHandler",
        "host": LOGSTASH_HOST,
        "port": LOGSTASH_PORT,
        "version": 1,
        "message_type": "django",
    }
    LOGGING["loggers"]["security"]["handlers"].append("logstash")
    LOGGING["loggers"]["django"]["handlers"].append("logstash")

# ── Content-Security-Policy (django-csp 4.x) ─────────────────────────────────
# Django templates contain inline JS; nonces are available
# via {{ CSP_NONCE }} in templates (context_processor csp.context_processors.nonce).
# For existing inline <script> tags, use nonce="{{ CSP_NONCE }}" on the <script> tag.
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        # Templates use inline JS → allow with nonce
        # 'unsafe-inline' stays as a fallback for older browsers (CSP2);
        # browsers supporting nonces (CSP3) automatically ignore it once a nonce is present.
        "script-src": ["'self'", NONCE, "'unsafe-inline'", "https://www.google.com", "https://www.gstatic.com"],
        # Common Django inline styles
        "style-src": ["'self'", "'unsafe-inline'"],
        "connect-src": ["'self'", "https://www.google.com"],
        "img-src": ["'self'", "data:"],
        "font-src": ["'self'"],
        "frame-src": ["'self'", "https://www.google.com"],
        "frame-ancestors": ["'none'"],
        # OIDC redirects to Keycloak
        "form-action": ["'self'", config('KEYCLOAK_URL', default='http://localhost:8080')],
    },
}

