class NoCacheMiddleware:
    """
    Empêche le navigateur de mettre en cache les pages authentifiées.
    Ainsi, la flèche 'retour' ne peut pas recharger une page protégée
    après déconnexion.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        return response