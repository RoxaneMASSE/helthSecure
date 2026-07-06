from django.shortcuts import redirect


# ── URLs excluded from the key check ─────────────────────────────────────────
_EXCLUDED_PREFIXES = (
    '/accounts/setup-keys/',
    '/accounts/unlock-keys/',
    '/accounts/api/',
    '/accounts/logout/',
    '/oidc/',
    '/static/',
    '/admin/',
)


class KeysUnlockMiddleware:
    """
    Redirects the user to setup-keys (first time) or unlock-keys
    (subsequent logins) if their E2E keys are not unlocked for the session.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._needs_redirect(request):
            try:
                profile = request.user.userprofile
                if profile.public_key:
                    return redirect('/accounts/unlock-keys/')
                else:
                    return redirect('/accounts/setup-keys/')
            except Exception:
                return redirect('/accounts/setup-keys/')

        return self.get_response(request)

    def _needs_redirect(self, request):
        if not request.user.is_authenticated:
            return False
        path = request.path
        for prefix in _EXCLUDED_PREFIXES:
            if path.startswith(prefix):
                return False
        if request.session.get('keys_unlocked'):
            return False
        return True


class NoCacheMiddleware:
    PUBLIC_PATHS = ['/', '/accounts/register/', '/oidc/authenticate/']

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.user.is_authenticated or request.path not in self.PUBLIC_PATHS:
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            # Disables the browser's bfcache — this is what causes the issue
            response['Clear-Site-Data'] = '"cache"'

        return response
