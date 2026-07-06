"""
Security audit logging: who did what and when.

Connects to Django's built-in auth signals so every login, logout and
failed authentication attempt is recorded, regardless of which
authentication backend handled it (Keycloak OIDC or the local one).
"""
import logging

from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver

logger = logging.getLogger("security")


def _client_ip(request):
    if request is None:
        return "unknown"
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


@receiver(user_logged_in)
def log_user_logged_in(sender, request, user, **kwargs):
    logger.info(
        "LOGIN_SUCCESS user=%s ip=%s",
        getattr(user, "email", user),
        _client_ip(request),
    )


@receiver(user_logged_out)
def log_user_logged_out(sender, request, user, **kwargs):
    logger.info(
        "LOGOUT user=%s ip=%s",
        getattr(user, "email", user) if user else "anonymous",
        _client_ip(request),
    )


@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request=None, **kwargs):
    username = credentials.get("username") or credentials.get("email") or "unknown"
    logger.warning(
        "LOGIN_FAILED username=%s ip=%s",
        username,
        _client_ip(request),
    )
