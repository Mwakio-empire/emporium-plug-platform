import tempfile
import importlib
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib import admin
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from logistics.models import KenyaCounty, KenyaTown


class KenyaTownModelTests(TestCase):
    def test_normalized_town_name_is_unique_within_county(self):
        county = KenyaCounty.objects.create(code='99', name='Test County')
        KenyaTown.objects.create(county=county, name='  Test   Town  ')

        with self.assertRaises(ValidationError):
            KenyaTown.objects.create(county=county, name='test town')

    def test_database_enforces_normalized_name_uniqueness(self):
        county = KenyaCounty.objects.create(code='99', name='Test County')
        KenyaTown.objects.create(county=county, name='Test Town')

        with self.assertRaises(IntegrityError), transaction.atomic():
            KenyaTown.objects.bulk_create([
                KenyaTown(
                    county=county,
                    name='Different display value',
                    normalized_name='test town',
                ),
            ])

    def test_same_normalized_name_is_allowed_in_different_counties(self):
        first = KenyaCounty.objects.create(code='98', name='First County')
        second = KenyaCounty.objects.create(code='99', name='Second County')

        KenyaTown.objects.create(county=first, name='Border Town')
        KenyaTown.objects.create(county=second, name=' border   town ')

        self.assertEqual(KenyaTown.objects.filter(normalized_name='border town').count(), 2)

    def test_name_is_nfkc_normalized_and_whitespace_is_collapsed(self):
        county = KenyaCounty.objects.create(code='99', name='Test County')

        town = KenyaTown.objects.create(county=county, name='  Ｔｅｓｔ\u00a0  Town  ')

        self.assertEqual(town.name, 'Test Town')
        self.assertEqual(town.normalized_name, 'test town')

    def test_empty_and_control_character_names_are_rejected(self):
        county = KenyaCounty.objects.create(code='99', name='Test County')

        for invalid_name in ('   ', 'Test\nTown', 'Test\x00Town'):
            with self.subTest(name=repr(invalid_name)):
                with self.assertRaises(ValidationError):
                    KenyaTown.objects.create(county=county, name=invalid_name)

    def test_casefolded_normalized_name_must_fit_database_field(self):
        county = KenyaCounty.objects.create(code='99', name='Test County')

        with self.assertRaises(ValidationError):
            KenyaTown.objects.create(county=county, name='ß' * 100)


class KenyaTownSeedDataTests(TestCase):
    def test_reference_data_contains_all_47_active_counties(self):
        self.assertEqual(KenyaCounty.objects.filter(is_active=True).count(), 47)

    def test_every_active_county_has_town_coverage(self):
        self.assertFalse(
            KenyaCounty.objects.filter(is_active=True, towns__isnull=True).exists()
        )

    def test_seeded_towns_record_knbs_revision(self):
        seeded = KenyaTown.objects.filter(
            source='KNBS',
            source_revision='2019-KPHC-URBAN-CENTRES',
        )

        self.assertEqual(seeded.count(), 324)
        self.assertFalse(seeded.filter(is_active=False).exists())

    def test_cross_county_centres_are_available_in_each_reported_county(self):
        thika_counties = set(
            KenyaTown.objects.filter(name='THIKA').values_list('county_id', flat=True)
        )

        self.assertEqual(thika_counties, {'21', '22'})

    def test_single_county_slash_label_is_not_split(self):
        voi_counties = list(
            KenyaTown.objects.filter(name='VOI').values_list('county_id', flat=True)
        )

        self.assertEqual(voi_counties, ['06'])


