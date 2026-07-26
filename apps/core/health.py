import logging

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views import View

logger = logging.getLogger(__name__)


class LivenessView(View):
    """Prove that the web process can serve requests; no dependency checks."""

    def get(self, request):
        return JsonResponse({'status': 'alive'})


class ReadinessView(View):
    """Report whether database and cache dependencies can serve traffic."""

    def get(self, request):
        failed = []
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
        except Exception as exc:
            failed.append('database')
            logger.error('Readiness database check failed | ExceptionType=%s', type(exc).__name__)

        cache_key = 'health:readiness'
        try:
            cache.set(cache_key, 'ok', timeout=10)
            if cache.get(cache_key) != 'ok':
                failed.append('cache')
        except Exception as exc:
            failed.append('cache')
            logger.error('Readiness cache check failed | ExceptionType=%s', type(exc).__name__)

        if failed:
            return JsonResponse({'status': 'unavailable', 'failed': failed}, status=503)
        return JsonResponse({'status': 'ready'})
