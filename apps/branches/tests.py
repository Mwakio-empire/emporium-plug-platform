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
