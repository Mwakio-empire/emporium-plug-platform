from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from catalog.models import Product
from marketing.models import ProductReview


DEMO_REASON = 'DEMO_ONLY: simulated review for storefront interface testing.'
REVIEWERS = (
    ('amina', '+254700090001', 'Amina'),
    ('brian', '+254700090002', 'Brian'),
    ('wanjiku', '+254700090003', 'Wanjiku'),
)
REVIEWS = {
    'DEMO-HOODIE-001': (
        (5, 'The fabric feels substantial and the relaxed fit looks good. The size options are easy to understand.'),
        (4, 'Comfortable for cooler evenings. I would like to see more colours added later.'),
        (5, 'The cuffs and hood feel well finished, and the fit matched what I expected.'),
    ),
    'DEMO-BACKPACK-001': (
        (5, 'The compartments are practical for work and the padded straps sit comfortably.'),
        (4, 'Good everyday size and the bottle pocket is useful. The navy colour looks smart.'),
        (4, 'It holds my daily essentials without feeling bulky. The zips are easy to use.'),
    ),
    'DEMO-FLASK-001': (
        (5, 'Kept my drink hot for the morning and the lid closed securely in my bag.'),
        (4, 'The 750 ml option is a useful size and the finish is easy to clean.'),
        (5, 'Feels sturdy and does not leak when properly closed. The colour is also accurate.'),
    ),
    'DEMO-PAN-001': (
        (5, 'Food released easily and the handle stayed comfortable during normal cooking.'),
        (4, 'The size selector made it easy to choose the right pan. Cleaning was straightforward.'),
        (5, 'A useful everyday pan with an even base and a comfortable handle.'),
    ),
}


class Command(BaseCommand):
    help = 'Create or remove clearly labelled simulated reviews for local interface testing.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--remove', action='store_true',
            help='Remove only the users and reviews created by this command.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if getattr(settings, 'IS_PRODUCTION', False):
            raise CommandError('Demo reviews are blocked in production.')

        User = get_user_model()
        demo_users = User.objects.filter(username__startswith='demo-review-')
        if options['remove']:
            removed_reviews, _ = ProductReview.objects.filter(
                moderation_reason=DEMO_REASON,
            ).delete()
            removed_users, _ = demo_users.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Removed {removed_reviews} demo review records and {removed_users} demo user records.'
            ))
            return

        moderator = User.objects.filter(
            is_superuser=True, is_active=True,
        ).order_by('pk').first()
        if moderator is None:
            raise CommandError('An active superuser is required to moderate demo reviews.')

        users = []
        for key, phone, first_name in REVIEWERS:
            username = f'demo-review-{key}'
            user = User.objects.filter(username=username).first()
            if user is None:
                user = User(
                    username=username,
                    phone_number=phone,
                    email=f'{username}@example.invalid',
                    first_name=first_name,
                    role=User.Role.CUSTOMER,
                    is_active=False,
                )
                user.set_unusable_password()
                user.save()
            users.append(user)

        products = Product.objects.filter(sku__in=REVIEWS).in_bulk(field_name='sku')
        if not products:
            raise CommandError('No demo catalogue products were found. Run seed_demo_catalog first.')

        now = timezone.now()
        created = 0
        updated = 0
        for sku, definitions in REVIEWS.items():
            product = products.get(sku)
            if product is None:
                continue
            for user, (rating, comment) in zip(users, definitions, strict=True):
                _, was_created = ProductReview.objects.update_or_create(
                    product=product,
                    customer=user,
                    is_current=True,
                    defaults={
                        'rating': rating,
                        'comment': comment,
                        'is_verified_purchase': False,
                        'is_approved': True,
                        'moderated_by': moderator,
                        'moderated_at': now,
                        'moderation_reason': DEMO_REASON,
                    },
                )
                created += int(was_created)
                updated += int(not was_created)

        self.stdout.write(self.style.SUCCESS(
            f'Demo reviews ready: {created} created, {updated} updated. '
            'They are labelled Sample review and are not verified purchases.'
        ))
