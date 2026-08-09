from itertools import product as cartesian_product

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import (
    Product,
    ProductOptionValue,
    ProductVariant,
    VariantOptionAssignment,
)


def _normalise_values(product, option_values):
    option_values = list(option_values)
    values = list(ProductOptionValue.objects.select_related('option').filter(
        pk__in=[value.pk if hasattr(value, 'pk') else value for value in option_values],
    ).order_by('option__position', 'option_id', 'position', 'id'))
    if len(values) != len(option_values):
        raise ValidationError('One or more selected option values no longer exist.')
    if any(value.option.product_id != product.pk for value in values):
        raise ValidationError('Every option value must belong to this product.')
    if len({value.option_id for value in values}) != len(values):
        raise ValidationError('Select exactly one value from each option group.')
    expected_option_ids = set(product.options.values_list('id', flat=True))
    if expected_option_ids and {value.option_id for value in values} != expected_option_ids:
        raise ValidationError('A variant combination must include every product option.')
    return values


def combination_signature(values):
    return '|'.join(f'{value.option_id}:{value.pk}' for value in values)


@transaction.atomic
def configure_variant(variant, option_values):
    """Validate and atomically attach a complete, unique option combination."""
    locked_variant = ProductVariant.objects.select_for_update().select_related('product').get(
        pk=variant.pk,
    )
    values = _normalise_values(locked_variant.product, option_values)
    signature = combination_signature(values)
    duplicate = ProductVariant.objects.filter(
        product=locked_variant.product,
        combination_signature=signature,
    ).exclude(pk=locked_variant.pk).exists()
    if duplicate:
        raise ValidationError('This product already has that option combination.')

    VariantOptionAssignment.objects.filter(variant=locked_variant).delete()
    VariantOptionAssignment.objects.bulk_create([
        VariantOptionAssignment(
            variant=locked_variant, option=value.option, value=value,
        )
        for value in values
    ])
    locked_variant.attribute_name = ' / '.join(value.option.name for value in values)[:50]
    locked_variant.attribute_value = ' / '.join(value.value for value in values)[:50]
    locked_variant.combination_signature = signature
    locked_variant.save(update_fields=[
        'attribute_name', 'attribute_value', 'combination_signature',
    ])
    return locked_variant


@transaction.atomic
def generate_missing_combinations(product_id):
    """Create all missing combinations for the values configured on a product."""
    product = Product.objects.select_for_update().get(pk=product_id)
    options = list(product.options.prefetch_related('values').order_by('position', 'id'))
    if not options or any(not option.values.exists() for option in options):
        raise ValidationError('Add at least one value to every option before generating variants.')

    created = []
    for values in cartesian_product(*(list(option.values.all()) for option in options)):
        signature = combination_signature(values)
        if ProductVariant.objects.filter(
            product=product, combination_signature=signature,
        ).exists():
            continue
        variant = ProductVariant.objects.create(
            product=product,
            attribute_name=' / '.join(option.name for option in options)[:50],
            attribute_value=' / '.join(value.value for value in values)[:50],
            combination_signature=signature,
        )
        VariantOptionAssignment.objects.bulk_create([
            VariantOptionAssignment(variant=variant, option=value.option, value=value)
            for value in values
        ])
        created.append(variant)
    return created
