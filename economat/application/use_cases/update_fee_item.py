"""
application/use_cases/update_fee_item.py
==========================================
USE CASE : UpdateFeeItemUseCase — Acteurs : Directeur / Secrétaire / Économe

Modifie ou archive une ligne de frais manuelle.
Les lignes système (scolarité) ne peuvent pas être modifiées ici.
"""
from __future__ import annotations

from economat.application.dto import DeactivateFeeItemCommand, FeeItemResult, UpdateFeeItemCommand
from economat.application.ports.repositories import FeeItemRepository
from economat.domain.fee.value_objects import FeeItemId
from economat.domain.school.payment_schedule import PaymentMode
from economat.domain.shared.errors import DomainError, EntityNotFoundError
from economat.domain.shared.value_objects import Currency, Money


class UpdateFeeItemUseCase:
    def __init__(self, fee_item_repo: FeeItemRepository) -> None:
        self._fees = fee_item_repo

    def execute(self, cmd: UpdateFeeItemCommand) -> FeeItemResult:
        try:
            return self._execute(cmd)
        except (DomainError, EntityNotFoundError, ValueError) as e:
            return FeeItemResult(success=False, error_message=str(e))
        except Exception as e:
            return FeeItemResult(success=False, error_message=f"Erreur inattendue : {e}")

    def _execute(self, cmd: UpdateFeeItemCommand) -> FeeItemResult:
        fee_item = self._fees.find_by_id(FeeItemId(cmd.fee_item_id))
        if fee_item is None:
            raise EntityNotFoundError("Ligne de frais introuvable.")
        if fee_item.is_system:
            raise DomainError(
                "Impossible de modifier une ligne scolarité (système). "
                "Modifiez le tarif du niveau à la place."
            )
        if not cmd.name.strip():
            raise DomainError("Le nom ne peut pas être vide.")
        if cmd.amount_fcfa <= 0:
            raise DomainError("Le montant doit être supérieur à 0 FCFA.")
        try:
            payment_mode = PaymentMode(cmd.payment_mode)
        except ValueError:
            raise DomainError(f"Mode de paiement inconnu : {cmd.payment_mode}")

        fee_item.name         = cmd.name.strip()
        fee_item.amount       = Money(cmd.amount_fcfa, Currency.XOF)
        fee_item.payment_mode = payment_mode
        fee_item.nb_months    = cmd.nb_months
        fee_item.is_mandatory = cmd.is_mandatory

        self._fees.save(fee_item)
        return FeeItemResult(
            success=True,
            fee_item_id=str(fee_item.id),
            name=fee_item.name,
            category=fee_item.category.value,
        )


class DeactivateFeeItemUseCase:
    def __init__(self, fee_item_repo: FeeItemRepository) -> None:
        self._fees = fee_item_repo

    def execute(self, cmd: DeactivateFeeItemCommand) -> FeeItemResult:
        try:
            fee_item = self._fees.find_by_id(FeeItemId(cmd.fee_item_id))
            if fee_item is None:
                raise EntityNotFoundError("Ligne de frais introuvable.")
            fee_item.deactivate()   # lève DomainError si is_system
            self._fees.save(fee_item)
            return FeeItemResult(success=True, fee_item_id=str(fee_item.id), name=fee_item.name)
        except (DomainError, EntityNotFoundError) as e:
            return FeeItemResult(success=False, error_message=str(e))
        except Exception as e:
            return FeeItemResult(success=False, error_message=f"Erreur inattendue : {e}")
