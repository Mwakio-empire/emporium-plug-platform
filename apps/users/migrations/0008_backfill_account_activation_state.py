from django.db import migrations, models
from django.db.models import F, Q


def backfill_activation_state(apps, schema_editor):
    User = apps.get_model('users', 'User')
    User.objects.filter(
        Q(is_active=True) | ~Q(role='CUSTOMER'),
        activated_at__isnull=True,
    ).update(activated_at=F('date_joined'))


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0007_user_activated_at_alter_otpverification_purpose_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_activation_state, migrations.RunPython.noop),
    ]
