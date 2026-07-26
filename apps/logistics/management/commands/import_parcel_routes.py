import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from analytics.models import AuditLog
from analytics.services import AuditTrackingService
from logistics.models import KenyaCounty, ParcelDestination
from users.models import User


REQUIRED_COLUMNS = {
    'county_code', 'town', 'collection_point', 'operator_name',
    'nairobi_dispatch_point', 'fee', 'included_weight_kg',
    'additional_kg_fee', 'estimated_days_min', 'estimated_days_max',
    'effective_from', 'effective_until', 'collection_instructions', 'is_active',
}


def parse_bool(value):
    normalized = str(value).strip().lower()
    if normalized in {'1', 'true', 'yes'}:
        return True
    if normalized in {'0', 'false', 'no'}:
        return False
    raise ValueError('must be true/false, yes/no or 1/0')


class Command(BaseCommand):
    help = 'Validate and import client-approved parcel destinations and rates from CSV.'

    def add_arguments(self, parser):
        parser.add_argument('csv_path')
        parser.add_argument('--dry-run', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(options['csv_path']).resolve()
        if not path.is_file():
            raise CommandError(f'CSV file does not exist: {path}')

        errors = []
        prepared = []
        with path.open('r', encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise CommandError(f'Missing CSV columns: {", ".join(sorted(missing))}')
            for line_number, row in enumerate(reader, start=2):
                try:
                    county = KenyaCounty.objects.get(code=str(row['county_code']).strip().zfill(2))
                    effective_until = (
                        date.fromisoformat(row['effective_until'].strip())
                        if row['effective_until'].strip() else None
                    )
                    values = {
                        'county': county,
                        'town': row['town'].strip(),
                        'collection_point': row['collection_point'].strip(),
                        'operator_name': row['operator_name'].strip(),
                        'nairobi_dispatch_point': row['nairobi_dispatch_point'].strip(),
                        'fee': Decimal(row['fee'].strip()),
                        'included_weight_kg': Decimal(row['included_weight_kg'].strip()),
                        'additional_kg_fee': Decimal(row['additional_kg_fee'].strip()),
                        'estimated_days_min': int(row['estimated_days_min']),
                        'estimated_days_max': int(row['estimated_days_max']),
                        'effective_from': date.fromisoformat(row['effective_from'].strip()),
                        'effective_until': effective_until,
                        'collection_instructions': row['collection_instructions'].strip(),
                        'is_active': parse_bool(row['is_active']),
                    }
                    candidate = ParcelDestination(**values)
                    candidate.full_clean(validate_unique=False)
                    prepared.append(values)
                except (KenyaCounty.DoesNotExist, ValueError, InvalidOperation, ValidationError) as exc:
                    errors.append(f'line {line_number}: {exc}')

        if errors:
            raise CommandError('Route import rejected:\n' + '\n'.join(errors))

        changed = 0
        for values in prepared:
            keys = {
                'county': values.pop('county'),
                'town': values.pop('town'),
                'collection_point': values.pop('collection_point'),
                'operator_name': values.pop('operator_name'),
            }
            _, created = ParcelDestination.objects.update_or_create(**keys, defaults=values)
            changed += 1
            self.stdout.write(f'{"created" if created else "updated"}: {keys["town"]} / {keys["collection_point"]}')

        if options['dry_run']:
            transaction.set_rollback(True)
            self.stdout.write(self.style.WARNING(f'Dry run validated {changed} route(s); no changes saved.'))
            return

        AuditTrackingService.log_action(
            User.get_system_account(), AuditLog.ActionTypes.PARCEL_ROUTE_CHANGE,
            f'parcel_route_csv_import={path.name}; routes_changed={changed}',
        )
        self.stdout.write(self.style.SUCCESS(f'Imported {changed} parcel route(s).'))
