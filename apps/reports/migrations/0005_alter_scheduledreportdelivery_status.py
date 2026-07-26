from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0004_scheduledreport_scheduledreportdelivery'),
    ]

    operations = [
        migrations.AlterField(
            model_name='scheduledreportdelivery',
            name='status',
            field=models.CharField(
                choices=[
                    ('PROCESSING', 'Processing - Do Not Retry'),
                    ('SENT', 'Sent'),
                    ('FAILED', 'Failed - Manual Follow-up Required'),
                ],
                max_length=10,
            ),
        ),
    ]
