from django import forms
from django.core.exceptions import ValidationError

from .models import ProductOptionValue, ProductVariant
from .variant_services import configure_variant


class ProductVariantAdminForm(forms.ModelForm):
    option_values = forms.ModelMultipleChoiceField(
        queryset=ProductOptionValue.objects.select_related('option__product').order_by(
            'option__product__name', 'option__position', 'option__name', 'position', 'value',
        ),
        required=False,
        help_text='Select one value from every option group for this product.',
    )

    class Meta:
        model = ProductVariant
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['option_values'].initial = self.instance.option_values.all()

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get('product')
        values = list(cleaned.get('option_values') or [])
        if not product:
            return cleaned
        expected = set(product.options.values_list('id', flat=True))
        selected = {value.option_id for value in values}
        if expected and selected != expected:
            missing = product.options.exclude(pk__in=selected).values_list('name', flat=True)
            raise ValidationError(
                f"Select one value from every option group. Missing: {', '.join(missing)}."
            )
        if any(value.option.product_id != product.pk for value in values):
            raise ValidationError('Every selected option value must belong to this product.')
        if len(selected) != len(values):
            raise ValidationError('Select only one value from each option group.')
        return cleaned

    def _save_m2m(self):
        values = list(self.cleaned_data.get('option_values') or [])
        if values:
            configure_variant(self.instance, values)
