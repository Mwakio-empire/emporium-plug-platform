from dataclasses import dataclass
import hashlib

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError

from .models import KenyaCounty, KenyaTown


def town_list_cache_key(county_code: str) -> str:
    """Return the current-version public town-list cache key for a county."""
    reference_version = str(
        getattr(settings, 'LOCATION_REFERENCE_DATA_VERSION', 'v1')
    )
    version_hash = hashlib.sha256(reference_version.encode('utf-8')).hexdigest()[:12]
    return f'location:towns:{version_hash}:{county_code}'


def invalidate_town_list_caches(county_codes) -> None:
    """Invalidate only the affected counties in the current reference version."""
    keys = {
        town_list_cache_key(str(code).strip())
        for code in county_codes
        if str(code).strip()
    }
    if keys:
        cache.delete_many(keys)


@dataclass(frozen=True, slots=True)
class ResolvedTownSelection:
    """Canonical destination names safe to snapshot on a quote."""

    county_name: str
    town_name: str


class TownSelectionService:
    """Resolve a listed or explicitly custom town against active reference data."""

    @staticmethod
    def resolve(
        *,
        county_code: str,
        town_id: int | None,
        use_custom_town: bool,
        custom_town: str,
    ) -> ResolvedTownSelection:
        code = str(county_code or '').strip()
        try:
            county = KenyaCounty.objects.get(code=code, is_active=True)
        except KenyaCounty.DoesNotExist as exc:
            raise ValidationError('Choose an active Kenyan county.') from exc

        has_selected_town = town_id not in (None, '')
        raw_custom_town = str(custom_town or '')
        has_custom_text = bool(raw_custom_town.strip())

        if use_custom_town and has_selected_town:
            raise ValidationError(
                'Choose either a listed town or enter an unlisted town, not both.'
            )

        if use_custom_town:
            if not has_custom_text:
                raise ValidationError('Enter the unlisted town name.')
            town_name = KenyaTown.normalize_name(raw_custom_town)
            if len(town_name) > KenyaTown._meta.get_field('name').max_length:
                raise ValidationError('Town name must be 100 characters or fewer.')
            return ResolvedTownSelection(
                county_name=county.name,
                town_name=town_name,
            )

        if has_custom_text:
            raise ValidationError(
                'Select the unlisted-town option before entering a custom town.'
            )
        if not has_selected_town:
            raise ValidationError('Choose a town or select the unlisted-town option.')

        try:
            selected_town = KenyaTown.objects.get(pk=town_id)
        except (KenyaTown.DoesNotExist, TypeError, ValueError) as exc:
            raise ValidationError('Choose an active town.') from exc
        if not selected_town.is_active:
            raise ValidationError('Choose an active town.')
        if selected_town.county_id != county.pk:
            raise ValidationError('Choose a town belonging to the selected county.')

        return ResolvedTownSelection(
            county_name=county.name,
            town_name=selected_town.name,
        )
