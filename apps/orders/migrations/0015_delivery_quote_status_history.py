import django.db.models.deletion

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0014_delivery_quote_request_and_closure'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DeliveryQuoteStatusHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('old_status', models.CharField(blank=True, max_length=20)),
                ('new_status', models.CharField(choices=[('REQUESTED', 'Requested'), ('REVIEWING', 'Being reviewed'), ('QUOTED', 'Quote ready'), ('ACCEPTED', 'Accepted'), ('DECLINED', 'Declined'), ('EXPIRED', 'Expired'), ('CANCELLED', 'Cancelled')], max_length=20)),
                ('note', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('changed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='delivery_quote_status_changes', to=settings.AUTH_USER_MODEL)),
                ('quote', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='status_history', to='orders.deliveryquoterequest')),
            ],
            options={'ordering': ['created_at']},
        ),
    ]
