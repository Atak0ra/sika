"""
application/use_cases/create_fee_item.py
==========================================
USE CASE : CreateFeeItemUseCase — Acteurs : Directeur / Secrétaire / Économe

Crée une ligne de frais manuelle (cantine, sortie, sport, fournitures, autre).
La catégorie SCOLARITE est interdite — les lignes scolarité sont créées
automatiquement par ensure_system_fee_for_level().
"""
from __future__ import annotations
import uuid

from economat.application.dto import CreateFeeItemCommand, FeeItemResult
from economat.application.ports.repositories import FeeItemRepository
from economat.domain.fee.entities import FeeItem
from economat.domain.fee.value_objects import FeeCategory, FeeItemId, FeeScope, FeeScopeType
from economat.domain.school.payment_schedule import PaymentMode
from economat.domain.school.value_objects import SchoolYearId
from economat.domain.shared.errors import DomainError
from economat.domain.shared.value_objects import Currency, Money


class CreateFeeItemUseCase:
    def __init__(self, fee_item_repo: FeeItemRepository) -> None:
        self._fees = fee_item_repo

    def execute(self, cmd: CreateFeeItemCommand) -> FeeItemResult:
        try:
            return self._execute(cmd)
        except (DomainError, ValueError) as e:
            return FeeItemResult(success=False, error_message=str(e))
        except Exception as e:
            return FeeItemResult(success=False, error_message=f"Erreur inattendue : {e}")

    def _execute(self, cmd: CreateFeeItemCommand) -> FeeItemResult:
        # Validation catégorie
        try:
            category = FeeCategory(cmd.category)
        except ValueError:
            raise DomainError(f"Catégorie inconnue : {cmd.category}")

        if category == FeeCategory.SCOLARITE:
            raise DomainError(
                "La catégorie SCOLARITE est réservée. "
                "Elle est créée automatiquement depuis le tarif du niveau."
            )

        if cmd.amount_fcfa <= 0:
            raise DomainError("Le montant doit être supérieur à 0 FCFA.")

        if not cmd.name.strip():
            raise DomainError("Le nom de la ligne ne peut pas être vide.")

        # Validation portée
        try:
            scope_type = FeeScopeType(cmd.scope_type)
        except ValueError:
            raise DomainError(f"Type de portée inconnu : {cmd.scope_type}")
        scope = FeeScope(scope_type=scope_type, target_id=cmd.target_id)

        # Validation mode de paiement
        try:
            payment_mode = PaymentMode(cmd.payment_mode)
        except ValueError:
            raise DomainError(f"Mode de paiement inconnu : {cmd.payment_mode}")

        fee_item = FeeItem(
            id=FeeItemId(value=str(uuid.uuid4())),
            school_year_id=SchoolYearId(cmd.school_year_id),
            name=cmd.name.strip(),
            category=category,
            amount=Money(cmd.amount_fcfa, Currency.XOF),
            scope=scope,
            payment_mode=payment_mode,
            nb_months=cmd.nb_months,
            is_mandatory=cmd.is_mandatory,
            is_active=True,
            is_system=False,
        )

        self._fees.save(fee_item)
        return FeeItemResult(
            success=True,
            fee_item_id=str(fee_item.id),
            name=fee_item.name,
            category=fee_item.category.value,
        )
