from django.db import migrations


def purge_otp_codes(apps, schema_editor):
    # Pre-Phase-2 rows may contain plaintext OTPs. OTPs are short-lived and
    # safely replaceable, so deleting every pending/historical row is safer
    # than trying to distinguish legacy values from password hashes.
    OTPVerification = apps.get_model('users', 'OTPVerification')
    OTPVerification.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0005_user_failed_login_attempts_user_last_failed_login_at_and_more'),
    ]

    operations = [
        migrations.RunPython(purge_otp_codes, migrations.RunPython.noop),
    ]
