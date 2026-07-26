import re

from django.core.exceptions import ValidationError
from django.db.models import Q


E164_PATTERN = re.compile(r'^\+[1-9]\d{7,14}$')


def normalize_phone_number(value):
    """Normalize Kenyan local numbers and accept valid international E.164 numbers."""
    compact = re.sub(r'[\s().-]+', '', str(value or '').strip())
    if re.fullmatch(r'0\d{9}', compact):
        compact = f'+254{compact[1:]}'
    elif re.fullmatch(r'254\d{9}', compact):
        compact = f'+{compact}'
    if not E164_PATTERN.fullmatch(compact):
        raise ValidationError('Enter a valid phone number, for example +2547XXXXXXXX.')
    return compact


def phone_aliases(value):
    """Return equivalent stored forms while legacy local-format rows are being cleaned."""
    normalized = normalize_phone_number(value)
    aliases = {normalized}
    if normalized.startswith('+254') and len(normalized) == 13:
        aliases.add(f'0{normalized[4:]}')
        aliases.add(normalized[1:])
    return aliases


def phone_lookup(value):
    return Q(phone_number__in=phone_aliases(value))


def resolve_user_identifier(user_model, value):
    """Prefer an exact legacy match, then try normalized phone aliases."""
    identifier = str(value or '').strip()
    exact = user_model.objects.filter(
        Q(phone_number=identifier) | Q(email__iexact=identifier) | Q(username=identifier)
    ).order_by('id').first()
    if exact is not None:
        return exact
    try:
        return user_model.objects.filter(phone_lookup(identifier)).order_by('id').first()
    except ValidationError:
        return None
