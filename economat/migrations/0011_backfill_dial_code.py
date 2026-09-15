from django.db import migrations

DIAL_CODES = {
    "SN": "+221",  # Sénégal
    "CI": "+225",  # Côte d'Ivoire
    "TG": "+228",  # Togo
    "BJ": "+229",  # Bénin
    "GN": "+224",  # Guinée Conakry
}


def backfill_dial_code(apps, schema_editor):
    CountryModel = apps.get_model("economat", "CountryModel")
    for code, dial_code in DIAL_CODES.items():
        CountryModel.objects.filter(code=code, dial_code="").update(dial_code=dial_code)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("economat", "0010_countrymodel_dial_code")]

    operations = [
        migrations.RunPython(backfill_dial_code, reverse_code=noop_reverse),
    ]
