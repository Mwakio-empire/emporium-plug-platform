from django.core.cache import cache
from django.core.exceptions import ValidationError


def check_rate_limit(key, limit=5, window_seconds=60):
    """
    Fixed-window cache-based rate limiter. Uses cache.add() to atomically
    set the TTL only on first hit -- avoids django-redis's INCR-on-missing-key
    behavior which creates keys with no expiry, silently making limits
    permanent. Raises ValidationError once limit is exceeded within window.
    """
    added = cache.add(key, 1, window_seconds)
    if added:
        current = 1
    else:
        try:
            current = cache.incr(key)
        except ValueError:
            cache.set(key, 1, window_seconds)
            current = 1
    if current > limit:
        raise ValidationError("Too many attempts. Please try again later.")
    return current