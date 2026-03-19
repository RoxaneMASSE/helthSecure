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
            # Désactive le bfcache du navigateur — c'est ce qui cause le problème
            response['Clear-Site-Data'] = '"cache"'

        return response