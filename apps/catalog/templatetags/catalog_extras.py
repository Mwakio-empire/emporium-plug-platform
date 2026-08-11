import json

from django import template
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.safestring import mark_safe

from catalog.stock_presentation import public_stock_status


register = template.Library()


@register.filter
def storefront_stock_status(product):
    """Return the privacy-safe public stock state for an annotated product."""
    return public_stock_status(
        getattr(product, 'available_stock', 0),
        getattr(product, 'low_stock_threshold', 0),
    )


@register.filter
def storefront_image_url(image, width=640):
    """Return a right-sized Cloudinary URL while leaving other storage URLs intact."""
    if not image:
        return ''
    try:
        url = image.url
    except (AttributeError, ValueError):
        return ''
    try:
        width = max(96, min(int(width), 1600))
    except (TypeError, ValueError):
        width = 640
    marker = '/image/upload/'
    if 'res.cloudinary.com/' not in url or marker not in url:
        return url
    url = url.replace('http://res.cloudinary.com/', 'https://res.cloudinary.com/', 1)
    transform = f'f_auto,q_auto,c_fill,g_auto,w_{width},h_{width}/'
    return url.replace(marker, f'{marker}{transform}', 1)


@register.filter
def json_ld(value):
    """Serialize JSON-LD while preventing a value from closing the script element."""
    encoded = json.dumps(value, cls=DjangoJSONEncoder, separators=(',', ':'))
    encoded = (
        encoded.replace('&', '\\u0026')
        .replace('<', '\\u003c')
        .replace('>', '\\u003e')
        .replace('\u2028', '\\u2028')
        .replace('\u2029', '\\u2029')
    )
    # JSON must remain unescaped by Django inside application/ld+json. The
    # replacements above prevent script termination; test_json_ld.py covers an
    # adversarial closing-script payload.
    return mark_safe(encoded)  # nosec B308 B703
