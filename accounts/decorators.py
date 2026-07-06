from functools import wraps
from django.shortcuts import redirect
import logging

logger = logging.getLogger("security")


def role_required(*roles):
    """
    Usage : @role_required("doctor")
            @role_required("doctor", "patient")
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect("/oidc/authenticate/")
            try:
                user_role = request.user.userprofile.role
                if user_role in roles:
                    return view_func(request, *args, **kwargs)
                logger.warning(
                    "ACCESS_DENIED user=%s role=%s required=%s path=%s",
                    request.user.email, user_role, roles, request.path,
                )
            except Exception as e:
                logger.error(f"Role check failed for user {request.user}: {e}")
            return redirect("accounts:acces_refuse")
        return wrapper
    return decorator