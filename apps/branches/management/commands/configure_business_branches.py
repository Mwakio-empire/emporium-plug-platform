from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from branches.models import Branch


S18_NAME = 'Gaberone Plaza S18'
B03_NAME = 'Gaberone Plaza B03'
OTC_NAME = 'OTC Mall'
OTC_LOCATION = 'Third floor, OTC Mall, Nairobi'
S18_LOCATION = 'Second floor, Shop S18, Gaberone Plaza, Gaberone Road, Nairobi'
B03_LOCATION = 'Fifth floor, Shop B03, Gaberone Plaza, Gaberone Road, Nairobi'
PLACEHOLDER_VALUES = {'tbd', 'todo', 'test', 'unknown', 'placeholder', 'n/a'}


class Command(BaseCommand):
    help = (
        'Create or update the three client-approved branches without inventing '
        'addresses or deleting existing records.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--otc-name', default=OTC_NAME)
        parser.add_argument('--otc-location', default=OTC_LOCATION)
        parser.add_argument('--s18-location', default=S18_LOCATION)
        parser.add_argument('--b03-location', default=B03_LOCATION)
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Validate and display the resulting topology, then roll it back.',
        )

    @staticmethod
    def _approved_text(value, label):
        normalized = str(value or '').strip()
        if not normalized:
            raise CommandError(f'{label} cannot be blank.')
        if normalized.casefold() in PLACEHOLDER_VALUES:
            raise CommandError(f'{label} cannot be a placeholder value.')
        return normalized

    def handle(self, *args, **options):
        otc_name = self._approved_text(options['otc_name'], 'OTC branch name')
        locations = {
            otc_name: self._approved_text(options['otc_location'], 'OTC location'),
            S18_NAME: self._approved_text(options['s18_location'], 'S18 location'),
            B03_NAME: self._approved_text(options['b03_location'], 'B03 location'),
        }
        if len(locations) != 3:
            raise CommandError('OTC, S18 and B03 must have three distinct branch names.')

        unexpected = list(
            Branch.objects.filter(is_active=True)
            .exclude(name__in=locations)
            .values_list('name', flat=True)
        )
        if unexpected:
            names = ', '.join(sorted(unexpected))
            raise CommandError(
                'Unexpected active branch records exist: '
                f'{names}. Review and deactivate or rename them explicitly before '
                'configuring production branches.'
            )

        desired = {
            otc_name: {
                'location': locations[otc_name],
                'is_active': True,
                'receives_supplier_stock': True,
                'offers_customer_pickup': False,
            },
            S18_NAME: {
                'location': locations[S18_NAME],
                'is_active': True,
                'receives_supplier_stock': False,
                'offers_customer_pickup': True,
            },
            B03_NAME: {
                'location': locations[B03_NAME],
                'is_active': True,
                'receives_supplier_stock': False,
                'offers_customer_pickup': False,
            },
        }

        with transaction.atomic():
            configured = []
            for name, values in desired.items():
                branch, created = Branch.objects.update_or_create(
                    name=name,
                    defaults=values,
                )
                configured.append((branch, created))

            receiving_hubs = Branch.objects.filter(
                is_active=True,
                receives_supplier_stock=True,
            ).count()
            pickup_branches = Branch.objects.filter(
                is_active=True,
                offers_customer_pickup=True,
            ).count()
            if receiving_hubs != 1 or pickup_branches != 1:
                raise CommandError(
                    'Configuration must result in exactly one supplier receiving hub '
                    'and exactly one customer pickup branch.'
                )

            for branch, created in configured:
                action = 'create' if created else 'update'
                self.stdout.write(
                    f'{action}: {branch.name} | {branch.location} | '
                    f'supplier_intake={branch.receives_supplier_stock} | '
                    f'customer_pickup={branch.offers_customer_pickup}'
                )

            if options['dry_run']:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING('Dry run: no branch changes saved.'))
            else:
                self.stdout.write(self.style.SUCCESS('Three-branch topology configured.'))
