import csv
from dataclasses import dataclass
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from logistics.location_services import invalidate_town_list_caches
from logistics.models import KenyaCounty, KenyaTown


@dataclass(frozen=True, slots=True)
class ValidatedTownRow:
    county_code: str
    name: str
    normalized_name: str


class Command(BaseCommand):
    help = 'Import a validated county/town CSV reference revision.'

    def add_arguments(self, parser):
        parser.add_argument('csv_path')
        parser.add_argument('--source-revision', required=True)
        parser.add_argument('--deactivate-missing', action='store_true')

    def handle(self, *args, **options):
        revision = str(options['source_revision'] or '').strip()
        if not revision:
            raise CommandError('--source-revision must not be empty.')
        if len(revision) > KenyaTown._meta.get_field('source_revision').max_length:
            raise CommandError('--source-revision is too long.')

        rows = self._read_and_validate(Path(options['csv_path']))
        affected_counties = {row.county_code for row in rows}
        created_count = 0
        updated_count = 0
        unchanged_count = 0
        skipped_count = 0
        deactivated_count = 0

        with transaction.atomic():
            for row in rows:
                town = KenyaTown.objects.filter(
                    county_id=row.county_code,
                    normalized_name=row.normalized_name,
                ).first()
                if town is None:
                    KenyaTown.objects.create(
                        county_id=row.county_code,
                        name=row.name,
                        source='CSV_IMPORT',
                        source_revision=revision,
                        is_active=True,
                    )
                    created_count += 1
                elif town.source != 'CSV_IMPORT':
                    # A normalized match owned by KNBS or a manual process has
                    # separate provenance. The import must never relabel,
                    # reactivate or otherwise take ownership of that record.
                    skipped_count += 1
                else:
                    changed = (
                        town.name != row.name
                        or not town.is_active
                        or town.source != 'CSV_IMPORT'
                        or town.source_revision != revision
                    )
                    town.name = row.name
                    town.is_active = True
                    town.source = 'CSV_IMPORT'
                    town.source_revision = revision
                    if changed:
                        town.save()
                        updated_count += 1
                    else:
                        unchanged_count += 1

            if options['deactivate_missing']:
                supplied = {
                    (row.county_code, row.normalized_name)
                    for row in rows
                }
                candidates = KenyaTown.objects.filter(
                    source='CSV_IMPORT',
                    source_revision=revision,
                    is_active=True,
                )
                deactivate_ids = [
                    town.pk
                    for town in candidates.only('pk', 'county_id', 'normalized_name')
                    if (town.county_id, town.normalized_name) not in supplied
                ]
                if deactivate_ids:
                    affected_counties.update(
                        KenyaTown.objects.filter(pk__in=deactivate_ids)
                        .values_list('county_id', flat=True)
                    )
                    deactivated_count = KenyaTown.objects.filter(
                        pk__in=deactivate_ids
                    ).update(is_active=False)

            transaction.on_commit(
                lambda codes=frozenset(affected_counties):
                    invalidate_town_list_caches(codes),
                robust=True,
            )

        self.stdout.write(self.style.SUCCESS(
            'Town import completed: '
            f'rows={len(rows)}, created={created_count}, updated={updated_count}, '
            f'unchanged={unchanged_count}, skipped={skipped_count}, '
            f'deactivated={deactivated_count}, counties={len(affected_counties)}.'
        ))

    def _read_and_validate(self, path: Path) -> list[ValidatedTownRow]:
        try:
            source_file = path.open('r', encoding='utf-8', newline='')
        except (OSError, UnicodeError) as exc:
            raise CommandError('The CSV file could not be opened as UTF-8.') from exc

        try:
            with source_file:
                reader = csv.DictReader(source_file)
                if reader.fieldnames != ['county_code', 'town']:
                    raise CommandError(
                        'CSV headers must be exactly: county_code,town.'
                    )
                raw_rows = list(reader)
        except UnicodeError as exc:
            raise CommandError('The CSV file is not valid UTF-8.') from exc

        if not raw_rows:
            raise CommandError('CSV must contain at least one town row.')

        county_codes = {
            str(row.get('county_code') or '').strip()
            for row in raw_rows
        }
        known_counties = set(
            KenyaCounty.objects.filter(code__in=county_codes)
            .values_list('code', flat=True)
        )
        if county_codes - known_counties:
            raise CommandError('CSV contains one or more unknown county codes.')

        validated = []
        seen = set()
        for row_number, row in enumerate(raw_rows, start=2):
            if None in row:
                raise CommandError(f'Row {row_number} has unexpected columns.')
            county_code = str(row.get('county_code') or '').strip()
            try:
                name = KenyaTown.normalize_name(row.get('town'))
            except ValidationError as exc:
                raise CommandError(f'Row {row_number} has an invalid town name.') from exc
            if not name:
                raise CommandError(f'Row {row_number} has an empty town name.')
            normalized_name = name.casefold()
            if (
                len(name) > KenyaTown._meta.get_field('name').max_length
                or len(normalized_name)
                > KenyaTown._meta.get_field('normalized_name').max_length
            ):
                raise CommandError(f'Row {row_number} has a town name that is too long.')
            identity = (county_code, normalized_name)
            if identity in seen:
                raise CommandError('CSV contains a normalized duplicate town.')
            seen.add(identity)
            validated.append(ValidatedTownRow(county_code, name, normalized_name))
        return validated
