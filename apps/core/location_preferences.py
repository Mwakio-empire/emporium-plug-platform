import re

from logistics.models import KenyaCounty


SHOPPER_LOCATION_SESSION_KEY = 'shopper_location'


def human_location_label(value):
    """Present uppercase reference names without altering canonical data."""
    lowered = str(value or '').strip().lower()
    return re.sub(
        r'(^|[\s\-/])([a-z])',
        lambda match: f'{match.group(1)}{match.group(2).upper()}',
        lowered,
    )


def active_county_choices():
    return [
        {'code': row['code'], 'name': human_location_label(row['name'])}
        for row in KenyaCounty.objects.filter(is_active=True)
        .order_by('name', 'code')
        .values('code', 'name')
    ]


def shopper_location_context(request):
    saved = request.session.get(SHOPPER_LOCATION_SESSION_KEY)
    if not isinstance(saved, dict):
        saved = {}
    elif saved:
        saved = {
            **saved,
            'county_name': human_location_label(saved.get('county_name')),
            'town_name': human_location_label(saved.get('town_name')),
        }
    return {
        'shopper_location_counties': active_county_choices(),
        'shopper_location': saved,
    }
