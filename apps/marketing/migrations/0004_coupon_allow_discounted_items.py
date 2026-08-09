from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketing', '0003_couponredemption_coupon_branches_coupon_is_active_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='coupon',
            name='allow_discounted_items',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Allow this coupon on flash-sale items. Quantity/wholesale '
                    'prices remain ineligible.'
                ),
            ),
        ),
    ]
