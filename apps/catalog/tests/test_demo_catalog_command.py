from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class SeedDemoCatalogCommandTests(SimpleTestCase):
    @override_settings(IS_PRODUCTION=True)
    def test_command_is_blocked_before_any_production_data_mutation(self):
        with self.assertRaisesMessage(
            CommandError,
            'Demo catalogue data is blocked in production.',
        ):
            call_command('seed_demo_catalog', skip_images=True)
