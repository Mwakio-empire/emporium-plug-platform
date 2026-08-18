import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('logistics', '0012_disable_legacy_delivery_zones')]

    operations = [
        migrations.CreateModel(
            name='KenyaTown',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('normalized_name', models.CharField(editable=False, max_length=100)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('source', models.CharField(default='KNBS', max_length=80)),
                ('source_revision', models.CharField(default='2019-KPHC', max_length=40)),
                (
                    'county',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='towns',
                        to='logistics.kenyacounty',
                    ),
                ),
            ],
            options={
                'ordering': ['county__name', 'name'],
                'indexes': [
                    models.Index(
                        fields=['county', 'is_active', 'name'],
                        name='town_county_active_name_idx',
                    ),
                ],
                'constraints': [
                    models.UniqueConstraint(
                        fields=('county', 'normalized_name'),
                        name='unique_normalized_town_per_county',
                    ),
                ],
            },
        ),
    ]
