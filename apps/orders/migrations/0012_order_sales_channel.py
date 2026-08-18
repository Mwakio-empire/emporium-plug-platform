from django.db import migrations, models


def classify_existing_orders(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')
    Order.objects.filter(order_type='WALK_IN').update(sales_channel='POS')


class Migration(migrations.Migration):

    dependencies = [('orders', '0011_order_parcel_collection_point_and_more')]

    operations = [
        migrations.AddField(
            model_name='order',
            name='sales_channel',
            field=models.CharField(
                choices=[
                    ('WEBSITE', 'Website checkout'),
                    ('WHATSAPP_ASSISTED', 'WhatsApp assisted'),
                    ('POS', 'Walk-in POS'),
                ],
                db_index=True,
                default='WEBSITE',
                max_length=20,
            ),
        ),
        migrations.RunPython(classify_existing_orders, migrations.RunPython.noop),
    ]
