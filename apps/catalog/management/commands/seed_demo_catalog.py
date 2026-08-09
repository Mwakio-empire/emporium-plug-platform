from decimal import Decimal
from pathlib import Path

import cloudinary.uploader
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from branches.models import Branch
from inventory.models import Stock, StockAuditLog
from inventory.services import InventoryService

from catalog.models import Category, Product, ProductOption, ProductOptionValue
from catalog.variant_services import generate_missing_combinations


PRODUCTS = (
    {
        'sku': 'DEMO-HOODIE-001', 'name': 'Everyday Heavyweight Hoodie',
        'slug': 'everyday-heavyweight-hoodie', 'category': 'Demo Fashion',
        'price': '2490.00', 'image': 'hoodie.png',
        'description': 'A soft heavyweight pullover hoodie with a relaxed everyday fit.',
        'specifications': {'Material': 'Cotton-blend fleece', 'Care': 'Machine wash cold'},
        'options': (
            ('Size', 'BUTTON', (('S', ''), ('M', ''), ('L', ''), ('XL', ''))),
            ('Colour', 'COLOUR', (('Black', '#202124'), ('Grey', '#6B7280'), ('Orange', '#EA580C'))),
        ),
    },
    {
        'sku': 'DEMO-BACKPACK-001', 'name': 'Everyday Commuter Backpack',
        'slug': 'everyday-commuter-backpack', 'category': 'Demo Bags & Travel',
        'price': '1890.00', 'image': 'backpack.png',
        'description': 'A practical multi-pocket backpack for work, school and day trips.',
        'specifications': {'Material': 'Woven polyester', 'Features': 'Padded straps and bottle pocket'},
        'options': (
            ('Capacity', 'BUTTON', (('20 L', ''), ('30 L', ''))),
            ('Colour', 'COLOUR', (('Navy', '#172554'), ('Black', '#111827'), ('Rose', '#BE5674'))),
        ),
    },
    {
        'sku': 'DEMO-FLASK-001', 'name': 'Stainless Steel Vacuum Flask',
        'slug': 'stainless-steel-vacuum-flask', 'category': 'Demo Home & Kitchen',
        'price': '1250.00', 'image': 'vacuum-flask.png',
        'description': 'An insulated stainless-steel flask for hot or cold everyday drinks.',
        'specifications': {'Material': 'Stainless steel', 'Insulation': 'Double-wall vacuum'},
        'options': (
            ('Capacity', 'BUTTON', (('500 ml', ''), ('750 ml', ''))),
            ('Colour', 'COLOUR', (('Orange', '#EA580C'), ('Black', '#111827'), ('Blue', '#1D4ED8'))),
        ),
    },
    {
        'sku': 'DEMO-PAN-001', 'name': 'Classic Non-Stick Frying Pan',
        'slug': 'classic-non-stick-frying-pan', 'category': 'Demo Home & Kitchen',
        'price': '1450.00', 'image': 'frying-pan.png',
        'description': 'A versatile non-stick frying pan with a comfortable stay-cool handle.',
        'specifications': {'Coating': 'Non-stick', 'Care': 'Hand wash recommended'},
        'options': (
            ('Size', 'BUTTON', (('24 cm', ''), ('28 cm', ''), ('30 cm', ''))),
        ),
    },
)


class Command(BaseCommand):
    help = 'Idempotently create a visual demo catalogue with structured variants and audited stock.'

    def add_arguments(self, parser):
        parser.add_argument('--branch', default='Gaberone Plaza S18')
        parser.add_argument('--quantity', type=int, default=5)
        parser.add_argument('--skip-images', action='store_true')

    def handle(self, *args, **options):
        if options['quantity'] < 0:
            raise CommandError('Quantity cannot be negative.')
        branch = Branch.objects.filter(name=options['branch'], is_active=True).first()
        if not branch:
            raise CommandError(f"Active branch '{options['branch']}' was not found.")
        actor = get_user_model().objects.filter(is_superuser=True, is_active=True).order_by('pk').first()
        if not actor:
            raise CommandError('An active superuser is required to create audited demo stock.')

        image_dir = Path(settings.BASE_DIR) / 'media' / 'demo_catalog'
        totals = {'products': 0, 'variants': 0, 'images': 0, 'stocks': 0}
        for definition in PRODUCTS:
            category, _ = Category.objects.get_or_create(
                name=definition['category'],
                defaults={'slug': definition['category'].lower().replace(' & ', '-').replace(' ', '-')},
            )
            product, created = Product.objects.update_or_create(
                sku=definition['sku'],
                defaults={
                    'name': definition['name'], 'slug': definition['slug'],
                    'category': category, 'price': Decimal(definition['price']),
                    'description': definition['description'],
                    'meta_description': definition['description'][:160],
                    'specifications': definition['specifications'],
                    'status': Product.Status.ACTIVE,
                },
            )
            totals['products'] += int(created)
            if not options['skip_images'] and not product.image:
                image_path = image_dir / definition['image']
                if not image_path.exists():
                    raise CommandError(f'Missing generated image: {image_path}')
                uploaded = cloudinary.uploader.upload(
                    str(image_path),
                    folder='catalog_products/demo',
                    public_id=image_path.stem,
                    resource_type='image',
                    overwrite=True,
                )
                product.image = uploaded['public_id']
                product.save(update_fields=['image', 'updated_at'])
                totals['images'] += 1

            for option_position, (name, display_type, values) in enumerate(definition['options'], 1):
                option, _ = ProductOption.objects.update_or_create(
                    product=product, name=name,
                    defaults={'display_type': display_type, 'position': option_position},
                )
                for value_position, (value, colour_hex) in enumerate(values, 1):
                    ProductOptionValue.objects.update_or_create(
                        option=option, value=value,
                        defaults={'colour_hex': colour_hex, 'position': value_position},
                    )
            created_variants = generate_missing_combinations(product.pk)
            totals['variants'] += len(created_variants)

            for index, variant in enumerate(product.variants.filter(is_active=True), 1):
                if definition['sku'] == 'DEMO-PAN-001' and '30 cm' in variant.attribute_value:
                    variant.price_override = Decimal('1890.00')
                    variant.save(update_fields=['price_override'])
                elif '750 ml' in variant.attribute_value or '30 L' in variant.attribute_value:
                    variant.price_override = product.price + Decimal('350.00')
                    variant.save(update_fields=['price_override'])
                stock = Stock.objects.filter(branch=branch, variant=variant).first()
                current = stock.quantity if stock else 0
                difference = options['quantity'] - current
                if difference:
                    InventoryService.adjust_stock(
                        branch=branch, variant=variant, change_amount=difference,
                        reason=StockAuditLog.Reason.CORRECTION, triggered_by=actor,
                        reference_number=f'DEMO-CATALOG-{variant.pk}-{options["quantity"]}',
                        note='Idempotent local demo catalogue stock setup.',
                    )
                    totals['stocks'] += 1

        self.stdout.write(self.style.SUCCESS(
            'Demo catalogue ready: '
            f"{totals['products']} products created, {totals['variants']} variants created, "
            f"{totals['images']} images uploaded, {totals['stocks']} stock lines adjusted."
        ))
