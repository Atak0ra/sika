"""
domain/fee/entities.py
========================
Entité FeeItem — poste de frais de scolarité.

Tarification différenciée par classe :
  - `amount`        : montant par défaut (toutes classes sans surcharge).
  - `class_amounts` : surcharges optionnelles { class_id_str: montant_int }.
  - `amount_for(class_id)` résout le montant effectif.
  - `get_payment_schedule(year_start, class_id)` utilise amount_for.
"""
from __future__ import annotations
import datetime
from dataclasses import dataclass, field
from typing import Dict, Optional

from ..school.payment_schedule import PaymentMode, PaymentSchedule
from ..school.value_objects import LevelId, SchoolYearId
from ..shared.errors import DomainError, ZeroAmountError
from ..shared.value_objects import Currency, Money
from .value_objects import FeeCategory, FeeItemId, FeeScope


@dataclass
class FeeItem:
    id: FeeItemId
    school_year_id: SchoolYearId
    name: str
    category: FeeCategory
    amount: Money                                  # montant par défaut
    scope: FeeScope
    class_amounts: Dict[str, int] = field(default_factory=dict)  # surcharges par classe
    payment_mode: PaymentMode = PaymentMode.UNIQUE
    nb_months: int = 10
    is_mandatory: bool = True
    is_active: bool = True
    is_system: bool = False
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Le nom de la ligne de frais ne peut pas être vide.")
        if self.amount.is_zero() and not self.is_system:
            raise ZeroAmountError("Le montant d'une ligne de frais doit être > 0.")
        if self.is_system and self.category != FeeCategory.SCOLARITE:
            raise DomainError("Une ligne système doit avoir la catégorie SCOLARITE.")
        if not self.is_system and self.category == FeeCategory.SCOLARITE:
            raise DomainError(
                "La catégorie SCOLARITE est réservée aux lignes système."
            )
        if self.nb_months < 1:
            raise ValueError("Le nombre de mois doit être >= 1.")
        for class_id, montant in (self.class_amounts or {}).items():
            if not isinstance(montant, int) or montant <= 0:
                raise ValueError(f"La surcharge pour {class_id} doit être un entier > 0.")
        # Cohérence portée / surcharges : si scope CLASSES, chaque surcharge
        # doit cibler une classe présente dans la portée.
        if (
            self.scope.scope_type.value == "CLASSES"
            and self.class_amounts
        ):
            from .value_objects import FeeScopeType
            scope_class_ids = set(str(cid) for cid in self.scope.class_ids)
            invalid = set(str(k) for k in self.class_amounts.keys()) - scope_class_ids
            if invalid:
                raise DomainError(
                    f"Surcharge(s) pour des classes hors portée : "
                    f"{', '.join(sorted(invalid))}. "
                    f"Seules les classes sélectionnées dans la portée peuvent "
                    f"avoir un tarif spécifique."
                )

    def applies_to(self, class_id: Optional[str]) -> bool:
        return self.scope.applies_to(class_id)

    def amount_for(self, class_id: Optional[str]) -> Money:
        """Montant effectif : surcharge si elle existe, sinon montant par défaut."""
        if class_id and self.class_amounts and class_id in self.class_amounts:
            return Money(self.class_amounts[class_id], self.amount.currency)
        return self.amount

    def get_payment_schedule(
        self,
        year_start: datetime.date,
        class_id: Optional[str] = None,
    ) -> PaymentSchedule:
        """Génère l'échéancier au montant effectif de la classe (ou défaut)."""
        effective = self.amount_for(class_id)
        if self.payment_mode == PaymentMode.UNIQUE:
            return PaymentSchedule.for_unique(effective, year_start)
        elif self.payment_mode == PaymentMode.TRANCHES:
            return PaymentSchedule.for_tranches(effective, year_start)
        return PaymentSchedule.for_mensuel(effective, year_start, nb_months=self.nb_months)

    def has_variable_amounts(self) -> bool:
        """True si le poste a des montants différents selon les classes."""
        return bool(self.class_amounts)

    def deactivate(self) -> None:
        if self.is_system:
            raise DomainError(
                "Impossible de désactiver une ligne système (scolarité). "
                "Modifiez le tarif du niveau à la place."
            )
        self.is_active = False

    def __str__(self) -> str:
        suffix = " (variable)" if self.has_variable_amounts() else ""
        return f"{self.name} [{self.category.label}] — {self.amount}{suffix}"
