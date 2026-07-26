from django.db import migrations


def disable_legacy_zones(apps, schema_editor):
    DeliveryZone = apps.get_model('logistics', 'DeliveryZone')
    DeliveryZone.objects.filter(is_active=True).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [('logistics', '0011_seed_kenya_counties')]
    operations = [migrations.RunPython(disable_legacy_zones, migrations.RunPython.noop)]
