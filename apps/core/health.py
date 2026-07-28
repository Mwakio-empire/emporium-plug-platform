import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views import View

logger = logging.getLogger(__name__)
ASYNC_PIPELINE_HEARTBEAT_KEY = 'health:async-pipeline:last-seen'


def _health_response(payload, *, status=200):
    response = JsonResponse(payload, status=status)
    response['Cache-Control'] = 'no-store'
    return response


def _dependency_failures(*, include_async_pipeline=False):
    failed = []
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception as exc:
        failed.append('database')
        logger.error('Readiness database check failed | ExceptionType=%s', type(exc).__name__)

    cache_available = True
    cache_key = 'health:readiness'
    try:
        cache.set(cache_key, 'ok', timeout=10)
        if cache.get(cache_key) != 'ok':
            cache_available = False
            failed.append('cache')
    except Exception as exc:
        cache_available = False
        failed.append('cache')
        logger.error('Readiness cache check failed | ExceptionType=%s', type(exc).__name__)

    if include_async_pipeline and cache_available:
        try:
            heartbeat = cache.get(ASYNC_PIPELINE_HEARTBEAT_KEY)
            age_seconds = time.time() - float(heartbeat)
        except (TypeError, ValueError):
            age_seconds = settings.ASYNC_HEARTBEAT_MAX_AGE_SECONDS + 1
        except Exception as exc:
            logger.error(
                'Operational heartbeat cache check failed | ExceptionType=%s',
                type(exc).__name__,
            )
            failed.append('cache')
            return failed
        if age_seconds < -60 or age_seconds > settings.ASYNC_HEARTBEAT_MAX_AGE_SECONDS:
            failed.append('async_pipeline')
    return failed


class LivenessView(View):
    """Prove that the web process can serve requests; no dependency checks."""

    def get(self, request):
        return _health_response({'status': 'alive'})


class ReadinessView(View):
    """Report whether database and cache dependencies can serve traffic."""

    def get(self, request):
        failed = _dependency_failures()
        if failed:
            return _health_response({'status': 'unavailable', 'failed': failed}, status=503)
        return _health_response({'status': 'ready'})


class OperationalHealthView(View):
    """Check database, cache, and the combined Beat-to-worker task pipeline."""

    def get(self, request):
        failed = _dependency_failures(include_async_pipeline=True)
        if failed:
            return _health_response({'status': 'unavailable', 'failed': failed}, status=503)
        return _health_response({'status': 'operational'})
