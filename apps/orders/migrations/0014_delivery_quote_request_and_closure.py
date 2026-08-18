import django.db.models.deletion
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0013_orderitem_pricing_source_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DeliveryQuoteClosure',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True)),
                ('label', models.CharField(max_length=120)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['date']},
        ),
        migrations.CreateModel(
            name='DeliveryQuoteRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference', models.CharField(editable=False, max_length=20, unique=True)),
                ('status', models.CharField(choices=[('REQUESTED', 'Requested'), ('REVIEWING', 'Being reviewed'), ('QUOTED', 'Quote ready'), ('ACCEPTED', 'Accepted'), ('DECLINED', 'Declined'), ('EXPIRED', 'Expired'), ('CANCELLED', 'Cancelled')], db_index=True, default='REQUESTED', max_length=20)),
                ('guest_session_hash', models.CharField(blank=True, default='', max_length=64)),
                ('customer_phone', models.CharField(max_length=15)),
                ('customer_name', models.CharField(max_length=100)),
                ('customer_email', models.EmailField(blank=True, default='', max_length=254)),
                ('county', models.CharField(max_length=80)),
                ('town', models.CharField(max_length=100)),
                ('preferred_collection_area', models.CharField(max_length=160)),
                ('notes', models.TextField(blank=True, default='')),
                ('cart_snapshot', models.JSONField(default=list)),
                ('requested_subtotal', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('response_due_at', models.DateTimeField(db_index=True)),
                ('review_started_at', models.DateTimeField(blank=True, null=True)),
                ('transport_operator', models.CharField(blank=True, default='', max_length=120)),
                ('collection_point', models.CharField(blank=True, default='', max_length=160)),
                ('delivery_fee', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('expected_arrival', models.CharField(blank=True, default='', max_length=180)),
                ('quoted_at', models.DateTimeField(blank=True, null=True)),
                ('expires_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('accepted_at', models.DateTimeField(blank=True, null=True)),
                ('declined_at', models.DateTimeField(blank=True, null=True)),
                ('cancelled_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='delivery_quote_requests', to='branches.branch')),
                ('customer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='delivery_quote_requests', to=settings.AUTH_USER_MODEL)),
                ('order', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='delivery_quote_request', to='orders.order')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='delivery_quotes_reviewed', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['created_at'],
                'constraints': [
                    models.CheckConstraint(condition=models.Q(('requested_subtotal__gte', 0)), name='delivery_quote_subtotal_nonnegative'),
                    models.CheckConstraint(condition=models.Q(('delivery_fee__gte', 0)), name='delivery_quote_fee_nonnegative'),
                ],
            },
        ),
    ]
