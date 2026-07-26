from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from branches.models import Branch


class BranchListTests(TestCase):

    def test_lists_only_active_branches(self):
        active = Branch.objects.create(name='Nakuru', location='Nakuru CBD')
        Branch.objects.create(name='Closed', location='Former location', is_active=False)

        response = self.client.get(reverse('branches:branch_list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'branches': [{
                'id': active.id,
                'name': active.name,
                'location': active.location,
            }],
        })

    def test_rejects_non_get_requests(self):
        response = self.client.post(reverse('branches:branch_list'))

        self.assertEqual(response.status_code, 405)


class ConfigureBusinessBranchesTests(TestCase):
    command_options = {
        'otc_name': 'OTC Mall',
        'otc_location': 'Third floor, OTC Mall, Nairobi',
        's18_location': (
            'Second floor, Shop S18, Gaberone Plaza, Gaberone Road, Nairobi'
        ),
        'b03_location': (
            'Fifth floor, Shop B03, Gaberone Plaza, Gaberone Road, Nairobi'
        ),
    }

    def run_command(self, **overrides):
        options = {**self.command_options, **overrides}
        output = StringIO()
        call_command('configure_business_branches', stdout=output, **options)
        return output.getvalue()

    def test_creates_exact_three_branch_capability_topology(self):
        self.run_command()

        self.assertEqual(Branch.objects.filter(is_active=True).count(), 3)
        otc = Branch.objects.get(name='OTC Mall')
        s18 = Branch.objects.get(name='Gaberone Plaza S18')
        b03 = Branch.objects.get(name='Gaberone Plaza B03')
        self.assertTrue(otc.receives_supplier_stock)
        self.assertFalse(otc.offers_customer_pickup)
        self.assertFalse(s18.receives_supplier_stock)
        self.assertTrue(s18.offers_customer_pickup)
        self.assertFalse(b03.receives_supplier_stock)
        self.assertFalse(b03.offers_customer_pickup)

    def test_updates_existing_s18_without_replacing_its_identity(self):
        existing = Branch.objects.create(
            name='Gaberone Plaza S18',
            location='Old description',
        )

        self.run_command()

        existing.refresh_from_db()
        self.assertEqual(
            existing.location,
            self.command_options['s18_location'],
        )
        self.assertTrue(existing.offers_customer_pickup)
        self.assertEqual(
            Branch.objects.filter(name='Gaberone Plaza S18').count(),
            1,
        )

    def test_is_idempotent(self):
        self.run_command()
        original_ids = set(Branch.objects.values_list('id', flat=True))

        self.run_command()

        self.assertEqual(
            set(Branch.objects.values_list('id', flat=True)),
            original_ids,
        )

    def test_dry_run_rolls_back_all_changes(self):
        output = self.run_command(dry_run=True)

        self.assertFalse(Branch.objects.exists())
        self.assertIn('Dry run: no branch changes saved.', output)

    def test_rejects_placeholder_location(self):
        with self.assertRaisesMessage(CommandError, 'cannot be a placeholder'):
            self.run_command(otc_location='TBD')

    def test_refuses_unreviewed_active_branch(self):
        Branch.objects.create(name='Demo Branch', location='Demo')

        with self.assertRaisesMessage(CommandError, 'Unexpected active branch'):
            self.run_command()

        self.assertEqual(Branch.objects.count(), 1)
