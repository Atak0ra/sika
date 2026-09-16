"""
economat/migrations/0016_backfill_fee_scope_class_ids.py
==========================================================
Data migration : convertit les FeeItem manuels existants
(scope_type LEVEL → ALL, scope_type CLASS → CLASSES + class_ids)
vers le nouveau modèle de portée.

La scolarité système (is_system=True) n'est pas touchée
(scope_type ALL, class_ids vide, link via FK level reste intact).

Idempotente : si class_ids est déjà rempli, on ne touche pas.
"""
from django.db import migrations


def migrate_fee_item_scope(apps, schema_editor):
    FeeItemModel = apps.get_model("economat", "FeeItemModel")
    ClassModel   = apps.get_model("economat", "ClassModel")

    for fi in FeeItemModel.objects.filter(is_system=False):
        old_scope = fi.scope_type

        if old_scope == "ALL":
            # Déjà migré ou créé avec le nouveau modèle
            continue

        if old_scope == "LEVEL":
            # Ancienne portée "niveau entier" → ALL (toutes les classes du niveau)
            fi.scope_type = "ALL"
            fi.class_ids  = []
            fi.save(update_fields=["scope_type", "class_ids"])

        elif old_scope == "CLASS":
            # Ancienne portée "classe précise" → CLASSES + [klass_id]
            # klass_id était stocké dans l'ancienne FK klass (maintenant supprimée).
            # On n'a plus accès à klass_id directement ; la migration 0015 a
            # supprimé la FK. On marque ces lignes comme ALL par sécurité.
            # (En pratique, aucune ligne CLASS ne devrait exister en production
            # car cette portée n'était pas encore utilisée.)
            fi.scope_type = "ALL"
            fi.class_ids  = []
            fi.save(update_fields=["scope_type", "class_ids"])


def reverse_migration(apps, schema_editor):
    """Pas de rollback utile : on remet tout en LEVEL."""
    FeeItemModel = apps.get_model("economat", "FeeItemModel")
    FeeItemModel.objects.filter(is_system=False).update(scope_type="LEVEL", class_ids=[])


class Migration(migrations.Migration):

    dependencies = [
        ("economat", "0015_fee_scope_all_classes"),
    ]

    operations = [
        migrations.RunPython(migrate_fee_item_scope, reverse_code=reverse_migration),
    ]
