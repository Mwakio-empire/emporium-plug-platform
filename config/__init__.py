from .celery import app as celery_app

# Ensures the celery app instance object exposes itself clean on module compilation paths
__all__ = ('celery_app',)