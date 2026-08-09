from django.conf import settings
from django.core import signing

from .models import DeliveryQuoteRequest


TOKEN_SALT = 'orders.delivery-quote-access.v1'


def issue_delivery_quote_token(quote: DeliveryQuoteRequest) -> str:
    return signing.dumps(
        {'quote_id': quote.pk, 'reference': quote.reference},
        salt=TOKEN_SALT,
        compress=True,
    )


def resolve_delivery_quote_token(token: str):
    if not token:
        return None
    try:
        payload = signing.loads(
            token,
            salt=TOKEN_SALT,
            max_age=getattr(settings, 'DELIVERY_QUOTE_ACCESS_MAX_AGE', 60 * 60 * 24 * 7),
        )
    except signing.BadSignature:
        return None
    return DeliveryQuoteRequest.objects.filter(
        pk=payload.get('quote_id'), reference=payload.get('reference'),
    ).first()
