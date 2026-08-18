from django.db import migrations


def migrate_legacy_variants(apps, schema_editor):
    ProductOption = apps.get_model('catalog', 'ProductOption')
    ProductOptionValue = apps.get_model('catalog', 'ProductOptionValue')
    ProductVariant = apps.get_model('catalog', 'ProductVariant')
    VariantOptionAssignment = apps.get_model('catalog', 'VariantOptionAssignment')

    for variant in ProductVariant.objects.select_related('product').iterator():
        option, _ = ProductOption.objects.get_or_create(
            product_id=variant.product_id,
            name=variant.attribute_name,
            defaults={'position': 0},
        )
        value, _ = ProductOptionValue.objects.get_or_create(
            option=option,
            value=variant.attribute_value,
            defaults={'position': 0},
        )
        VariantOptionAssignment.objects.get_or_create(
            variant=variant,
            option=option,
            defaults={'value': value},
        )
        variant.sku = f'{variant.product.sku}-V{variant.pk:06d}'
        variant.combination_signature = f'{option.pk}:{value.pk}'
        variant.save(update_fields=['sku', 'combination_signature'])


class Migration(migrations.Migration):
    dependencies = [('catalog', '0006_alter_productvariant_unique_together_and_more')]
    operations = [migrations.RunPython(migrate_legacy_variants, migrations.RunPython.noop)]
