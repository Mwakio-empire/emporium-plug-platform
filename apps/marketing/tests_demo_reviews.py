from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from branches.models import Branch
from catalog.models import Category, Product
from marketing.management.commands.seed_demo_reviews import DEMO_ORDER_NOTE, DEMO_REASON
from marketing.models import ProductReview
from marketing.services import FeedbackService
from orders.models import Order


class SeedDemoReviewsCommandTests(TestCase):
    def setUp(self):
        User = get_user_model()
        User.objects.create_superuser(
            username='review-moderator',
            phone_number='+254700099999',
            password='test-password',
        )
        Branch.objects.create(name='Demo Review Branch', location='Nairobi')
        category = Category.objects.create(name='Demo Fashion', slug='demo-fashion-reviews')
        Product.objects.create(
            sku='DEMO-HOODIE-001',
            name='Demo Hoodie',
            slug='demo-hoodie-reviews',
            category=category,
            price='2490.00',
            status=Product.Status.ACTIVE,
        )

    def test_command_creates_labelled_verified_preview_idempotently(self):
        call_command('seed_demo_reviews')
        call_command('seed_demo_reviews')

        reviews = ProductReview.objects.filter(moderation_reason=DEMO_REASON)
        self.assertEqual(reviews.count(), 3)
        self.assertTrue(all(review.is_approved for review in reviews))
        self.assertEqual(reviews.filter(is_verified_purchase=True).count(), 1)
        verified = reviews.get(is_verified_purchase=True)
        self.assertTrue(FeedbackService._has_completed_purchase(
            verified.product, verified.customer,
        ))
        self.assertEqual(Order.objects.filter(notes=DEMO_ORDER_NOTE).count(), 1)

        response = self.client.get(reverse(
            'core:product_detail', kwargs={'slug': verified.product.slug},
        ))
        self.assertContains(response, 'Sample review')
        self.assertContains(response, 'Verified purchase')
        self.assertContains(response, 'from 3 reviews')
        self.assertNotContains(response, '3 verified reviews')

    def test_remove_deletes_only_demo_records(self):
        call_command('seed_demo_reviews')

        call_command('seed_demo_reviews', remove=True)

        self.assertFalse(ProductReview.objects.filter(moderation_reason=DEMO_REASON).exists())
        self.assertFalse(Order.objects.filter(notes=DEMO_ORDER_NOTE).exists())
        self.assertFalse(
            get_user_model().objects.filter(username__startswith='demo-review-').exists()
        )
