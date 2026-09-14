# Migration 0008 — CountryModel + SchoolModel.country → FK
#
# Étapes :
#   1. Créer la table economat_country
#   2. Renommer country (CharField) → country_legacy
#   3. Ajouter country_new (FK nullable)
#   4. RunPython : pré-remplir les 5 pays + mapper les écoles existantes
#   5. Supprimer country_legacy
#   6. Renommer country_new → country

from django.db import migrations, models
import django.db.models.deletion

INITIAL_COUNTRIES = [
    ("SN", "Sénégal",        "XOF", "samirpay", ["Orange Money", "Wave", "Free Money"]),
    ("CI", "Côte d'Ivoire",  "XOF", "",         ["Orange Money", "MTN Mobile Money", "Moov Money", "Wave"]),
    ("TG", "Togo",           "XOF", "",         ["Flooz (Togocom)", "T-Money (Togocom)", "Wave"]),
    ("BJ", "Bénin",          "XOF", "",         ["MTN Mobile Money", "Moov Money"]),
    ("GN", "Guinée Conakry", "XOF", "crpay",    ["Orange Money", "MTN Mobile Money"]),
]

# Mapping legacy string → code ISO (tolère libellés ET codes déjà ISO)
LEGACY_TO_CODE = {
    "Sénégal": "SN", "senegal": "SN", "SN": "SN",
    "Côte d'Ivoire": "CI", "Cote d'Ivoire": "CI", "CI": "CI",
    "Togo": "TG", "togo": "TG", "TG": "TG",
    "Bénin": "BJ", "Benin": "BJ", "BJ": "BJ",
    "Guinée Conakry": "GN", "Guinee Conakry": "GN", "GN": "GN",
}



def populate_countries_and_migrate_schools(apps, schema_editor):
    CountryModel = apps.get_model("economat", "CountryModel")
    SchoolModel  = apps.get_model("economat", "SchoolModel")

    countries = {}
    for code, name, currency, provider, operators in INITIAL_COUNTRIES:
        country, _ = CountryModel.objects.get_or_create(
            code=code,
            defaults={"name": name, "currency": currency,
                      "payment_provider": provider,
                      "mobile_operators": operators, "is_active": True},
        )
        countries[code] = country

    default_country = countries["SN"]
    for school in SchoolModel.objects.all():
        raw = (school.country_legacy or "").strip()
        code = LEGACY_TO_CODE.get(raw, "SN")
        school.country_new = countries.get(code, default_country)
        school.save(update_fields=["country_new"])


def reverse_migration(apps, schema_editor):
    SchoolModel = apps.get_model("economat", "SchoolModel")
    for school in SchoolModel.objects.select_related("country_new").all():
        if school.country_new:
            school.country_legacy = school.country_new.name
            school.save(update_fields=["country_legacy"])


class Migration(migrations.Migration):
    dependencies = [("economat", "0007_paymentmodel_channel_and_more")]

    operations = [
        migrations.CreateModel(
            name="CountryModel",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("code", models.CharField(db_index=True, max_length=2, unique=True,
                                          verbose_name="Code ISO",
                                          help_text="Code ISO 3166-1 alpha-2 (ex. SN)")),
                ("name", models.CharField(max_length=100, verbose_name="Pays")),
                ("currency", models.CharField(default="XOF", max_length=10,
                                              verbose_name="Devise", help_text="XOF, XAF…")),
                ("payment_provider", models.CharField(
                    blank=True, default="", max_length=20,
                    choices=[("", "Aucune (mode test / Fake)"),
                             ("samirpay", "Samirpay (Sénégal)"),
                             ("crpay", "CRPay (Guinée Conakry)")],
                    verbose_name="Passerelle de paiement")),
                ("mobile_operators", models.JSONField(
                    blank=True, default=list, verbose_name="Opérateurs Mobile Money",
                    help_text='Liste JSON, ex. ["Orange Money", "Wave"]')),
                ("is_active", models.BooleanField(
                    default=True, verbose_name="Actif",
                    help_text="Masqué dans les formulaires si décoché")),
            ],
            options={"db_table": "economat_country", "ordering": ["name"],
                     "verbose_name": "Pays", "verbose_name_plural": "Pays",
                     "app_label": "economat"},
        ),
        migrations.RenameField(
            model_name="schoolmodel", old_name="country", new_name="country_legacy",
        ),
        migrations.AddField(
            model_name="schoolmodel",
            name="country_new",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="schools",
                to="economat.countrymodel",
                verbose_name="Pays",
            ),
        ),
        migrations.RunPython(populate_countries_and_migrate_schools, reverse_code=reverse_migration),
        migrations.RemoveField(model_name="schoolmodel", name="country_legacy"),
        migrations.RenameField(model_name="schoolmodel", old_name="country_new", new_name="country"),
    ]
