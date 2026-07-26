from django.db import migrations


COUNTIES = [
    ('01', 'Mombasa'), ('02', 'Kwale'), ('03', 'Kilifi'),
    ('04', 'Tana River'), ('05', 'Lamu'), ('06', 'Taita Taveta'),
    ('07', 'Garissa'), ('08', 'Wajir'), ('09', 'Mandera'),
    ('10', 'Marsabit'), ('11', 'Isiolo'), ('12', 'Meru'),
    ('13', 'Tharaka-Nithi'), ('14', 'Embu'), ('15', 'Kitui'),
    ('16', 'Machakos'), ('17', 'Makueni'), ('18', 'Nyandarua'),
    ('19', 'Nyeri'), ('20', 'Kirinyaga'), ('21', "Murang'a"),
    ('22', 'Kiambu'), ('23', 'Turkana'), ('24', 'West Pokot'),
    ('25', 'Samburu'), ('26', 'Trans Nzoia'), ('27', 'Uasin Gishu'),
    ('28', 'Elgeyo-Marakwet'), ('29', 'Nandi'), ('30', 'Baringo'),
    ('31', 'Laikipia'), ('32', 'Nakuru'), ('33', 'Narok'),
    ('34', 'Kajiado'), ('35', 'Kericho'), ('36', 'Bomet'),
    ('37', 'Kakamega'), ('38', 'Vihiga'), ('39', 'Bungoma'),
    ('40', 'Busia'), ('41', 'Siaya'), ('42', 'Kisumu'),
    ('43', 'Homa Bay'), ('44', 'Migori'), ('45', 'Kisii'),
    ('46', 'Nyamira'), ('47', 'Nairobi City'),
]


def seed_counties(apps, schema_editor):
    County = apps.get_model('logistics', 'KenyaCounty')
    for code, name in COUNTIES:
        County.objects.update_or_create(code=code, defaults={'name': name, 'is_active': True})


class Migration(migrations.Migration):
    dependencies = [('logistics', '0010_kenyacounty_parceldestination_parceldispatch')]
    operations = [migrations.RunPython(seed_counties, migrations.RunPython.noop)]
