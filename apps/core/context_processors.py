from urllib.parse import quote

from django.conf import settings
from django.templatetags.static import static


def build_whatsapp_url(message):
    phone = str(getattr(settings, 'WHATSAPP_ORDER_PHONE', '') or '').strip()
    digits = ''.join(character for character in phone if character.isdigit())
    return f'https://wa.me/{digits}?text={quote(message)}' if digits else ''


def business_contact(request):
    message = (
        'Hello Emporium Plug, I would like help placing an order. '
        'Please confirm availability and the final payable amount.'
    )
    store_logo_url = request.build_absolute_uri(static('branding/emporium-plug-original.png'))
    store_schema = {
        '@context': 'https://schema.org',
        '@type': 'OnlineStore',
        '@id': f"{request.build_absolute_uri('/')}#store",
        'name': 'Emporium Plug',
        'url': request.build_absolute_uri('/'),
        'logo': store_logo_url,
        'description': (
            'Nairobi wholesale and retail store offering S18 pickup and '
            'assisted parcel arrangements to Kenyan towns.'
        ),
        'areaServed': {'@type': 'Country', 'name': 'Kenya'},
        'contactPoint': {
            '@type': 'ContactPoint',
            'telephone': '+254116153335',
            'contactType': 'customer service',
            'areaServed': 'KE',
            'availableLanguage': ['English', 'Swahili'],
        },
    }
    organization_schema = {
        '@context': 'https://schema.org',
        '@graph': [
            store_schema,
            {
                '@type': 'WebSite',
                '@id': f"{request.build_absolute_uri('/')}#website",
                'name': 'Emporium Plug',
                'url': request.build_absolute_uri('/'),
                'publisher': {'@id': f"{request.build_absolute_uri('/')}#store"},
                'potentialAction': {
                    '@type': 'SearchAction',
                    'target': f"{request.build_absolute_uri('/')}?search={{search_term_string}}",
                    'query-input': 'required name=search_term_string',
                },
            },
        ],
    }
    return {
        'business_contact_numbers': ('0739 150 246', '0116 153 335', '0783 025 355'),
        'whatsapp_order_url': build_whatsapp_url(message),
        'organization_schema': organization_schema,
        'store_logo_url': store_logo_url,
    }
