# config/settings.py

from pathlib import Path
import environ
import os
import sys
from datetime import timedelta
from django.core.exceptions import ImproperlyConfigured
from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent

sys.path.insert(0, os.path.join(BASE_DIR, 'apps'))

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

IS_TESTING = 'test' in sys.argv or any('test' in arg for arg in sys.argv)
ENVIRONMENT = env('ENVIRONMENT', default='test' if IS_TESTING else 'development').strip().lower()
if ENVIRONMENT not in {'development', 'test', 'staging', 'production'}:
    raise ImproperlyConfigured('ENVIRONMENT must be development, test, staging or production.')
IS_STAGING = ENVIRONMENT == 'staging'
IS_PRODUCTION = ENVIRONMENT == 'production'
IS_DEPLOYED_ENVIRONMENT = IS_STAGING or IS_PRODUCTION

SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = [host.strip() for host in env('ALLOWED_HOSTS').split(',') if host.strip()]
if IS_DEPLOYED_ENVIRONMENT and DEBUG:
    raise ImproperlyConfigured('DEBUG must be false in staging and production.')
if not DEBUG:
    if len(SECRET_KEY) < 50 or SECRET_KEY.startswith('django-insecure-'):
        raise ImproperlyConfigured('Production SECRET_KEY must be random and at least 50 characters.')
    if not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS:
        raise ImproperlyConfigured('Production ALLOWED_HOSTS must contain explicit hostnames.')

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'cloudinary',
]

THIRD_PARTY_APPS = [
    'storages',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'django_filters',
]

LOCAL_APPS = [
    'branches.apps.BranchesConfig',
    'users.apps.UsersConfig',
    'catalog.apps.CatalogConfig',
    'inventory.apps.InventoryConfig',
    'orders.apps.OrdersConfig',
    'payments.apps.PaymentsConfig',
    'notifications.apps.NotificationsConfig',
    'logistics.apps.LogisticsConfig',
    'analytics.apps.AnalyticsConfig',
    'reports.apps.ReportsConfig',
    'marketing.apps.MarketingConfig',
    'core.apps.CoreConfig',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'core.logging.RequestIDMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.csp.ContentSecurityPolicyMiddleware',
    'core.middleware.SecurityResponseHeadersMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.csp',
                'core.context_processors.business_contact',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': env.db('DATABASE_URL')
}

if IS_DEPLOYED_ENVIRONMENT and 'postgresql' not in DATABASES['default']['ENGINE']:
    raise ImproperlyConfigured('Staging and production require PostgreSQL.')

DATABASES['default']['CONN_MAX_AGE'] = env.int('DATABASE_CONN_MAX_AGE', default=600)

AUTH_USER_MODEL = 'users.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
AUTHENTICATION_BACKENDS = [
    'users.backends.PhoneOrEmailBackend',
    'django.contrib.auth.backends.ModelBackend',
]
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ----------------------------------------------------------------------
# STATIC & MEDIA FILES
# ----------------------------------------------------------------------
STATIC_URL = 'static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# ----------------------------------------------------------------------
# CLOUDINARY
# ----------------------------------------------------------------------
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': env('CLOUDINARY_CLOUD_NAME', default='sandbox_cloud'),
    'API_KEY': env('CLOUDINARY_API_KEY', default=''),
    'API_SECRET': env('CLOUDINARY_API_SECRET', default=''),
}

# ----------------------------------------------------------------------
# STORAGE BACKENDS (AWS S3 or local fallback)
# ----------------------------------------------------------------------
USE_AWS_S3 = env.bool('USE_AWS_S3', default=False)

if USE_AWS_S3:
    AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME', default='eu-west-1')
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
            "OPTIONS": {"location": "media"},
        },
        "staticfiles": {
            "BACKEND": "storages.backends.s3boto3.S3StaticStorage",
            "OPTIONS": {"location": "static"},
        },
    }
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }

# django-cloudinary-storage 0.3.0 still inspects this legacy alias from its
# collectstatic command. STORAGES above remains Django's source of truth.
STATICFILES_STORAGE = STORAGES['staticfiles']['BACKEND']

# ----------------------------------------------------------------------
# REDIS CACHE — single definition, production-grade
# ----------------------------------------------------------------------
REDIS_URL = env('REDIS_URL', default='').strip()
LOCAL_CACHE_ONLY = env.bool('LOCAL_CACHE_ONLY', default=False)
if LOCAL_CACHE_ONLY and not (DEBUG or IS_TESTING):
    raise ImproperlyConfigured('LOCAL_CACHE_ONLY is restricted to development and tests.')
