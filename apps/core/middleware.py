from urllib.parse import urlencode

from django.shortcuts import redirect
from django.http import HttpResponseForbidden
from django.urls import reverse
from django.utils.cache import patch_cache_control


class AdminStaffLoginMiddleware:
    """Route Django-admin authentication through the mandatory staff 2FA flow."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/admin/'):
            if not request.user.is_authenticated:
                login_url = reverse('accounts:login')
                return redirect(f'{login_url}?{urlencode({"next": request.get_full_path()})}')
            if not request.user.is_active or not request.user.is_staff:
                return HttpResponseForbidden('System data is restricted to authorized administrators.')
            if request.path.startswith('/admin/login/'):
                return redirect('admin:index')
        return self.get_response(request)


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
