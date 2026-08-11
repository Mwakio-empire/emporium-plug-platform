import re


def human_location_label(value):
    """Present uppercase reference names without altering canonical data."""
    lowered = str(value or '').strip().lower()
    return re.sub(
        r'(^|[\s\-/])([a-z])',
        lambda match: f'{match.group(1)}{match.group(2).upper()}',
        lowered,
    )