if REDIS_URL and not LOCAL_CACHE_ONLY:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'CONNECTION_POOL_KWARGS': {
                    'max_connections': 100,
                    'retry_on_timeout': True,
                },
                'SOCKET_TIMEOUT': 5,
                'SOCKET_CONNECT_TIMEOUT': 5,
            }
        }
    }
elif DEBUG or IS_TESTING:
    CACHES = {
        'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
    }
else:
    raise ImproperlyConfigured('REDIS_URL is required when DEBUG is false.')

# Cache TTL constants
CACHE_TTL_CATALOG = 3600         # 1 hour — product/category lookups
CACHE_TTL_STATIC_DATA = 86400    # 24 hours — branches, locations
CACHE_TTL_STOREFRONT = 60 * 15   # 15 minutes — hot catalog pathways
CACHE_TTL_PROMOTIONS = 60 * 30   # 30 minutes — coupon/flash sale validations

# ----------------------------------------------------------------------
# CELERY
# ----------------------------------------------------------------------
CELERY_BROKER_URL = REDIS_URL if REDIS_URL and not LOCAL_CACHE_ONLY else 'memory://'
CELERY_RESULT_BACKEND = REDIS_URL if REDIS_URL and not LOCAL_CACHE_ONLY else 'cache+memory://'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 15 * 60
CELERY_WORKER_PREFETCH_MULTIPLIER = 1


SITE_BASE_URL = env('SITE_BASE_URL', default='https://example.com')
PICKUP_RESERVATION_WORKING_DAYS = env.int('PICKUP_RESERVATION_WORKING_DAYS', default=2)
RETURN_REQUEST_WINDOW_DAYS = env.int('RETURN_REQUEST_WINDOW_DAYS', default=7)
PRIVACY_CONTROLLER_NAME = env('PRIVACY_CONTROLLER_NAME', default='').strip()
PRIVACY_CONTACT_EMAIL = env('PRIVACY_CONTACT_EMAIL', default='').strip()
PRIVACY_NOTICE_APPROVED = env.bool('PRIVACY_NOTICE_APPROVED', default=False)
if IS_PRODUCTION and not IS_TESTING:
    if not PRIVACY_CONTROLLER_NAME or not PRIVACY_CONTACT_EMAIL:
        raise ImproperlyConfigured(
            'Production requires the approved controller name and privacy contact.'
        )
    if not PRIVACY_NOTICE_APPROVED:
        raise ImproperlyConfigured(
            'Production requires an approved privacy notice before customer data is collected.'
        )

# Outbound customer contact is suppressed by default. Production must opt into
# a configured provider explicitly rather than contacting real numbers by accident.
NOTIFICATION_PROVIDER = env('NOTIFICATION_PROVIDER', default='console')
AFRICASTALKING_USERNAME = env('AFRICASTALKING_USERNAME', default='sandbox')
AFRICASTALKING_API_KEY = env('AFRICASTALKING_API_KEY', default='')
AFRICASTALKING_SENDER_ID = env('AFRICASTALKING_SENDER_ID', default='')
WHATSAPP_FALLBACK_ENABLED = env.bool('WHATSAPP_FALLBACK_ENABLED', default=False)
WHATSAPP_API_URL = env('WHATSAPP_API_URL', default='')
WHATSAPP_BEARER_TOKEN = env('WHATSAPP_BEARER_TOKEN', default='')
INBOUND_SMS_ENABLED = env.bool('INBOUND_SMS_ENABLED', default=False)
INBOUND_SMS_WEBHOOK_TOKEN = env('INBOUND_SMS_WEBHOOK_TOKEN', default='').strip()
if INBOUND_SMS_ENABLED and len(INBOUND_SMS_WEBHOOK_TOKEN) < 32:
    raise ImproperlyConfigured(
        'INBOUND_SMS_WEBHOOK_TOKEN must contain at least 32 characters when inbound SMS is enabled.'
    )
if IS_PRODUCTION and not IS_TESTING and NOTIFICATION_PROVIDER == 'console':
    raise ImproperlyConfigured('Production must configure an outbound notification provider.')
WHATSAPP_ORDER_PHONE = env(
    'WHATSAPP_ORDER_PHONE', default='+254116153335',
).strip()

