from pathlib import Path
from decouple import config
import datetime

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='localhost,127.0.0.1',
    cast=lambda v: [s.strip() for s in v.split(',')]
)

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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "mozilla_django_oidc.middleware.SessionRefresh",
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

LANGUAGE_CODE = "fr-be"
TIME_ZONE = "Europe/Brussels"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


KEYCLOAK_URL   = config('KEYCLOAK_URL', default='http://localhost:8080')
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
OIDC_LEEWAY = datetime.timedelta(seconds=60)

AUTHENTICATION_BACKENDS = [
    "accounts.backends.KeycloakOIDCBackend",
    "django.contrib.auth.backends.ModelBackend",
]

LOGIN_REDIRECT_URL  = "/"
LOGOUT_REDIRECT_URL = "/"
LOGIN_URL           = "/oidc/authenticate/"
