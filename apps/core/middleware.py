from django.utils.cache import patch_cache_control


class SecurityResponseHeadersMiddleware:
    """Add browser hardening and prevent shared caching of authenticated pages."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault(
            'Permissions-Policy',
            'camera=(), microphone=(), geolocation=(), payment=()',
        )
        response.setdefault('X-Permitted-Cross-Domain-Policies', 'none')
        if getattr(request, 'user', None) and request.user.is_authenticated:
            patch_cache_control(response, private=True, no_store=True)
        return response