class KenyaTownSeedMigrationTests(TransactionTestCase):
    migrate_from = [('logistics', '0013_kenyatown')]
    migrate_to = [('logistics', '0014_seed_kenya_towns_2019')]

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.migrate_from)
        old_apps = self.executor.loader.project_state(self.migrate_from).apps
        County = old_apps.get_model('logistics', 'KenyaCounty')
        Town = old_apps.get_model('logistics', 'KenyaTown')
        county_rows = importlib.import_module(
            'logistics.migrations.0011_seed_kenya_counties'
        ).COUNTIES
        for code, name in county_rows:
            County.objects.update_or_create(
                code=code,
                defaults={'name': name, 'is_active': True},
            )
        county = County.objects.get(code='21')
        Town.objects.create(
            county=county,
            name='Client-maintained Thika',
            normalized_name='thika',
            source='CLIENT',
            source_revision='manual-v1',
            is_active=False,
        )

    def tearDown(self):
        MigrationExecutor(connection).migrate(self.migrate_to)
        super().tearDown()

    def test_forward_and_reverse_preserve_preexisting_manual_record(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.migrate_to)
        migrated_apps = self.executor.loader.project_state(self.migrate_to).apps
        Town = migrated_apps.get_model('logistics', 'KenyaTown')

        town = Town.objects.get(county_id='21', normalized_name='thika')
        self.assertEqual(town.name, 'Client-maintained Thika')
        self.assertEqual(town.source, 'CLIENT')
        self.assertEqual(town.source_revision, 'manual-v1')
        self.assertFalse(town.is_active)

        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.migrate_from)
        rolled_back_apps = self.executor.loader.project_state(self.migrate_from).apps
        Town = rolled_back_apps.get_model('logistics', 'KenyaTown')
        self.assertTrue(
            Town.objects.filter(county_id='21', normalized_name='thika').exists()
        )


class TownSelectionServiceTests(TestCase):
    def setUp(self):
        self.kakamega = KenyaCounty.objects.create(code='98', name='Kakamega Test')
        self.kisumu = KenyaCounty.objects.create(code='99', name='Kisumu Test')
        self.kakamega_town = KenyaTown.objects.create(
            county=self.kakamega,
            name='Kakamega',
        )
        self.kisumu_town = KenyaTown.objects.create(
            county=self.kisumu,
            name='Kisumu',
        )

    def resolve(self, **overrides):
        from logistics.location_services import TownSelectionService

        values = {
            'county_code': self.kakamega.code,
            'town_id': self.kakamega_town.pk,
            'use_custom_town': False,
            'custom_town': '',
        }
        values.update(overrides)
        return TownSelectionService.resolve(**values)

    def test_resolver_returns_canonical_selected_names(self):
        selection = self.resolve()

        self.assertEqual(selection.county_name, 'Kakamega Test')
        self.assertEqual(selection.town_name, 'Kakamega')

    def test_free_text_resolver_accepts_county_suffix_and_normalizes_town(self):
        from logistics.location_services import TownSelectionService

        selection = TownSelectionService.resolve_free_text(
            county='  Kakamega Test County  ',
            town='  Shinyalu   Centre  ',
        )

        self.assertEqual(selection.county_name, 'Kakamega Test')
        self.assertEqual(selection.town_name, 'Shinyalu Centre')

    def test_free_text_resolver_rejects_unknown_county(self):
        from logistics.location_services import TownSelectionService

        with self.assertRaisesMessage(ValidationError, "Kenya's 47 counties"):
            TownSelectionService.resolve_free_text(
                county='Imaginary County',
                town='Somewhere',
            )

    def test_resolver_normalizes_explicit_custom_town(self):
        selection = self.resolve(
            town_id=None,
            use_custom_town=True,
            custom_town='  Mumias   East  ',
        )

        self.assertEqual(selection.county_name, 'Kakamega Test')
        self.assertEqual(selection.town_name, 'Mumias East')

    def test_resolver_rejects_nonexistent_or_inactive_county(self):
        for county_code in ('97', self.kakamega.code):
            with self.subTest(county_code=county_code):
                if county_code == self.kakamega.code:
                    self.kakamega.is_active = False
                    self.kakamega.save(update_fields=['is_active'])
                with self.assertRaisesMessage(
                    ValidationError,
                    'Choose an active Kenyan county.',
                ):
                    self.resolve(county_code=county_code)

    def test_resolver_rejects_inactive_town(self):
        self.kakamega_town.is_active = False
        self.kakamega_town.save(update_fields=['is_active'])

        with self.assertRaisesMessage(
            ValidationError,
            'Choose an active town.',
        ):
            self.resolve()

    def test_resolver_rejects_town_from_another_county(self):
        with self.assertRaisesMessage(
            ValidationError,
            'Choose a town belonging to the selected county.',
        ):
            self.resolve(town_id=self.kisumu_town.pk)

    def test_resolver_rejects_ambiguous_selected_and_custom_input(self):
        with self.assertRaisesMessage(
            ValidationError,
            'Choose either a listed town or enter an unlisted town, not both.',
        ):
            self.resolve(use_custom_town=True, custom_town='Mumias')

    def test_resolver_rejects_missing_town_selection(self):
        with self.assertRaisesMessage(
            ValidationError,
            'Choose a town or select the unlisted-town option.',
        ):
            self.resolve(town_id=None)

    def test_resolver_rejects_custom_town_when_fallback_is_not_selected(self):
        with self.assertRaisesMessage(
            ValidationError,
            'Select the unlisted-town option before entering a custom town.',
        ):
            self.resolve(town_id=None, custom_town='Mumias')

    def test_resolver_rejects_overlong_or_control_character_custom_town(self):
        for invalid_name in ('A' * 101, 'Mumias\nTown'):
            with self.subTest(invalid_name=repr(invalid_name)):
                with self.assertRaises(ValidationError):
                    self.resolve(
                        town_id=None,
                        use_custom_town=True,
                        custom_town=invalid_name,
                    )


class TownListAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.first_county = KenyaCounty.objects.create(code='98', name='First Test County')
        self.second_county = KenyaCounty.objects.create(code='99', name='Second Test County')
        self.zulu = KenyaTown.objects.create(county=self.first_county, name='Zulu')
        self.alpha = KenyaTown.objects.create(county=self.first_county, name='Alpha')
        self.inactive = KenyaTown.objects.create(
            county=self.first_county,
            name='Hidden',
            is_active=False,
        )
        self.other = KenyaTown.objects.create(county=self.second_county, name='Other')
        self.url = reverse('logistics:towns')

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def test_anonymous_lookup_returns_only_active_county_towns_in_name_order(self):
        response = self.client.get(self.url, {'county': self.first_county.code})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {'id': self.alpha.pk, 'name': 'Alpha'},
                {'id': self.zulu.pk, 'name': 'Zulu'},
            ],
        )
        self.assertEqual(set(response.json()[0]), {'id', 'name'})

    def test_lookup_rejects_missing_invalid_and_inactive_counties(self):
        inactive_county = KenyaCounty.objects.create(
            code='97',
            name='Inactive Test County',
            is_active=False,
        )
        for query in ({}, {'county': 'not-a-code'}, {'county': inactive_county.code}):
            with self.subTest(query=query):
                response = self.client.get(self.url, query)
                self.assertEqual(response.status_code, 400)
                self.assertIn('county', response.json())

    def test_invalid_county_response_is_not_cached(self):
        response = self.client.get(self.url, {'county': '96'})
        self.assertEqual(response.status_code, 400)

        county = KenyaCounty.objects.create(code='96', name='New Test County')
        town = KenyaTown.objects.create(county=county, name='New Town')
        response = self.client.get(self.url, {'county': county.code})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{'id': town.pk, 'name': 'New Town'}])

    def test_reference_version_change_bypasses_a_previous_successful_cache(self):
        response = self.client.get(self.url, {'county': self.first_county.code})
        self.assertEqual(response.status_code, 200)
        self.alpha.is_active = False
        self.alpha.save(update_fields=['is_active'])

        with self.settings(LOCATION_REFERENCE_DATA_VERSION='test-revision-2'):
            response = self.client.get(self.url, {'county': self.first_county.code})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Alpha', [town['name'] for town in response.json()])

    def test_lookup_uses_only_scoped_location_throttle(self):
        from logistics.views import TownListView

        self.assertEqual(TownListView.permission_classes, [AllowAny])
        self.assertEqual(TownListView.throttle_classes, [ScopedRateThrottle])
        self.assertEqual(TownListView.throttle_scope, 'location_lookup')
        self.assertEqual(
            settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['location_lookup'],
            '120/min',
        )


