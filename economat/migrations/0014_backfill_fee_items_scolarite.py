"""
economat/migrations/0014_backfill_fee_items_scolarite.py
=========================================================
Migration de données : crée une ligne système FeeItem SCOLARITE pour chaque
niveau existant, puis rattache tous les paiements existants (fee_item=null)
au FeeItem SCOLARITE de leur niveau.

Idempotente : `get_or_create` garantit qu'une re-exécution ne crée pas de
doublons si la migration était appliquée partiellement.
"""
from __future__ import annotations

import uuid

from django.db import migrations


def create_scolarite_fee_items(apps, schema_editor):
    """Pour chaque niveau, crée le FeeItem système SCOLARITE correspondant."""
    LevelModel      = apps.get_model("economat", "LevelModel")
    FeeItemModel    = apps.get_model("economat", "FeeItemModel")
    PaymentModel    = apps.get_model("economat", "PaymentModel")
    EnrollmentModel = apps.get_model("economat", "EnrollmentModel")

    # ── 1. Créer un FeeItem SCOLARITE système par niveau ──────────────────────
    for level in LevelModel.objects.select_related("school_year").all():
        fee_item, _ = FeeItemModel.objects.get_or_create(
            school_year_id=level.school_year_id,
            level_id=level.id,
            is_system=True,
            category="SCOLARITE",
            defaults={
                "id":           uuid.uuid4(),
                "name":         f"Scolarité — {level.name}",
                "amount":       level.annual_fee,
                "scope_type":   "LEVEL",
                "payment_mode": level.payment_mode,
                "nb_months":    level.nb_months,
                "is_mandatory": True,
                "is_active":    True,
            },
        )
        # Mettre à jour le montant si le tarif a changé (réexécution idempotente)
        if fee_item.amount != level.annual_fee:
            fee_item.amount       = level.annual_fee
            fee_item.payment_mode = level.payment_mode
            fee_item.nb_months    = level.nb_months
            fee_item.save(update_fields=["amount", "payment_mode", "nb_months"])

    # ── 2. Rattacher les paiements existants (fee_item=null) ─────────────────
    # On trouve la ligne SCOLARITE du niveau de chaque paiement via enrollment → level
    for payment in PaymentModel.objects.filter(fee_item__isnull=True).select_related(
        "enrollment__level"
    ):
        level_id = payment.enrollment.level_id
        fee_item = FeeItemModel.objects.filter(
            level_id=level_id, is_system=True, category="SCOLARITE"
        ).first()
        if fee_item:
            payment.fee_item = fee_item
            payment.save(update_fields=["fee_item"])


def reverse_backfill(apps, schema_editor):
    """Annule le backfill : remet fee_item à null sur les paiements touchés."""
    PaymentModel = apps.get_model("economat", "PaymentModel")
    PaymentModel.objects.filter(
        fee_item__is_system=True, fee_item__category="SCOLARITE"
    ).update(fee_item=None)


class Migration(migrations.Migration):

    dependencies = [
        ("economat", "0013_fee_items_and_level_nb_months"),
    ]

    operations = [
        migrations.RunPython(
            create_scolarite_fee_items,
            reverse_code=reverse_backfill,
        ),
    ]
