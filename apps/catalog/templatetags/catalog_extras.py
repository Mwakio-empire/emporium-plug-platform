import json

from django import template
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.safestring import mark_safe


register = template.Library()


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
