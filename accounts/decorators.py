from functools import wraps
from django.shortcuts import redirect


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
                if request.user.userprofile.role in roles:
                    return view_func(request, *args, **kwargs)
            except Exception:
                pass
            return redirect("accounts:acces_refuse")
        return wrapper
    return decorator