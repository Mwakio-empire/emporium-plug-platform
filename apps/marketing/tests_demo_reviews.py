from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from catalog.models import Category, Product
from marketing.management.commands.seed_demo_reviews import DEMO_REASON
from marketing.models import ProductReview


class SeedDemoReviewsCommandTests(TestCase):
    def setUp(self):
        User = get_user_model()
        User.objects.create_superuser(
            username='review-moderator',
            phone_number='+254700099999',
            password='test-password',
        )
        category = Category.objects.create(name='Demo Fashion', slug='demo-fashion-reviews')
        Product.objects.create(
            sku='DEMO-HOODIE-001',
            name='Demo Hoodie',
            slug='demo-hoodie-reviews',
            category=category,
            price='2490.00',
            status=Product.Status.ACTIVE,
        )

    def test_command_creates_labelled_unverified_samples_idempotently(self):
        call_command('seed_demo_reviews')
        call_command('seed_demo_reviews')

        reviews = ProductReview.objects.filter(moderation_reason=DEMO_REASON)
        self.assertEqual(reviews.count(), 3)
        self.assertTrue(all(review.is_approved for review in reviews))
        self.assertFalse(any(review.is_verified_purchase for review in reviews))

    def test_remove_deletes_only_demo_records(self):
        call_command('seed_demo_reviews')

        call_command('seed_demo_reviews', remove=True)

        self.assertFalse(ProductReview.objects.filter(moderation_reason=DEMO_REASON).exists())
        self.assertFalse(
            get_user_model().objects.filter(username__startswith='demo-review-').exists()
        )