class KenyaTownImportCommandTests(TestCase):
    def setUp(self):
        cache.clear()
        self.county = KenyaCounty.objects.create(code='98', name='Import County')
        self.other_county = KenyaCounty.objects.create(code='99', name='Other County')
        self.temp_directory = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_directory.cleanup()
        cache.clear()
        super().tearDown()

    def write_csv(self, content, filename='towns.csv'):
        path = Path(self.temp_directory.name) / filename
        path.write_text(content, encoding='utf-8')
        return str(path)

    def import_file(self, content, *, revision='client-2026-08', **options):
        path = self.write_csv(content)
        with self.captureOnCommitCallbacks(execute=True):
            call_command(
                'import_kenya_towns',
                path,
                source_revision=revision,
                **options,
            )

    def test_import_is_idempotent_and_reactivates_matching_town(self):
        content = 'county_code,town\n98,  Mumias   Town  \n'

        self.import_file(content)
        town = KenyaTown.objects.get(county=self.county, normalized_name='mumias town')
        town.is_active = False
        town.save(update_fields=['is_active'])
        self.import_file(content)

        self.assertEqual(
            KenyaTown.objects.filter(county=self.county, normalized_name='mumias town').count(),
            1,
        )
        town.refresh_from_db()
        self.assertTrue(town.is_active)
        self.assertEqual(town.source_revision, 'client-2026-08')

    def test_import_preserves_foreign_source_match_and_creates_safe_new_rows(self):
        protected = KenyaTown.objects.create(
            county=self.county,
            name='  KNBS Display Town  ',
            source='KNBS',
            source_revision='2019-KPHC-URBAN-CENTRES',
            is_active=False,
        )
        original = (
            protected.name,
            protected.normalized_name,
            protected.is_active,
            protected.source,
            protected.source_revision,
        )
        output = StringIO()
        path = self.write_csv(
            'county_code,town\n98,knbs display town\n98,Safe New Town\n'
        )

        with self.captureOnCommitCallbacks(execute=True):
            call_command(
                'import_kenya_towns',
                path,
                source_revision='client-2026-08',
                stdout=output,
            )

        protected.refresh_from_db()
        self.assertEqual(
            (
                protected.name,
                protected.normalized_name,
                protected.is_active,
                protected.source,
                protected.source_revision,
            ),
            original,
        )
        self.assertTrue(
            KenyaTown.objects.filter(
                county=self.county,
                normalized_name='safe new town',
                source='CSV_IMPORT',
                source_revision='client-2026-08',
                is_active=True,
            ).exists()
        )
        self.assertIn('skipped=1', output.getvalue())

    def test_import_rejects_unknown_county_before_any_write(self):
        path = self.write_csv(
            'county_code,town\n98,Valid Town\n97,Unknown County Town\n'
        )

        with self.assertRaises(CommandError):
            call_command('import_kenya_towns', path, source_revision='client-2026-08')

        self.assertFalse(KenyaTown.objects.filter(county=self.county).exists())

    def test_import_rejects_normalized_duplicate_before_any_write(self):
        path = self.write_csv(
            'county_code,town\n98,Test Town\n98,  test   town  \n'
        )

        with self.assertRaises(CommandError):
            call_command('import_kenya_towns', path, source_revision='client-2026-08')

        self.assertFalse(KenyaTown.objects.filter(county=self.county).exists())

    def test_import_requires_exact_headers_and_nonempty_revision(self):
        wrong_headers = self.write_csv('town,county_code\nMumias,98\n')
        valid_file = self.write_csv('county_code,town\n98,Mumias\n', 'valid.csv')

        with self.assertRaises(CommandError):
            call_command(
                'import_kenya_towns',
                wrong_headers,
                source_revision='client-2026-08',
            )
        with self.assertRaises(CommandError):
            call_command('import_kenya_towns', valid_file, source_revision='   ')

        self.assertFalse(KenyaTown.objects.filter(county=self.county).exists())

    def test_deactivate_missing_is_limited_to_supplied_revision(self):
        included = KenyaTown.objects.create(
            county=self.county,
            name='Included',
            source='CSV_IMPORT',
            source_revision='revision-a',
        )
        missing_same_revision = KenyaTown.objects.create(
            county=self.county,
            name='Missing A',
            source='CSV_IMPORT',
            source_revision='revision-a',
        )
        other_revision = KenyaTown.objects.create(
            county=self.county,
            name='Missing B',
            source='CSV_IMPORT',
            source_revision='revision-b',
        )

        self.import_file(
            'county_code,town\n98,Included\n',
            revision='revision-a',
            deactivate_missing=True,
        )

        included.refresh_from_db()
        missing_same_revision.refresh_from_db()
        other_revision.refresh_from_db()
        self.assertTrue(included.is_active)
        self.assertFalse(missing_same_revision.is_active)
        self.assertTrue(other_revision.is_active)

    def test_successful_import_invalidates_affected_county_cache(self):
        existing = KenyaTown.objects.create(county=self.county, name='Existing')
        url = reverse('logistics:towns')
        self.assertEqual(
            self.client.get(url, {'county': self.county.code}).json(),
            [{'id': existing.pk, 'name': 'Existing'}],
        )

        self.import_file('county_code,town\n98,New Town\n')

        names = [
            item['name']
            for item in self.client.get(url, {'county': self.county.code}).json()
        ]
        self.assertEqual(names, ['Existing', 'New Town'])

    def test_cache_failure_does_not_fail_a_committed_import(self):
        path = self.write_csv('county_code,town\n98,Committed Town\n')

        with patch(
            'logistics.management.commands.import_kenya_towns.invalidate_town_list_caches',
            side_effect=RuntimeError('cache unavailable'),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                call_command(
                    'import_kenya_towns',
                    path,
                    source_revision='client-2026-08',
                )

        self.assertTrue(
            KenyaTown.objects.filter(
                county=self.county,
                normalized_name='committed town',
            ).exists()
        )


class KenyaTownAdminTests(TestCase):
    def test_admin_is_searchable_filtered_and_has_no_bulk_delete(self):
        from logistics.admin import KenyaTownAdmin

        model_admin = KenyaTownAdmin(KenyaTown, admin.site)

        self.assertIn('name', model_admin.search_fields)
        self.assertEqual(model_admin.list_select_related, ('county',))
        self.assertIn('county', model_admin.list_filter)
        self.assertIn('source_revision', model_admin.list_filter)
        self.assertIsNone(model_admin.actions)
        self.assertFalse(model_admin.has_delete_permission(None))

    def test_admin_save_invalidates_the_affected_county_cache_after_commit(self):
        from logistics.admin import KenyaTownAdmin

        cache.clear()
        county = KenyaCounty.objects.create(code='98', name='Admin County')
        town = KenyaTown.objects.create(county=county, name='Visible Town')
        url = reverse('logistics:towns')
        self.assertEqual(len(self.client.get(url, {'county': county.code}).json()), 1)

        town.is_active = False
        model_admin = KenyaTownAdmin(KenyaTown, admin.site)
        with self.captureOnCommitCallbacks(execute=True):
            model_admin.save_model(None, town, None, True)

        self.assertEqual(self.client.get(url, {'county': county.code}).json(), [])