# Optional off-site logical backups supplement, but never replace, managed
# PostgreSQL point-in-time recovery. A bucket lifecycle owns retention.
BACKUP_ENABLED = env.bool('BACKUP_ENABLED', default=False)
BACKUP_S3_BUCKET = env('BACKUP_S3_BUCKET', default='').strip()
BACKUP_S3_PREFIX = env('BACKUP_S3_PREFIX', default='emporium-plug/database').strip()
BACKUP_S3_REGION = env('BACKUP_S3_REGION', default='eu-west-1').strip()
BACKUP_S3_KMS_KEY_ID = env('BACKUP_S3_KMS_KEY_ID', default='').strip()
PG_DUMP_BINARY = env('PG_DUMP_BINARY', default='pg_dump').strip()
BACKUP_COMMAND_TIMEOUT_SECONDS = env.int('BACKUP_COMMAND_TIMEOUT_SECONDS', default=1800)
if BACKUP_ENABLED and not BACKUP_S3_BUCKET:
    raise ImproperlyConfigured('BACKUP_S3_BUCKET is required when BACKUP_ENABLED is true.')

# ----------------------------------------------------------------------
# SENTRY — guarded so it doesn't crash when DSN is empty in development
# ----------------------------------------------------------------------
SENTRY_DSN = env('SENTRY_DSN', default='')

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=env.float('SENTRY_TRACES_SAMPLE_RATE', default=0.1),
        profiles_sample_rate=env.float('SENTRY_PROFILES_SAMPLE_RATE', default=0.1),
        send_default_pii=env.bool('SENTRY_SEND_DEFAULT_PII', default=False),
    )

# ----------------------------------------------------------------------
# SECURITY HEADERS (production only)
# ----------------------------------------------------------------------
if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=3600)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
        'SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False,
    )
    SECURE_HSTS_PRELOAD = env.bool('SECURE_HSTS_PRELOAD', default=False)
    CSRF_TRUSTED_ORIGINS = [
        origin.strip() for origin in env('CSRF_TRUSTED_ORIGINS', default='').split(',')
        if origin.strip()
    ]
    if not CSRF_TRUSTED_ORIGINS or any(
        not origin.startswith('https://') for origin in CSRF_TRUSTED_ORIGINS
    ):
        raise ImproperlyConfigured(
            'Production/staging requires explicit HTTPS CSRF_TRUSTED_ORIGINS.'
        )
    if not SITE_BASE_URL.startswith('https://'):
        raise ImproperlyConfigured('SITE_BASE_URL must use HTTPS when DEBUG is false.')
    if env.bool('TRUST_PROXY_HEADERS', default=False):
        SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
else:
    X_FRAME_OPTIONS = 'SAMEORIGIN'

SECURE_CSP = {
    'default-src': [CSP.SELF],
    'base-uri': [CSP.SELF],
    'object-src': [CSP.NONE],
    'frame-ancestors': [CSP.NONE],
    'form-action': [CSP.SELF],
    'script-src': [CSP.SELF, CSP.NONCE, 'https://cdn.jsdelivr.net'],
    'style-src': [CSP.SELF],
    'img-src': [CSP.SELF, 'data:', 'https:'],
    'font-src': [CSP.SELF, 'data:'],
    'connect-src': [CSP.SELF],
}
if not DEBUG and not IS_TESTING and not all(CLOUDINARY_STORAGE.values()):
    raise ImproperlyConfigured(
        'Production/staging requires Cloudinary credentials for persistent catalog images.'
    )

# ----------------------------------------------------------------------
# TEST OVERRIDES — use fast in-memory cache during test runs
# ----------------------------------------------------------------------
if IS_TESTING:
    STORAGES['staticfiles'] = {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    }
    STATICFILES_STORAGE = STORAGES['staticfiles']['BACKEND']
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }
    # Password strength is a production concern; tests need deterministic,
    # fast hashing so the complete suite remains practical in CI.
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
    # Tests must never depend on a running Redis service or enqueue work for
    # an external worker. Tests that assert task behaviour call or mock the
    # task explicitly; incidental `.delay()` calls remain in memory.
    CELERY_BROKER_URL = 'memory://'
    CELERY_RESULT_BACKEND = 'cache+memory://'
    CELERY_TASK_ALWAYS_EAGER = False


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'users.jwt.VersionedJWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 24,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '2000/hour',
        'login': '20/hour',
        'signup': '10/hour',
        'otp': '30/hour',
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'request_id': {'()': 'core.logging.RequestIDFilter'},
    },
    'formatters': {
        'json': {'()': 'core.logging.JsonFormatter'},
        'plain': {'format': '%(levelname)s %(name)s %(message)s'},
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'filters': ['request_id'],
            'formatter': 'plain' if DEBUG or IS_TESTING else 'json',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING' if IS_TESTING else 'INFO',
    },
}

# Explicit browser-session protections. Secure flags are enabled below in
# production; HttpOnly and SameSite remain safe in every environment.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 12 * 60 * 60
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_REFERRER_POLICY = 'same-origin'

# There is intentionally no impersonation route or middleware in Phase 2.
# Re-enable only with re-authentication, a persistent banner and audit coverage.
IMPERSONATION_ENABLED = False
